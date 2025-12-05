"""
Authentication schemas.
"""
from typing import Optional
from pydantic import BaseModel, Field
from app.core.constants import UserRole, AuthSource


class LoginRequest(BaseModel):
    """Login request schema."""
    username: str = Field(..., description="Username or email")
    password: str = Field(..., description="Password")

    class Config:
        json_schema_extra = {
            "example": {
                "username": "admin",
                "password": "admin_password"
            }
        }


class OdooLoginRequest(LoginRequest):
    """Odoo admin login with location selector."""
    location_id: str = Field(..., description="Location ID (principal, sucursal, sucursal_sacha)")
    verify_ssl: bool = Field(default=True)

    class Config:
        json_schema_extra = {
            "example": {
                "username": "admin",
                "password": "admin_password",
                "location_id": "principal",
                "verify_ssl": True
            }
        }


class TokenResponse(BaseModel):
    """JWT token response."""
    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Token expiration time in seconds")

    class Config:
        json_schema_extra = {
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
                "expires_in": 86400
            }
        }


class LoginResponse(TokenResponse):
    """Login response with user info."""
    user: "UserInfo"

    class Config:
        json_schema_extra = {
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
                "expires_in": 86400,
                "user": {
                    "username": "jperez",
                    "role": "cajero",
                    "auth_source": "database",
                    "full_name": "Juan Pérez"
                }
            }
        }


class UserInfo(BaseModel):
    """User information from token."""
    username: str
    role: UserRole
    auth_source: AuthSource
    full_name: Optional[str] = None
    user_id: Optional[int] = None  # Only for database users

    class Config:
        json_schema_extra = {
            "example": {
                "username": "jperez",
                "role": "cajero",
                "auth_source": "database",
                "full_name": "Juan Pérez",
                "user_id": 1
            }
        }


class TokenPayload(BaseModel):
    """JWT token payload."""
    sub: str  # User ID or username
    username: str
    role: str
    auth_source: str
    exp: int
    iat: int
