"""Authentication and User Management Service.

Provides secure SQLite-backed user storage, PBKDF2 password hashing with per-user salt,
HMAC-SHA256 bearer token issuance and validation, and role-based access control.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status

from src.api.config import settings
from src.api.schemas.auth import (
    AuthTokenResponse,
    UserProfile,
    UserRegisterRequest,
    UserRole,
    UserUpdateRequest,
)


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _b64url_decode(s: str) -> bytes:
    padding = 4 - (len(s) % 4)
    if padding and padding < 4:
        s += "=" * padding
    return base64.urlsafe_b64decode(s.encode("utf-8"))


class AuthService:
    """Manages authentication, tokens, credentials, and role lifecycle."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or settings.db_path
        self.secret_key = settings.secret_key.encode("utf-8")
        self._failed_attempts: Dict[str, List[float]] = {}
        self._init_db()

    def _check_login_throttle(self, key: str) -> None:
        now = time.time()
        window = 60.0  # 60 seconds sliding window
        max_attempts = 5
        attempts = [t for t in self._failed_attempts.get(key, []) if now - t < window]
        self._failed_attempts[key] = attempts
        if len(attempts) >= max_attempts:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many failed login attempts. Please wait 60 seconds before retrying.",
            )

    def _record_failed_attempt(self, key: str) -> None:
        now = time.time()
        if key not in self._failed_attempts:
            self._failed_attempts[key] = []
        self._failed_attempts[key].append(now)

    def _clear_failed_attempts(self, key: str) -> None:
        self._failed_attempts.pop(key, None)

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Initializes tables and performs schema migrations if necessary."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT UNIQUE NOT NULL COLLATE NOCASE,
                    name TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'user',
                    preferred_vehicle TEXT NOT NULL DEFAULT 'Car',
                    created_at TEXT NOT NULL,
                    is_simulated INTEGER NOT NULL DEFAULT 0
                );
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);")

            # Check if is_simulated column exists in case of existing database
            cols = [r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
            if "is_simulated" not in cols:
                conn.execute("ALTER TABLE users ADD COLUMN is_simulated INTEGER NOT NULL DEFAULT 0;")

            # Normalize legacy roles to strictly: guest, user, patrol, admin
            conn.execute("UPDATE users SET role = 'user' WHERE role IN ('commuter', 'logistics_operator');")
            conn.execute("UPDATE users SET role = 'patrol' WHERE role = 'patrol_officer';")

            conn.commit()

    def _hash_password(self, password: str, salt: str) -> str:
        key = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            100_000,
        )
        return key.hex()

    def create_token(
        self,
        user_id: int,
        email: str,
        role: str,
        expire_hours: Optional[int] = None,
    ) -> str:
        """Issues an HMAC-SHA256 signed bearer token."""
        header = {"alg": "HS256", "typ": "JWT"}
        exp_hours = expire_hours if expire_hours is not None else settings.token_expire_hours
        exp = int(time.time()) + (exp_hours * 3600)
        payload = {
            "sub": str(user_id),
            "email": email,
            "role": role,
            "exp": exp,
            "iat": int(time.time()),
        }

        header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
        payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
        signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
        signature = hmac.new(self.secret_key, signing_input, hashlib.sha256).digest()
        sig_b64 = _b64url_encode(signature)

        return f"{header_b64}.{payload_b64}.{sig_b64}"

    def verify_token(self, token: str) -> Dict[str, Any]:
        """Validates token signature and expiration, returning decoded payload."""
        parts = token.split(".")
        if len(parts) != 3:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token structure. Please sign in again.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        header_b64, payload_b64, sig_b64 = parts
        signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
        expected_sig = hmac.new(self.secret_key, signing_input, hashlib.sha256).digest()

        try:
            provided_sig = _b64url_decode(sig_b64)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Malformed token signature. Please sign in again.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not hmac.compare_digest(expected_sig, provided_sig):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token signature. Authentication failed.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        try:
            payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Malformed token payload.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if "exp" in payload and payload["exp"] < time.time():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired. Please sign in again.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return payload

    def register(self, req: UserRegisterRequest) -> AuthTokenResponse:
        """Registers a new user.
        
        Public registration ALWAYS creates role 'user'. Any client-supplied
        role is ignored to strictly prevent privilege escalation.
        """
        clean_email = req.email.strip().lower()
        # Role is explicitly hard-forced to 'user'
        assigned_role = UserRole.USER.value

        with self._get_connection() as conn:
            row = conn.execute("SELECT id FROM users WHERE email = ?", (clean_email,)).fetchone()
            if row:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="An account with this email address already exists.",
                )

            salt = secrets.token_hex(16)
            pwd_hash = self._hash_password(req.password, salt)
            now = datetime.now(timezone.utc).isoformat()

            cursor = conn.execute(
                """
                INSERT INTO users (email, name, password_hash, salt, role, preferred_vehicle, created_at, is_simulated)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (clean_email, req.name.strip(), pwd_hash, salt, assigned_role, req.preferred_vehicle, now),
            )
            conn.commit()
            user_id = cursor.lastrowid

        user_profile = UserProfile(
            id=user_id,
            email=clean_email,
            name=req.name.strip(),
            role=assigned_role,
            preferred_vehicle=req.preferred_vehicle,
            created_at=now,
            is_simulated=False,
        )
        token = self.create_token(user_id, clean_email, assigned_role)
        return AuthTokenResponse(
            access_token=token,
            user=user_profile,
            message="Account registered successfully.",
        )

    def login(self, email: str, password: str) -> AuthTokenResponse:
        """Authenticates user with generic error messages and rate throttling."""
        clean_email = email.strip().lower()
        self._check_login_throttle(clean_email)

        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT id, email, name, password_hash, salt, role, preferred_vehicle, created_at, is_simulated FROM users WHERE email = ?",
                (clean_email,),
            ).fetchone()

        if not row:
            self._record_failed_attempt(clean_email)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        expected_hash = self._hash_password(password, row["salt"])
        if not hmac.compare_digest(expected_hash, row["password_hash"]):
            self._record_failed_attempt(clean_email)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        self._clear_failed_attempts(clean_email)

        user_profile = UserProfile(
            id=row["id"],
            email=row["email"],
            name=row["name"],
            role=row["role"],
            preferred_vehicle=row["preferred_vehicle"],
            created_at=row["created_at"],
            is_simulated=bool(row["is_simulated"]),
        )
        token = self.create_token(row["id"], row["email"], row["role"])
        return AuthTokenResponse(
            access_token=token,
            user=user_profile,
            message="Sign-in successful.",
        )

    def create_guest_session(self) -> AuthTokenResponse:
        """Issues a server-validated short-lived guest session token."""
        guest_email = "guest@routewise.local"
        token = self.create_token(
            user_id=0,
            email=guest_email,
            role=UserRole.GUEST.value,
            expire_hours=settings.guest_token_expire_hours,
        )
        guest_profile = UserProfile(
            id=0,
            email=guest_email,
            name="Guest Observer",
            role=UserRole.GUEST.value,
            preferred_vehicle="Car",
            created_at=datetime.now(timezone.utc).isoformat(),
            is_simulated=False,
        )
        return AuthTokenResponse(
            access_token=token,
            user=guest_profile,
            message="Guest session initialized. Strictly read-only access granted.",
        )

    def get_user_by_id(self, user_id: int) -> UserProfile:
        """Retrieves user profile by ID, handling guest user ID 0."""
        if user_id == 0:
            return UserProfile(
                id=0,
                email="guest@routewise.local",
                name="Guest Observer",
                role=UserRole.GUEST.value,
                preferred_vehicle="Car",
                created_at="2026-01-01T00:00:00Z",
                is_simulated=False,
            )

        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT id, email, name, role, preferred_vehicle, created_at, is_simulated FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()

        if not row:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User account no longer exists. Please sign in again.",
            )

        return UserProfile(
            id=row["id"],
            email=row["email"],
            name=row["name"],
            role=row["role"],
            preferred_vehicle=row["preferred_vehicle"],
            created_at=row["created_at"],
            is_simulated=bool(row["is_simulated"]),
        )

    def update_user(self, user_id: int, req: UserUpdateRequest) -> UserProfile:
        """Updates profile details for an authenticated user."""
        if user_id == 0:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Guest users cannot modify account profile. Please sign in or create an account.",
            )

        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            if not row:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

            new_name = req.name.strip() if req.name else row["name"]
            new_veh = req.preferred_vehicle if req.preferred_vehicle else row["preferred_vehicle"]

            conn.execute(
                "UPDATE users SET name = ?, preferred_vehicle = ? WHERE id = ?",
                (new_name, new_veh, user_id),
            )
            conn.commit()

            updated = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

        return UserProfile(
            id=updated["id"],
            email=updated["email"],
            name=updated["name"],
            role=updated["role"],
            preferred_vehicle=updated["preferred_vehicle"],
            created_at=updated["created_at"],
            is_simulated=bool(updated["is_simulated"]),
        )

    def promote_user(self, user_id: int, target_role: str) -> UserProfile:
        """Admin-only method to update role of a user."""
        if target_role not in [r.value for r in UserRole if r != UserRole.GUEST]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid target role '{target_role}'. Valid roles are: 'user', 'patrol', 'admin'.",
            )

        with self._get_connection() as conn:
            row = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
            if not row:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

            conn.execute("UPDATE users SET role = ? WHERE id = ?", (target_role, user_id))
            conn.commit()
            updated = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

        return UserProfile(
            id=updated["id"],
            email=updated["email"],
            name=updated["name"],
            role=updated["role"],
            preferred_vehicle=updated["preferred_vehicle"],
            created_at=updated["created_at"],
            is_simulated=bool(updated["is_simulated"]),
        )

    def create_patrol_user(
        self,
        email: str,
        name: str,
        password: str,
        is_simulated: int = 0,
    ) -> UserProfile:
        """Provisions a verified patrol officer account."""
        clean_email = email.strip().lower()
        with self._get_connection() as conn:
            row = conn.execute("SELECT id FROM users WHERE email = ?", (clean_email,)).fetchone()
            salt = secrets.token_hex(16)
            pwd_hash = self._hash_password(password, salt)
            now = datetime.now(timezone.utc).isoformat()

            if row:
                # Update existing user to patrol
                conn.execute(
                    """
                    UPDATE users
                    SET name = ?, password_hash = ?, salt = ?, role = 'patrol', is_simulated = ?
                    WHERE id = ?
                    """,
                    (name.strip(), pwd_hash, salt, is_simulated, row["id"]),
                )
                user_id = row["id"]
            else:
                cursor = conn.execute(
                    """
                    INSERT INTO users (email, name, password_hash, salt, role, preferred_vehicle, created_at, is_simulated)
                    VALUES (?, ?, ?, ?, 'patrol', 'Patrol Vehicle', ?, ?)
                    """,
                    (clean_email, name.strip(), pwd_hash, salt, now, is_simulated),
                )
                user_id = cursor.lastrowid
            conn.commit()
            res = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

        return UserProfile(
            id=res["id"],
            email=res["email"],
            name=res["name"],
            role=res["role"],
            preferred_vehicle=res["preferred_vehicle"],
            created_at=res["created_at"],
            is_simulated=bool(res["is_simulated"]),
        )


auth_service = AuthService()
