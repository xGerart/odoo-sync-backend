from pydantic import BaseModel, field_validator
from typing import Optional, List, Any, Dict


class OdooConfig(BaseModel):
    url: str
    database: str
    username: str
    password: str
    verify_ssl: bool = True  # Allow disabling SSL verification for development


class ProductData(BaseModel):
    descripcion: str
    cantidad: float
    codigo_auxiliar: Optional[str] = None
    precio_unitario: float


class ProductMapped(BaseModel):
    name: str
    qty_available: float
    barcode: str
    standard_price: float
    list_price: float  # Sale price (without IVA for Odoo)
    display_price: Optional[float] = None  # Sale price with IVA for display
    type: str = 'storable'
    tracking: str = 'none'  # 'none' = track by quantity only (like sucursal products), 'lot' = track by lots/serial
    available_in_pos: bool = True
    quantity_mode: str = 'replace'  # 'replace' or 'add' for stock quantity updates


class ProductInput(BaseModel):
    name: str
    qty_available: float
    barcode: str
    standard_price: float
    list_price: float  # Sale price (without IVA for Odoo)
    display_price: Optional[float] = None  # Sale price with IVA for display
    quantity_mode: str = 'replace'  # 'replace' or 'add'


class SyncResult(BaseModel):
    success: bool
    message: str
    product_id: Optional[int] = None
    action: str  # 'created', 'updated', 'error'
    product_name: Optional[str] = None  # Product name for better identification
    barcode: Optional[str] = None  # Product barcode for reference
    error_details: Optional[str] = None  # Additional error details for debugging


class SyncResponse(BaseModel):
    results: List[SyncResult]
    total_processed: int
    created_count: int
    updated_count: int
    errors_count: int
    pdf_filename: Optional[str] = None


class XMLParseResponse(BaseModel):
    products: List[ProductData]
    total_found: int


class OdooConnectionTest(BaseModel):
    success: bool
    message: str
    user_id: Optional[int] = None


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None


class SaleByEmployee(BaseModel):
    employee_name: str
    payment_method: str
    total_amount: float
    transaction_count: int
    first_sale_time: Optional[str] = None  # Time of first sale (apertura)


class PaymentMethodSummary(BaseModel):
    method: str
    total: float
    count: int


class POSSession(BaseModel):
    id: int
    name: str
    state: str  # 'opening_control', 'opened', 'closing_control', 'closed'
    user_id: int
    user_name: str
    start_at: Optional[str] = None
    stop_at: Optional[str] = None
    config_id: int
    config_name: str
    cash_register_balance_start: float = 0.0
    cash_register_balance_end_real: Optional[float] = None

    @field_validator('start_at', 'stop_at', mode='before')
    @classmethod
    def validate_datetime_fields(cls, v):
        # Odoo returns False instead of None for empty datetime fields
        if v is False:
            return None
        return v

    @field_validator('cash_register_balance_end_real', mode='before')
    @classmethod
    def validate_balance_end(cls, v):
        # Odoo returns False instead of None for empty float fields
        if v is False:
            return None
        return v


class CierreCajaResponse(BaseModel):
    date: str
    total_sales: float
    sales_by_employee: List[SaleByEmployee]
    payment_methods: List[PaymentMethodSummary]
    first_sale_time: Optional[str] = None  # Time of first sale of the day (apertura general)
    last_sale_time: Optional[str] = None   # Time of last sale of the day
    pos_sessions: List[POSSession] = []    # Active POS sessions


class TransferItem(BaseModel):
    barcode: str
    quantity: int


class TransferRequest(BaseModel):
    products: List[TransferItem]


class ConfirmTransferRequest(BaseModel):
    products: List[TransferItem]  # Final confirmed list (may be adjusted)


class TransferResponse(BaseModel):
    success: bool
    message: str
    xml_content: Optional[str] = None
    pdf_content: Optional[str] = None  # Base64 encoded PDF
    pdf_filename: Optional[str] = None  # PDF filename for download
    processed_count: int = 0
    inventory_reduced: bool = False


class PriceInconsistency(BaseModel):
    """Model for price inconsistency between principal and branch"""
    barcode: str
    product_name: str
    principal_id: int
    sucursal_id: int
    principal_list_price: float
    sucursal_list_price: float
    principal_standard_price: float
    sucursal_standard_price: float
    list_price_difference: float
    standard_price_difference: float
    principal_stock: float
    sucursal_stock: float


class InconsistenciesResponse(BaseModel):
    """Response model for inconsistencies detection"""
    success: bool
    message: str
    total_inconsistencies: int
    inconsistencies: List[PriceInconsistency]


class FixInconsistencyItem(BaseModel):
    """Model for a single inconsistency fix request"""
    barcode: str
    sucursal_id: int
    new_name: Optional[str] = None  # New name from principal
    new_list_price: Optional[float] = None  # New sale price from principal
    new_standard_price: Optional[float] = None  # New cost price from principal


class FixInconsistenciesRequest(BaseModel):
    """Request model for fixing multiple inconsistencies"""
    items: List[FixInconsistencyItem]


class FixInconsistenciesResponse(BaseModel):
    """Response model for fixing inconsistencies"""
    success: bool
    message: str
    total_processed: int
    fixed_count: int
    errors_count: int
    results: List[SyncResult]