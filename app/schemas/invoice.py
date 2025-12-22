"""
Invoice schemas for request/response validation.
Handles data transfer between API endpoints and clients.
"""
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field


# ============================================================================
# REQUEST SCHEMAS
# ============================================================================

class InvoiceItemUpdateRequest(BaseModel):
    """Request to update invoice item (bodeguero)."""
    quantity: float = Field(..., gt=0, description="Quantity in units")
    barcode: Optional[str] = Field(None, description="Product barcode")

    class Config:
        json_schema_extra = {
            "example": {
                "quantity": 120,
                "barcode": "7501234567890"
            }
        }


class InvoiceSubmitRequest(BaseModel):
    """Request to submit invoice as completed (bodeguero)."""
    notes: Optional[str] = Field(None, description="Optional notes or comments")

    class Config:
        json_schema_extra = {
            "example": {
                "notes": "Todos los códigos de barras verificados"
            }
        }


class InvoiceSyncRequest(BaseModel):
    """Request to sync invoice to Odoo (admin)."""
    notes: Optional[str] = Field(None, description="Optional admin notes")

    class Config:
        json_schema_extra = {
            "example": {
                "notes": "Sincronizado después de verificación"
            }
        }


# ============================================================================
# RESPONSE SCHEMAS
# ============================================================================

class InvoiceItemResponse(BaseModel):
    """Invoice item response (prices filtered based on role)."""
    id: int
    codigo_original: str
    product_name: str
    quantity: float
    cantidad_original: float
    barcode: Optional[str]
    modified_by_bodeguero: bool
    # Prices are Optional - will be None for bodeguero role
    unit_price: Optional[float] = None
    total_price: Optional[float] = None

    class Config:
        from_attributes = True


class PendingInvoiceResponse(BaseModel):
    """Pending invoice response with items."""
    id: int
    invoice_number: Optional[str]
    supplier_name: Optional[str]
    invoice_date: Optional[datetime]
    status: str
    uploaded_by_username: str
    xml_filename: str
    created_at: datetime
    updated_at: datetime
    submitted_at: Optional[datetime]
    submitted_by: Optional[str]
    notes: Optional[str]
    items: List[InvoiceItemResponse]
    total_items: int
    total_quantity: float

    class Config:
        from_attributes = True


class PendingInvoiceListResponse(BaseModel):
    """List of pending invoices."""
    invoices: List[PendingInvoiceResponse]
    total: int


class InvoiceUploadResponse(BaseModel):
    """Response after uploading XML invoices."""
    success: bool
    message: str
    invoices_created: int
    invoice_ids: List[int]
    total_products: int


class InvoiceSyncResponse(BaseModel):
    """Response after syncing invoice to Odoo."""
    success: bool
    message: str
    successful_items: int
    failed_items: int
    errors: List[str] = []


# ============================================================================
# HISTORY SCHEMAS
# ============================================================================

class InvoiceHistoryItemResponse(BaseModel):
    """Invoice history item response."""
    id: int
    codigo_original: str
    barcode: Optional[str]
    product_id: Optional[int]
    product_name: str
    quantity: float
    unit_price: Optional[float]
    total_value: Optional[float]
    success: bool
    error_message: Optional[str]
    was_modified: bool

    class Config:
        from_attributes = True


class InvoiceHistoryResponse(BaseModel):
    """Invoice history response."""
    id: int
    invoice_number: str
    supplier_name: Optional[str]
    uploaded_by: str
    synced_by: str
    synced_at: datetime
    total_items: int
    successful_items: int
    failed_items: int
    has_errors: bool
    items: List[InvoiceHistoryItemResponse]

    class Config:
        from_attributes = True


class InvoiceHistoryListResponse(BaseModel):
    """List of invoice history records."""
    history: List[InvoiceHistoryResponse]
    total: int
