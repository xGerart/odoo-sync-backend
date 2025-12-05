"""
Common schemas shared across features.
"""
from typing import Optional, Any, Dict
from pydantic import BaseModel, Field


class MessageResponse(BaseModel):
    """Generic message response."""
    message: str
    success: bool = True


class ErrorResponse(BaseModel):
    """Error response schema."""
    message: str
    success: bool = False
    details: Optional[Dict[str, Any]] = None


class PaginationParams(BaseModel):
    """Pagination parameters."""
    page: int = Field(default=1, ge=1, description="Page number (1-indexed)")
    page_size: int = Field(default=50, ge=1, le=1000, description="Items per page")

    @property
    def offset(self) -> int:
        """Calculate SQL offset from page number."""
        return (self.page - 1) * self.page_size


class PaginatedResponse(BaseModel):
    """Paginated response wrapper."""
    items: list
    total: int
    page: int
    page_size: int
    total_pages: int

    @classmethod
    def create(cls, items: list, total: int, params: PaginationParams):
        """Create paginated response from items and params."""
        total_pages = (total + params.page_size - 1) // params.page_size
        return cls(
            items=items,
            total=total,
            page=params.page,
            page_size=params.page_size,
            total_pages=total_pages
        )


class OdooConfigBase(BaseModel):
    """Base Odoo connection configuration."""
    url: str = Field(..., description="Odoo server URL")
    database: str = Field(..., description="Odoo database name")
    port: int = Field(default=443, ge=1, le=65535, description="Odoo port")
    verify_ssl: bool = Field(default=True, description="Verify SSL certificate")


class OdooCredentials(OdooConfigBase):
    """Odoo connection credentials."""
    username: str = Field(..., description="Odoo username")
    password: str = Field(..., description="Odoo password")

    class Config:
        json_schema_extra = {
            "example": {
                "url": "https://odoo.example.com",
                "database": "production_db",
                "port": 443,
                "username": "admin",
                "password": "password123",
                "verify_ssl": True
            }
        }


class BranchConnectionRequest(BaseModel):
    """Branch connection request using location selector."""
    location_id: str = Field(..., description="Location ID (principal, sucursal, sucursal_sacha)")
    username: str = Field(..., description="Odoo username")
    password: str = Field(..., description="Odoo password")
    verify_ssl: bool = Field(default=True, description="Verify SSL certificate")

    class Config:
        json_schema_extra = {
            "example": {
                "location_id": "sucursal",
                "username": "admin",
                "password": "password123",
                "verify_ssl": True
            }
        }


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str
    environment: str
    database_connected: bool
    odoo_principal_status: Optional[str] = None
    odoo_sucursal_status: Optional[str] = None
