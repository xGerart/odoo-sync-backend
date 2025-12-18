"""
Product Sync History schemas.
"""
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel


class ProductSyncHistoryItemResponse(BaseModel):
    """Response schema for a product sync history item."""
    id: int
    barcode: str
    product_id: int
    product_name: str
    action: str  # 'created', 'updated', 'error'
    quantity_processed: float
    success: bool
    error_message: Optional[str] = None
    stock_before: Optional[float] = None
    stock_after: Optional[float] = None
    stock_updated: bool = False
    old_standard_price: Optional[float] = None
    new_standard_price: Optional[float] = None
    old_list_price: Optional[float] = None
    new_list_price: Optional[float] = None
    price_updated: bool = False
    is_new_product: bool = False

    class Config:
        from_attributes = True


class ProductSyncHistoryResponse(BaseModel):
    """Response schema for product sync history."""
    id: int
    xml_filename: str
    xml_provider: str
    profit_margin: Optional[float] = None
    quantity_mode: str
    apply_iva: bool
    executed_by: str
    executed_at: datetime
    total_items: int
    successful_items: int
    failed_items: int
    created_count: int
    updated_count: int
    has_errors: bool
    error_summary: Optional[str] = None
    pdf_filename: Optional[str] = None
    items: List[ProductSyncHistoryItemResponse] = []

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": 1,
                "xml_filename": "factura_dmujeres_20251217.xml",
                "xml_provider": "D'Mujeres",
                "profit_margin": 0.3,
                "quantity_mode": "replace",
                "apply_iva": True,
                "executed_by": "admin",
                "executed_at": "2025-12-17T10:30:00",
                "total_items": 50,
                "successful_items": 48,
                "failed_items": 2,
                "created_count": 10,
                "updated_count": 38,
                "has_errors": True,
                "error_summary": "2 products failed: Product A: Invalid barcode, Product B: Not found",
                "pdf_filename": "sync_report_20251217_103000.pdf",
                "items": []
            }
        }


class ProductSyncHistoryListResponse(BaseModel):
    """Response schema for list of product sync history."""
    history: List[ProductSyncHistoryResponse]
    total: int

    class Config:
        json_schema_extra = {
            "example": {
                "history": [],
                "total": 0
            }
        }
