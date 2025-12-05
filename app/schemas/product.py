"""
Product-related schemas.
"""
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator
from app.core.constants import QuantityMode, XMLProvider


class ProductData(BaseModel):
    """Raw product data from XML parsing."""
    descripcion: str = Field(..., description="Product description/name")
    cantidad: float = Field(..., ge=0, description="Quantity")
    codigo_auxiliar: Optional[str] = Field(None, description="Product barcode/SKU")
    precio_unitario: float = Field(..., gt=0, description="Unit price")

    class Config:
        json_schema_extra = {
            "example": {
                "descripcion": "Producto de ejemplo",
                "cantidad": 10.0,
                "codigo_auxiliar": "123456789",
                "precio_unitario": 5.50
            }
        }


class ProductMapped(BaseModel):
    """Product mapped to Odoo format."""
    name: str = Field(..., description="Product name")
    qty_available: float = Field(..., ge=0, description="Available quantity")
    barcode: str = Field(..., description="Product barcode")
    standard_price: float = Field(..., gt=0, description="Cost price")
    list_price: float = Field(..., gt=0, description="Sale price (without IVA)")
    display_price: Optional[float] = Field(None, description="Sale price with IVA for display")
    type: str = Field(default='storable', description="Product type")
    tracking: str = Field(default='none', description="Inventory tracking mode")
    available_in_pos: bool = Field(default=True, description="Available in POS")
    quantity_mode: QuantityMode = Field(default=QuantityMode.REPLACE, description="Quantity update mode")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Producto de ejemplo",
                "qty_available": 10.0,
                "barcode": "123456789",
                "standard_price": 5.50,
                "list_price": 8.25,
                "display_price": 9.49,
                "type": "storable",
                "tracking": "none",
                "available_in_pos": True,
                "quantity_mode": "replace"
            }
        }


class ProductInput(BaseModel):
    """Schema for manual product creation."""
    name: str = Field(..., min_length=1, description="Product name")
    qty_available: float = Field(..., ge=0, description="Available quantity")
    barcode: str = Field(..., min_length=1, description="Product barcode")
    standard_price: float = Field(..., gt=0, description="Cost price")
    list_price: float = Field(..., gt=0, description="Sale price (without IVA)")
    display_price: Optional[float] = None
    quantity_mode: QuantityMode = Field(default=QuantityMode.REPLACE)
    image_1920: Optional[str] = Field(None, description="Product image (base64)")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Nuevo Producto",
                "qty_available": 20.0,
                "barcode": "987654321",
                "standard_price": 10.00,
                "list_price": 15.00,
                "display_price": 17.25,
                "quantity_mode": "replace",
                "image_1920": None
            }
        }


class ProductResponse(BaseModel):
    """Product information response from Odoo."""
    id: int
    name: str
    barcode: Optional[str] = None
    qty_available: float
    standard_price: float
    list_price: float
    display_price: Optional[float] = None
    tracking: Optional[str] = None
    available_in_pos: bool
    image_1920: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "id": 123,
                "name": "Producto de ejemplo",
                "barcode": "123456789",
                "qty_available": 10.0,
                "standard_price": 5.50,
                "list_price": 8.25,
                "display_price": 9.49,
                "tracking": "none",
                "available_in_pos": True,
                "image_1920": None
            }
        }


class SyncResult(BaseModel):
    """Result of a single product sync operation."""
    success: bool
    message: str
    product_id: Optional[int] = None
    action: str = Field(..., description="Action taken: 'created', 'updated', or 'error'")
    product_name: Optional[str] = None
    barcode: Optional[str] = None
    error_details: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Product created successfully",
                "product_id": 123,
                "action": "created",
                "product_name": "Producto de ejemplo",
                "barcode": "123456789"
            }
        }


class SyncResponse(BaseModel):
    """Response from bulk product sync operation."""
    results: List[SyncResult]
    total_processed: int
    created_count: int
    updated_count: int
    errors_count: int
    pdf_filename: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "results": [],
                "total_processed": 25,
                "created_count": 10,
                "updated_count": 12,
                "errors_count": 3,
                "pdf_filename": "stock_report_20240115_103000.pdf"
            }
        }


class XMLUploadRequest(BaseModel):
    """Request for XML file upload with provider."""
    provider: XMLProvider = Field(..., description="XML provider type")
    apply_margin: bool = Field(default=True, description="Apply profit margin")
    margin_percentage: Optional[float] = Field(None, ge=0, le=1, description="Custom margin (0-1)")
    quantity_mode: QuantityMode = Field(default=QuantityMode.REPLACE)

    class Config:
        json_schema_extra = {
            "example": {
                "provider": "D'Mujeres",
                "apply_margin": True,
                "margin_percentage": 0.50,
                "quantity_mode": "replace"
            }
        }


class XMLParseResponse(BaseModel):
    """Response from XML parsing."""
    products: List[ProductData]
    total_found: int
    provider: XMLProvider

    class Config:
        json_schema_extra = {
            "example": {
                "products": [],
                "total_found": 25,
                "provider": "D'Mujeres"
            }
        }


class InconsistencyItem(BaseModel):
    """Price or data inconsistency between principal and branch."""
    barcode: str
    product_name: str
    sucursal_id: int
    principal_list_price: float
    sucursal_list_price: float
    list_price_difference: float
    principal_standard_price: float
    sucursal_standard_price: float
    standard_price_difference: float
    principal_stock: float
    sucursal_stock: float

    class Config:
        json_schema_extra = {
            "example": {
                "barcode": "123456789",
                "product_name": "Producto A",
                "sucursal_id": 456,
                "principal_list_price": 10.00,
                "sucursal_list_price": 9.50,
                "list_price_difference": 0.50,
                "principal_standard_price": 8.00,
                "sucursal_standard_price": 7.50,
                "standard_price_difference": 0.50,
                "principal_stock": 100.0,
                "sucursal_stock": 50.0
            }
        }


class FixInconsistencyItem(BaseModel):
    """Item to fix in branch."""
    barcode: str
    sucursal_id: int
    new_name: Optional[str] = None
    new_list_price: Optional[float] = None
    new_standard_price: Optional[float] = None

    class Config:
        json_schema_extra = {
            "example": {
                "barcode": "123456789",
                "sucursal_id": 456,
                "new_name": "Producto A",
                "new_list_price": 10.00,
                "new_standard_price": 8.00
            }
        }


class InconsistencyResponse(BaseModel):
    """Response with detected inconsistencies."""
    success: bool = Field(default=True, description="Success status")
    message: Optional[str] = Field(default=None, description="Optional message")
    inconsistencies: List[InconsistencyItem]
    total_inconsistencies: int = Field(description="Total inconsistencies found")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Found 5 inconsistencies",
                "inconsistencies": [],
                "total_inconsistencies": 5
            }
        }


class SyncRequest(BaseModel):
    """Request for syncing products to Odoo."""
    products: List[dict] = Field(..., description="List of products to sync")
    profit_margin: float = Field(default=0.50, ge=0, le=1, description="Profit margin (0-1)")
    quantity_mode: str = Field(default="replace", description="Quantity mode: replace or add")

    class Config:
        json_schema_extra = {
            "example": {
                "products": [],
                "profit_margin": 0.50,
                "quantity_mode": "replace"
            }
        }
