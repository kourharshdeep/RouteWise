"""FastAPI authentication and role-based authorization dependencies."""
from __future__ import annotations

from typing import Callable, Sequence
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.api.schemas.auth import UserProfile, UserRole
from src.services.auth_service import auth_service

security = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> UserProfile:
    """Dependency that extracts and verifies bearer token, returning current user or guest profile.
    
    Returns 401 Unauthorized for missing, malformed, or expired tokens.
    """
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token required. Please sign in or continue as guest.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = auth_service.verify_token(credentials.credentials)
    user_id = int(payload.get("sub", 0))
    return auth_service.get_user_by_id(user_id)


def require_role(*allowed_roles: str) -> Callable[[UserProfile], UserProfile]:
    """Dependency factory returning a validator that enforces allowed user roles.
    
    Returns 401 if not authenticated, and 403 Forbidden if user role is insufficient.
    """
    def role_checker(current_user: UserProfile = Depends(get_current_user)) -> UserProfile:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Access forbidden: requires role in [{', '.join(allowed_roles)}]. "
                    f"Your active role is '{current_user.role}'."
                ),
            )
        return current_user

    return role_checker


# Common convenience role guards
require_authenticated = require_role(UserRole.USER.value, UserRole.PATROL.value, UserRole.ADMIN.value)
require_patrol = require_role(UserRole.PATROL.value, UserRole.ADMIN.value)
require_admin = require_role(UserRole.ADMIN.value)
