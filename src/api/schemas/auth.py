"""Authentication and user schemas."""
from __future__ import annotations

from enum import Enum
from typing import Optional
from pydantic import BaseModel, EmailStr, Field


class UserRole(str, Enum):
    GUEST = "guest"
    USER = "user"
    PATROL = "patrol"
    ADMIN = "admin"


class UserRegisterRequest(BaseModel):
    """Payload for registering a new user."""

    email: str = Field(..., description="User's email address")
    password: str = Field(..., min_length=6, description="Password with minimum 6 characters")
    name: str = Field(..., min_length=2, description="User full name")
    role: Optional[str] = Field(default=None, description="Client-supplied role (ignored by server; public registrations always receive role 'user')")
    preferred_vehicle: str = Field(default="Car", description="Default vehicle type: Car, Motorcycle, Bus, Truck, Other")


class UserLoginRequest(BaseModel):
    """Payload for user login."""

    email: str = Field(..., description="User email address")
    password: str = Field(..., description="User password")


class UserProfile(BaseModel):
    """Public user profile."""

    id: int
    email: str
    name: str
    role: str
    preferred_vehicle: str
    created_at: str
    is_simulated: bool = False


class AuthTokenResponse(BaseModel):
    """Authentication response with bearer token."""

    access_token: str
    token_type: str = "bearer"
    user: UserProfile
    message: str = "Authentication successful"


class UserUpdateRequest(BaseModel):
    """Payload for updating user profile / preferences."""

    name: Optional[str] = None
    preferred_vehicle: Optional[str] = None


class RolePromotionRequest(BaseModel):
    """Admin-only payload for promoting/demoting user roles."""

    role: str = Field(..., description="Target role: 'user', 'patrol', or 'admin'")
