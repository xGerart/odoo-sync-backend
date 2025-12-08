"""
Transfer-related schemas.
"""
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field


class TransferItem(BaseModel):
    """Single product item in a transfer."""
    barcode: str = Field(..., description="Product barcode")
    quantity: int = Field(..., gt=0, description="Quantity to transfer")

    class Config:
        json_schema_extra = {
            "example": {
                "barcode": "123456789",
                "quantity": 5
            }
        }


class TransferRequest(BaseModel):
    """Request to prepare a transfer."""
    products: List[TransferItem] = Field(..., min_length=1, description="Products to transfer")

    class Config:
        json_schema_extra = {
            "example": {
                "products": [
                    {"barcode": "123456789", "quantity": 5},
                    {"barcode": "987654321", "quantity": 3}
                ]
            }
        }


class VerifyTransferRequest(BaseModel):
    """Request to verify a transfer (bodeguero verifying cajero's transfer)."""
    transfer_id: int = Field(..., description="ID of transfer to verify")
    products: List[TransferItem] = Field(..., min_length=1, description="Verified products (can be edited)")

    class Config:
        json_schema_extra = {
            "example": {
                "transfer_id": 1,
                "products": [
                    {"barcode": "123456789", "quantity": 5},
                    {"barcode": "987654321", "quantity": 3}
                ]
            }
        }


class ConfirmTransferRequest(BaseModel):
    """Request to confirm and execute a transfer."""
    products: List[TransferItem] = Field(..., min_length=1, description="Final confirmed products")

    class Config:
        json_schema_extra = {
            "example": {
                "products": [
                    {"barcode": "123456789", "quantity": 5},
                    {"barcode": "987654321", "quantity": 3}
                ]
            }
        }


class TransferProductDetail(BaseModel):
    """Detailed product information in transfer response."""
    barcode: str
    name: str
    quantity_requested: int
    quantity_transferred: int
    stock_before: float
    stock_after: float
    success: bool
    error_message: Optional[str] = None


class TransferResponse(BaseModel):
    """Response from transfer operation."""
    success: bool
    message: str
    xml_content: Optional[str] = Field(None, description="Generated XML content")
    pdf_content: Optional[str] = Field(None, description="Base64 encoded PDF")
    pdf_filename: Optional[str] = Field(None, description="PDF filename for download")
    processed_count: int = Field(default=0, description="Number of products processed")
    inventory_reduced: bool = Field(default=False, description="Whether inventory was actually reduced")
    products: Optional[List[TransferProductDetail]] = None

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Transfer prepared successfully",
                "xml_content": "<?xml version='1.0'?>...",
                "pdf_filename": "transfer_admin_report_20240115_103000.pdf",
                "processed_count": 2,
                "inventory_reduced": False
            }
        }


class TransferValidationError(BaseModel):
    """Transfer validation error details."""
    barcode: str
    product_name: str
    error_type: str  # 'not_found', 'insufficient_stock', 'exceeds_limit'
    requested_quantity: int
    available_quantity: float
    max_allowed_quantity: Optional[float] = None


class TransferValidationResponse(BaseModel):
    """Response from transfer validation."""
    valid: bool
    errors: List[TransferValidationError]
    warnings: List[str] = []


# Pending Transfer Schemas

class PendingTransferItemResponse(BaseModel):
    """Response schema for a pending transfer item."""
    id: int
    barcode: str
    product_id: int
    product_name: str
    quantity: int
    available_stock: int
    unit_price: Optional[float] = None

    class Config:
        from_attributes = True


class PendingTransferResponse(BaseModel):
    """Response schema for a pending transfer."""
    id: int
    user_id: Optional[int] = None  # Nullable for Odoo admins
    username: str
    created_by_role: Optional[str] = None  # 'admin', 'bodeguero', 'cajero'
    status: str
    created_at: datetime
    updated_at: datetime
    verified_at: Optional[datetime] = None
    verified_by: Optional[str] = None
    confirmed_at: Optional[datetime] = None
    confirmed_by: Optional[str] = None
    items: List[PendingTransferItemResponse] = []

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": 1,
                "user_id": 5,
                "username": "bodeguero1",
                "created_by_role": "bodeguero",
                "status": "pending",
                "created_at": "2025-12-03T10:30:00",
                "updated_at": "2025-12-03T10:30:00",
                "verified_at": None,
                "verified_by": None,
                "confirmed_at": None,
                "confirmed_by": None,
                "items": [
                    {
                        "id": 1,
                        "barcode": "123456789",
                        "product_id": 100,
                        "product_name": "Producto Ejemplo",
                        "quantity": 5,
                        "available_stock": 20,
                        "unit_price": 15.50
                    }
                ]
            }
        }


class PendingTransferListResponse(BaseModel):
    """Response schema for list of pending transfers."""
    transfers: List[PendingTransferResponse]
    total: int

    class Config:
        json_schema_extra = {
            "example": {
                "transfers": [
                    {
                        "id": 1,
                        "username": "bodeguero1",
                        "status": "pending",
                        "created_at": "2025-12-03T10:30:00",
                        "items": []
                    }
                ],
                "total": 1
            }
        }
