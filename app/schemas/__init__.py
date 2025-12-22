"""
Pydantic schemas for request/response validation.
"""
from app.schemas.common import (
    MessageResponse,
    ErrorResponse,
    PaginationParams,
    PaginatedResponse,
    OdooConfigBase,
    OdooCredentials,
    HealthResponse
)
from app.schemas.user import (
    UserBase,
    UserCreate,
    UserUpdate,
    UserResponse,
    UserListResponse
)
from app.schemas.auth import (
    LoginRequest,
    OdooLoginRequest,
    TokenResponse,
    LoginResponse,
    UserInfo,
    TokenPayload
)
from app.schemas.product import (
    ProductData,
    ProductMapped,
    ProductInput,
    ProductResponse,
    SyncResult,
    SyncResponse,
    XMLUploadRequest,
    XMLParseResponse,
    InconsistencyItem,
    InconsistencyResponse
)
from app.schemas.transfer import (
    TransferItem,
    TransferRequest,
    ConfirmTransferRequest,
    TransferProductDetail,
    TransferResponse,
    TransferValidationError,
    TransferValidationResponse
)
from app.schemas.sales import (
    SaleByEmployee,
    PaymentMethodSummary,
    POSSession,
    CierreCajaResponse,
    SalesDateRange
)
from app.schemas.adjustment import (
    AdjustmentTypeEnum,
    AdjustmentReasonEnum,
    AdjustmentItem,
    AdjustmentRequest,
    ConfirmAdjustmentRequest,
    AdjustmentResponse,
    PendingAdjustmentItemResponse,
    PendingAdjustmentResponse,
    PendingAdjustmentListResponse,
    AdjustmentHistoryItemResponse,
    AdjustmentHistoryResponse
)
from app.schemas.product_sync import (
    ProductSyncHistoryItemResponse,
    ProductSyncHistoryResponse,
    ProductSyncHistoryListResponse
)
from app.schemas.invoice import (
    InvoiceItemUpdateRequest,
    InvoiceSubmitRequest,
    InvoiceSyncRequest,
    InvoiceItemResponse,
    PendingInvoiceResponse,
    PendingInvoiceListResponse,
    InvoiceUploadResponse,
    InvoiceSyncResponse,
    InvoiceHistoryItemResponse,
    InvoiceHistoryResponse,
    InvoiceHistoryListResponse
)

__all__ = [
    # Common
    "MessageResponse",
    "ErrorResponse",
    "PaginationParams",
    "PaginatedResponse",
    "OdooConfigBase",
    "OdooCredentials",
    "HealthResponse",
    # User
    "UserBase",
    "UserCreate",
    "UserUpdate",
    "UserResponse",
    "UserListResponse",
    # Auth
    "LoginRequest",
    "OdooLoginRequest",
    "TokenResponse",
    "LoginResponse",
    "UserInfo",
    "TokenPayload",
    # Product
    "ProductData",
    "ProductMapped",
    "ProductInput",
    "ProductResponse",
    "SyncResult",
    "SyncResponse",
    "XMLUploadRequest",
    "XMLParseResponse",
    "InconsistencyItem",
    "InconsistencyResponse",
    # Transfer
    "TransferItem",
    "TransferRequest",
    "ConfirmTransferRequest",
    "TransferProductDetail",
    "TransferResponse",
    "TransferValidationError",
    "TransferValidationResponse",
    # Sales
    "SaleByEmployee",
    "PaymentMethodSummary",
    "POSSession",
    "CierreCajaResponse",
    "SalesDateRange",
    # Adjustment
    "AdjustmentTypeEnum",
    "AdjustmentReasonEnum",
    "AdjustmentItem",
    "AdjustmentRequest",
    "ConfirmAdjustmentRequest",
    "AdjustmentResponse",
    "PendingAdjustmentItemResponse",
    "PendingAdjustmentResponse",
    "PendingAdjustmentListResponse",
    "AdjustmentHistoryItemResponse",
    "AdjustmentHistoryResponse",
    # Product Sync History
    "ProductSyncHistoryItemResponse",
    "ProductSyncHistoryResponse",
    "ProductSyncHistoryListResponse",
    # Invoice
    "InvoiceItemUpdateRequest",
    "InvoiceSubmitRequest",
    "InvoiceSyncRequest",
    "InvoiceItemResponse",
    "PendingInvoiceResponse",
    "PendingInvoiceListResponse",
    "InvoiceUploadResponse",
    "InvoiceSyncResponse",
    "InvoiceHistoryItemResponse",
    "InvoiceHistoryResponse",
    "InvoiceHistoryListResponse",
]
