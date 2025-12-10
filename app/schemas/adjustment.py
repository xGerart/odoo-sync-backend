"""
Adjustment-related schemas.
"""
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field
from enum import Enum


class AdjustmentTypeEnum(str, Enum):
    """Adjustment type enum for API."""
    ENTRY = "entry"
    EXIT = "exit"
    ADJUSTMENT = "adjustment"


class AdjustmentReasonEnum(str, Enum):
    """Adjustment reason enum for API."""
    # ENTRY reasons
    PURCHASE = "purchase"
    RETURN_IN = "return_in"
    CORRECTION_IN = "correction_in"
    # EXIT reasons
    SALE = "sale"
    DAMAGE = "damage"
    LOSS = "loss"
    THEFT = "theft"
    RETURN_OUT = "return_out"
    CORRECTION_OUT = "correction_out"
    LOCAL_SERVICE_USE = "local_service_use"  # Uso local de servicios
    EXPIRED = "expired"  # Caducado
    # ADJUSTMENT reasons
    PHYSICAL_COUNT = "physical_count"
    SYSTEM_CORRECTION = "system_correction"


class AdjustmentItem(BaseModel):
    """Single product item in an adjustment."""
    barcode: str = Field(..., description="Product barcode")
    product_id: int = Field(..., description="Odoo product ID")
    product_name: str = Field(..., description="Product name")
    quantity: int = Field(..., description="Quantity to adjust (negative for exits)")
    available_stock: int = Field(..., description="Current available stock")
    adjustment_type: AdjustmentTypeEnum = Field(..., description="Type of adjustment")
    reason: AdjustmentReasonEnum = Field(..., description="Reason for adjustment")
    description: Optional[str] = Field(None, description="Optional description")
    unit_price: Optional[float] = Field(None, description="Unit price")
    new_product_name: Optional[str] = Field(None, description="New product name (for ADJUSTMENT type)")
    photo_url: Optional[str] = Field(None, description="Photo URL (for ADJUSTMENT type)")

    class Config:
        json_schema_extra = {
            "example": {
                "barcode": "123456789",
                "product_id": 100,
                "product_name": "Producto Ejemplo",
                "quantity": 10,
                "available_stock": 50,
                "adjustment_type": "entry",
                "reason": "purchase",
                "description": "Compra de mercadería",
                "unit_price": 15.50,
                "new_product_name": None,
                "photo_url": None
            }
        }


class AdjustmentRequest(BaseModel):
    """Request to prepare an adjustment."""
    items: List[AdjustmentItem] = Field(..., min_length=1, description="Items to adjust")

    class Config:
        json_schema_extra = {
            "example": {
                "items": [
                    {
                        "barcode": "123456789",
                        "product_id": 100,
                        "product_name": "Producto A",
                        "quantity": 10,
                        "available_stock": 50,
                        "adjustment_type": "entry",
                        "reason": "purchase",
                        "description": "Nueva compra"
                    },
                    {
                        "barcode": "987654321",
                        "product_id": 101,
                        "product_name": "Producto B",
                        "quantity": -5,
                        "available_stock": 20,
                        "adjustment_type": "exit",
                        "reason": "damage",
                        "description": "Producto dañado"
                    }
                ]
            }
        }


class ConfirmAdjustmentRequest(BaseModel):
    """Request to confirm and execute an adjustment."""
    items: List[AdjustmentItem] = Field(..., min_length=1, description="Final confirmed items")

    class Config:
        json_schema_extra = {
            "example": {
                "items": [
                    {
                        "barcode": "123456789",
                        "product_id": 100,
                        "product_name": "Producto A",
                        "quantity": 10,
                        "available_stock": 50,
                        "adjustment_type": "entry",
                        "reason": "purchase"
                    }
                ]
            }
        }


class AdjustmentResponse(BaseModel):
    """Response from adjustment operation."""
    success: bool
    message: str
    processed_count: int = Field(default=0, description="Number of items processed")
    inventory_updated: bool = Field(default=False, description="Whether inventory was actually updated in Odoo")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Adjustment prepared successfully",
                "processed_count": 2,
                "inventory_updated": False
            }
        }


# Pending Adjustment Schemas

class PendingAdjustmentItemResponse(BaseModel):
    """Response schema for a pending adjustment item."""
    id: int
    barcode: str
    product_id: int
    product_name: str
    quantity: int
    available_stock: int
    adjustment_type: str
    reason: str
    description: Optional[str] = None
    unit_price: Optional[float] = None
    new_product_name: Optional[str] = None
    photo_url: Optional[str] = None

    class Config:
        from_attributes = True


class PendingAdjustmentResponse(BaseModel):
    """Response schema for a pending adjustment."""
    id: int
    user_id: Optional[int] = None
    username: str
    adjustment_type: str
    status: str
    created_at: datetime
    updated_at: datetime
    confirmed_at: Optional[datetime] = None
    confirmed_by: Optional[str] = None
    items: List[PendingAdjustmentItemResponse] = []

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": 1,
                "user_id": 5,
                "username": "bodeguero1",
                "adjustment_type": "entry",
                "status": "pending",
                "created_at": "2025-12-04T10:30:00",
                "updated_at": "2025-12-04T10:30:00",
                "confirmed_at": None,
                "confirmed_by": None,
                "items": [
                    {
                        "id": 1,
                        "barcode": "123456789",
                        "product_id": 100,
                        "product_name": "Producto Ejemplo",
                        "quantity": 10,
                        "available_stock": 50,
                        "adjustment_type": "entry",
                        "reason": "purchase",
                        "description": "Nueva compra",
                        "unit_price": 15.50
                    }
                ]
            }
        }


class PendingAdjustmentListResponse(BaseModel):
    """Response schema for list of pending adjustments."""
    adjustments: List[PendingAdjustmentResponse]
    total: int

    class Config:
        json_schema_extra = {
            "example": {
                "adjustments": [
                    {
                        "id": 1,
                        "username": "bodeguero1",
                        "adjustment_type": "entry",
                        "status": "pending",
                        "created_at": "2025-12-04T10:30:00",
                        "items": []
                    }
                ],
                "total": 1
            }
        }


# Adjustment History Schemas

class AdjustmentHistoryItemResponse(BaseModel):
    """Response schema for adjustment history item."""
    id: int
    adjustment_type: str
    product_name: str
    barcode: str
    quantity: int
    reason: str
    description: Optional[str] = None
    created_by: str
    confirmed_by: str
    created_at: datetime
    confirmed_at: datetime

    class Config:
        from_attributes = True


class AdjustmentHistoryResponse(BaseModel):
    """Response schema for adjustment history."""
    history: List[AdjustmentHistoryItemResponse]
    total: int

    class Config:
        json_schema_extra = {
            "example": {
                "history": [
                    {
                        "id": 1,
                        "adjustment_type": "entry",
                        "product_name": "Producto A",
                        "barcode": "123456789",
                        "quantity": 10,
                        "reason": "purchase",
                        "description": "Nueva compra",
                        "created_by": "bodeguero1",
                        "confirmed_by": "admin",
                        "created_at": "2025-12-04T10:30:00",
                        "confirmed_at": "2025-12-04T11:00:00"
                    }
                ],
                "total": 1
            }
        }
