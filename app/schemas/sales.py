"""
Sales and cash register schemas.
"""
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class SaleByEmployee(BaseModel):
    """Sales summary by employee and payment method."""
    employee_name: str
    payment_method: str
    total_amount: float
    transaction_count: int
    first_sale_time: Optional[str] = Field(None, description="Time of first sale (apertura)")

    class Config:
        json_schema_extra = {
            "example": {
                "employee_name": "SILVIA CHICAIZA",
                "payment_method": "Efectivo",
                "total_amount": 150.75,
                "transaction_count": 12,
                "first_sale_time": "08:30:00"
            }
        }


class PaymentMethodSummary(BaseModel):
    """Payment method summary."""
    method: str
    total: float
    count: int

    class Config:
        json_schema_extra = {
            "example": {
                "method": "Efectivo",
                "total": 450.50,
                "count": 35
            }
        }


class POSSession(BaseModel):
    """Point of Sale session information."""
    id: int
    name: str
    state: str = Field(..., description="Session state: opened, closed, etc.")
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
        """Handle Odoo False values for datetime fields."""
        if v is False:
            return None
        return v

    @field_validator('cash_register_balance_end_real', mode='before')
    @classmethod
    def validate_balance_end(cls, v):
        """Handle Odoo False values for float fields."""
        if v is False:
            return None
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "id": 1,
                "name": "POS/2024/0001",
                "state": "opened",
                "user_id": 2,
                "user_name": "Juan Pérez",
                "start_at": "2024-01-15T08:00:00",
                "stop_at": None,
                "config_id": 1,
                "config_name": "Main POS",
                "cash_register_balance_start": 100.00,
                "cash_register_balance_end_real": None
            }
        }


class CierreCajaResponse(BaseModel):
    """Cash register closing report response."""
    date: str = Field(..., description="Date of the report (YYYY-MM-DD)")
    total_sales: float
    sales_by_employee: List[SaleByEmployee]
    payment_methods: List[PaymentMethodSummary]
    first_sale_time: Optional[str] = Field(None, description="Time of first sale (apertura general)")
    last_sale_time: Optional[str] = Field(None, description="Time of last sale")
    pos_sessions: List[POSSession] = Field(default_factory=list, description="Active POS sessions")

    class Config:
        json_schema_extra = {
            "example": {
                "date": "2024-01-15",
                "total_sales": 1250.75,
                "sales_by_employee": [],
                "payment_methods": [],
                "first_sale_time": "08:30:00",
                "last_sale_time": "18:45:00",
                "pos_sessions": []
            }
        }


class SalesDateRange(BaseModel):
    """Date range for sales queries."""
    start_date: str = Field(..., description="Start date (YYYY-MM-DD)")
    end_date: Optional[str] = Field(None, description="End date (YYYY-MM-DD), defaults to start_date")

    class Config:
        json_schema_extra = {
            "example": {
                "start_date": "2024-01-15",
                "end_date": "2024-01-15"
            }
        }
