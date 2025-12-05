"""
User-related schemas.
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, field_validator
from app.core.constants import UserRole


class UserBase(BaseModel):
    """Base user schema."""
    username: str = Field(..., min_length=3, max_length=50, description="Username")
    email: EmailStr = Field(..., description="Email address")
    full_name: Optional[str] = Field(None, max_length=100, description="Full name")


class UserCreate(UserBase):
    """Schema for creating a new user."""
    password: str = Field(..., min_length=8, description="Password (min 8 characters)")
    role: UserRole = Field(..., description="User role (cajero or bodeguero)")

    @field_validator('role')
    @classmethod
    def validate_role(cls, v: UserRole) -> UserRole:
        """Ensure role is not admin (admins auth via Odoo)."""
        if v == UserRole.ADMIN:
            raise ValueError("Cannot create admin users. Admins authenticate via Odoo.")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "username": "jperez",
                "email": "jperez@example.com",
                "full_name": "Juan Pérez",
                "password": "SecurePass123",
                "role": "cajero"
            }
        }


class UserUpdate(BaseModel):
    """Schema for updating a user."""
    email: Optional[EmailStr] = None
    full_name: Optional[str] = Field(None, max_length=100)
    password: Optional[str] = Field(None, min_length=8)
    is_active: Optional[bool] = None
    role: Optional[UserRole] = None

    @field_validator('role')
    @classmethod
    def validate_role(cls, v: Optional[UserRole]) -> Optional[UserRole]:
        """Ensure role is not admin (admins auth via Odoo)."""
        if v == UserRole.ADMIN:
            raise ValueError("Cannot assign admin role. Admins authenticate via Odoo.")
        return v


class UserResponse(UserBase):
    """Schema for user response."""
    id: int
    role: UserRole
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": 1,
                "username": "jperez",
                "email": "jperez@example.com",
                "full_name": "Juan Pérez",
                "role": "cajero",
                "is_active": True,
                "created_at": "2024-01-15T10:30:00",
                "updated_at": "2024-01-15T10:30:00"
            }
        }


class UserListResponse(BaseModel):
    """Schema for list of users."""
    users: list[UserResponse]
    total: int
