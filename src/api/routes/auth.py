"""Authentication API routes."""
from __future__ import annotations

import sqlite3
from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException, status

from src.api.dependencies import get_current_user, require_admin
from src.api.schemas.auth import (
    AuthTokenResponse,
    RolePromotionRequest,
    UserProfile,
    UserRegisterRequest,
    UserLoginRequest,
    UserUpdateRequest,
)
from src.services.auth_service import auth_service
from src.api.config import settings

router = APIRouter(prefix="/v1/auth", tags=["Authentication"])


@router.post("/register", response_model=AuthTokenResponse, status_code=status.HTTP_201_CREATED)
def register(req: UserRegisterRequest) -> AuthTokenResponse:
    """Registers a new user. Public registration strictly creates role 'user'."""
    return auth_service.register(req)


@router.post("/login", response_model=AuthTokenResponse)
def login(req: UserLoginRequest) -> AuthTokenResponse:
    """Authenticates credentials and returns bearer access token."""
    return auth_service.login(req.email, req.password)


@router.post("/guest", response_model=AuthTokenResponse)
def guest_login() -> AuthTokenResponse:
    """Issues a server-validated short-lived guest session with strictly read-only access."""
    return auth_service.create_guest_session()


@router.get("/me", response_model=UserProfile)
def get_me(current_user: UserProfile = Depends(get_current_user)) -> UserProfile:
    """Returns the profile of the currently authenticated user or guest."""
    return current_user


@router.put("/profile", response_model=UserProfile)
def update_profile(
    req: UserUpdateRequest,
    current_user: UserProfile = Depends(get_current_user),
) -> UserProfile:
    """Updates profile and preferred vehicle for the current user. Blocked for guests."""
    if current_user.role == "guest":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Guest users cannot modify account profile. Please sign in or create an account.",
        )
    return auth_service.update_user(current_user.id, req)


@router.patch("/users/{user_id}/role", response_model=UserProfile)
def promote_user_role(
    user_id: int,
    req: RolePromotionRequest,
    _: UserProfile = Depends(require_admin),
) -> UserProfile:
    """Admin-only endpoint to promote or alter user role."""
    return auth_service.promote_user(user_id, req.role)


@router.get("/demo-accounts")
def get_demo_accounts() -> List[Dict[str, Any]]:
    """Returns currently available demo accounts seeded for evaluation."""
    accounts = []
    with auth_service._get_connection() as conn:
        rows = conn.execute(
            "SELECT email, name, role, preferred_vehicle, is_simulated FROM users WHERE is_simulated = 1"
        ).fetchall()
        for r in rows:
            pwd = settings.demo_patrol_password if r["role"] == "patrol" else "routewise2026"
            accounts.append({
                "name": r["name"],
                "email": r["email"],
                "password": pwd,
                "role": r["role"],
                "vehicle": r["preferred_vehicle"],
                "is_simulated": bool(r["is_simulated"]),
            })

    # If none seeded yet, provide clean 안내
    if not accounts:
        return [
            {
                "name": "Demo Patrol Officer (Unseeded)",
                "email": "patrol@routewise.ai",
                "password": settings.demo_patrol_password,
                "role": "patrol",
                "vehicle": "Patrol Vehicle",
                "note": "Run 'python -m app.seed_demo' to seed simulated account and reports.",
                "is_simulated": True,
            },
            {
                "name": "Demo Public Commuter (Unseeded)",
                "email": "demo@routewise.ai",
                "password": "routewise2026",
                "role": "user",
                "vehicle": "Car",
                "note": "Run 'python -m app.seed_demo' to seed simulated account and reports.",
                "is_simulated": True,
            }
        ]
    return accounts
