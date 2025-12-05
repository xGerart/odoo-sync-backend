"""
Business constants and enums.
Centralizes magic numbers and strings.
"""
from enum import Enum


class UserRole(str, Enum):
    """User roles in the system."""
    ADMIN = "admin"
    CAJERO = "cajero"
    BODEGUERO = "bodeguero"


class AuthSource(str, Enum):
    """Authentication source."""
    DATABASE = "database"
    ODOO = "odoo"


class QuantityMode(str, Enum):
    """Quantity update mode for products."""
    ADD = "add"
    REPLACE = "replace"


class XMLProvider(str, Enum):
    """XML invoice providers."""
    DMUJERES = "D'Mujeres"
    LANSEY = "LANSEY"
    GENERIC = "generic"


class TransferStatus(str, Enum):
    """Transfer status."""
    PREPARED = "prepared"
    CONFIRMED = "confirmed"
    FAILED = "failed"


# Odoo model names
class OdooModel:
    """Odoo model names."""
    PRODUCT_PRODUCT = "product.product"
    PRODUCT_TEMPLATE = "product.template"
    STOCK_QUANT = "stock.quant"
    STOCK_LOCATION = "stock.location"
    STOCK_MOVE = "stock.move"
    POS_ORDER = "pos.order"
    POS_PAYMENT = "pos.payment"
    POS_SESSION = "pos.session"
    RES_USERS = "res.users"
    RES_GROUPS = "res.groups"


# File validation
ALLOWED_XML_EXTENSIONS = {".xml"}
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
PDF_HEADER = b"%PDF-"

# Price rounding (Ecuador specific)
VALID_PRICE_ENDINGS = {0.00, 0.05}

# Default employee names (for sales reports)
DEFAULT_EMPLOYEES = [
    "SILVIA CHICAIZA",
    "KATHERINE YUMISACA",
    "Administrador"
]

# Payment methods
PAYMENT_METHODS = {
    "cash": "Efectivo",
    "transfer": "Transferencia",
    "datafast": "Datafast"
}

# Transfer limits
MAX_TRANSFER_PERCENTAGE = 0.50  # 50% max per product

# Tax rates
IVA_RATE = 0.15  # 15% IVA Ecuador

# Default profit margins
DEFAULT_MARGIN = 0.50  # 50% profit margin

# Price tolerance for inconsistency detection
PRICE_TOLERANCE = 0.01  # $0.01 difference

# Pagination defaults
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 1000

# Token expiration
ACCESS_TOKEN_EXPIRE_MINUTES = 1440  # 24 hours
REFRESH_TOKEN_EXPIRE_DAYS = 30

# Password requirements
MIN_PASSWORD_LENGTH = 8
REQUIRE_UPPERCASE = True
REQUIRE_LOWERCASE = True
REQUIRE_DIGIT = True
REQUIRE_SPECIAL = False
