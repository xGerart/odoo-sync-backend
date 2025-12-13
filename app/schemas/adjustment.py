"""
Adjustment-related schemas.
"""
from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field
from enum import Enum
import json


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


# Complete Adjustment History Schemas (with snapshots and PDF)

class AdjustmentHistoryItemDetailResponse(BaseModel):
    """Detailed response schema for adjustment history item."""
    id: int
    barcode: str
    product_id: int
    product_name: str
    quantity_requested: int
    quantity_adjusted: int
    adjustment_type: str
    reason: Optional[str] = None
    success: bool
    error_message: Optional[str] = None
    stock_before: Optional[int] = None
    stock_after: Optional[int] = None
    unit_price: Optional[float] = None
    total_value: Optional[float] = None

    class Config:
        from_attributes = True


class AdjustmentHistoryDetailResponse(BaseModel):
    """Complete adjustment history record with all details."""
    id: int
    pending_adjustment_id: Optional[int] = None
    location: str
    location_name: Optional[str] = None
    executed_by: str
    executed_at: datetime
    total_items: int
    successful_items: int
    failed_items: int
    total_quantity_requested: int
    total_quantity_adjusted: int
    pdf_filename: Optional[str] = None
    has_errors: bool
    error_summary: Optional[str] = None
    items: List[AdjustmentHistoryItemDetailResponse] = []
    snapshots_before: List[Dict[str, Any]] = []
    snapshots_after: List[Dict[str, Any]] = []

    class Config:
        from_attributes = True

    @classmethod
    def model_validate(cls, obj: Any, **kwargs):
        """Custom validation to parse JSON fields."""
        if isinstance(obj, dict):
            # Already a dict, use default validation
            return super().model_validate(obj, **kwargs)

        # Parse from ORM object
        data = {
            'id': obj.id,
            'pending_adjustment_id': obj.pending_adjustment_id,
            'location': obj.location,
            'location_name': obj.location_name,
            'executed_by': obj.executed_by,
            'executed_at': obj.executed_at,
            'total_items': obj.total_items,
            'successful_items': obj.successful_items,
            'failed_items': obj.failed_items,
            'total_quantity_requested': obj.total_quantity_requested,
            'total_quantity_adjusted': obj.total_quantity_adjusted,
            'pdf_filename': obj.pdf_filename,
            'has_errors': obj.has_errors,
            'error_summary': obj.error_summary,
            'items': [AdjustmentHistoryItemDetailResponse.model_validate(item) for item in obj.items],
            'snapshots_before': json.loads(obj.snapshots_before) if obj.snapshots_before else [],
            'snapshots_after': json.loads(obj.snapshots_after) if obj.snapshots_after else []
        }
        return cls(**data)


class AdjustmentHistoryListResponse(BaseModel):
    """Response schema for list of complete adjustment histories."""
    history: List[AdjustmentHistoryDetailResponse]
    total: int


# ============================================================
# Unified History Schemas (combines pending + history)
# ============================================================

class UnifiedAdjustmentRecord(BaseModel):
    """Unified record combining pending and history adjustments."""
    id: str = Field(..., description="Composite ID: 'pending_{id}' or 'history_{id}'")
    original_id: int = Field(..., description="Original record ID from database")
    source: str = Field(..., description="Source table: 'pending' or 'history'")
    status: str = Field(..., description="Status: 'pending', 'confirmed', or 'rejected'")
    adjustment_type: str = Field(..., description="Adjustment type")
    username: str = Field(..., description="User who created/executed the adjustment")
    created_at: datetime = Field(..., description="Creation date")
    updated_at: datetime = Field(..., description="Last update date")
    confirmed_at: Optional[datetime] = Field(None, description="Confirmation date")
    confirmed_by: Optional[str] = Field(None, description="Admin who confirmed")
    total_items: int = Field(..., description="Total number of items")
    successful_items: Optional[int] = Field(None, description="Successful items (history only)")
    failed_items: Optional[int] = Field(None, description="Failed items (history only)")
    items: List[Dict[str, Any]] = Field(..., description="List of adjustment items")
    has_pdf: bool = Field(..., description="Whether PDF report is available")
    pdf_filename: Optional[str] = Field(None, description="PDF filename")
    has_errors: Optional[bool] = Field(None, description="Whether execution had errors (history only)")

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "pending_123",
                "original_id": 123,
                "source": "pending",
                "status": "pending",
                "adjustment_type": "entry",
                "username": "bodeguero1",
                "created_at": "2025-01-15T10:30:00",
                "updated_at": "2025-01-15T10:30:00",
                "confirmed_at": None,
                "confirmed_by": None,
                "total_items": 5,
                "successful_items": None,
                "failed_items": None,
                "items": [],
                "has_pdf": False,
                "pdf_filename": None,
                "has_errors": None
            }
        }


class UnifiedAdjustmentHistoryResponse(BaseModel):
    """Response for unified adjustment history (pending + confirmed + rejected)."""
    records: List[UnifiedAdjustmentRecord] = Field(..., description="List of unified adjustment records")
    total: int = Field(..., description="Total number of records")

    class Config:
        json_schema_extra = {
            "example": {
                "records": [],
                "total": 0
            }
        }
