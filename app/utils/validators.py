"""
Validation utilities for input data.
"""
import re
from typing import Optional
from pathlib import Path
from app.core.constants import (
    ALLOWED_XML_EXTENSIONS,
    ALLOWED_IMAGE_EXTENSIONS,
    PDF_HEADER
)


def validate_barcode(barcode: str) -> bool:
    """
    Validate product barcode format.

    Args:
        barcode: Barcode string

    Returns:
        True if valid
    """
    # Allow alphanumeric barcodes, 5-20 characters
    if not barcode or len(barcode) < 5 or len(barcode) > 20:
        return False

    # Must be alphanumeric (letters, numbers, hyphens)
    return bool(re.match(r'^[A-Za-z0-9\-_]+$', barcode))


def validate_xml_file(filename: str) -> tuple[bool, Optional[str]]:
    """
    Validate XML file extension.

    Args:
        filename: Filename to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    path = Path(filename)
    ext = path.suffix.lower()

    if ext not in ALLOWED_XML_EXTENSIONS:
        return False, f"Invalid file type. Allowed: {', '.join(ALLOWED_XML_EXTENSIONS)}"

    return True, None


def validate_pdf_content(content: bytes) -> bool:
    """
    Validate that content is actually a PDF file.

    Args:
        content: File content bytes

    Returns:
        True if valid PDF
    """
    if not content:
        return False

    # Check PDF header
    return content.startswith(PDF_HEADER)


def validate_pdf_filename(filename: str) -> tuple[bool, Optional[str]]:
    """
    Validate PDF filename for security (prevent path traversal).

    Args:
        filename: Filename to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    # No path traversal
    if '..' in filename or '/' in filename or '\\' in filename:
        return False, "Invalid filename: path traversal not allowed"

    # Must be PDF
    if not filename.lower().endswith('.pdf'):
        return False, "Invalid filename: must be PDF"

    # Check for allowed prefixes (reports only)
    allowed_prefixes = ['stock_report_', 'transfer_admin_report_', 'transfer_report_']
    if not any(filename.startswith(prefix) for prefix in allowed_prefixes):
        return False, f"Invalid filename: must start with {', '.join(allowed_prefixes)}"

    return True, None


def validate_quantity(quantity: float, min_value: float = 0) -> tuple[bool, Optional[str]]:
    """
    Validate quantity value.

    Args:
        quantity: Quantity to validate
        min_value: Minimum allowed value

    Returns:
        Tuple of (is_valid, error_message)
    """
    if quantity < min_value:
        return False, f"Quantity must be at least {min_value}"

    if quantity > 1_000_000:
        return False, "Quantity too large (max 1,000,000)"

    return True, None


def validate_price(price: float, min_value: float = 0.01) -> tuple[bool, Optional[str]]:
    """
    Validate price value.

    Args:
        price: Price to validate
        min_value: Minimum allowed price

    Returns:
        Tuple of (is_valid, error_message)
    """
    if price < min_value:
        return False, f"Price must be at least {min_value}"

    if price > 1_000_000:
        return False, "Price too large (max 1,000,000)"

    return True, None


def validate_email(email: str) -> bool:
    """
    Validate email format.

    Args:
        email: Email to validate

    Returns:
        True if valid email format
    """
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def validate_username(username: str) -> tuple[bool, Optional[str]]:
    """
    Validate username format.

    Args:
        username: Username to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if len(username) < 3:
        return False, "Username must be at least 3 characters"

    if len(username) > 50:
        return False, "Username must be at most 50 characters"

    # Alphanumeric, underscore, hyphen only
    if not re.match(r'^[a-zA-Z0-9_-]+$', username):
        return False, "Username can only contain letters, numbers, underscore and hyphen"

    return True, None


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to prevent security issues.

    Args:
        filename: Original filename

    Returns:
        Sanitized filename
    """
    # Remove path components
    filename = Path(filename).name

    # Remove or replace dangerous characters
    filename = re.sub(r'[^\w\-.]', '_', filename)

    # Limit length
    if len(filename) > 255:
        name, ext = filename.rsplit('.', 1) if '.' in filename else (filename, '')
        filename = name[:250] + ('.' + ext if ext else '')

    return filename


def validate_date_format(date_str: str, format: str = "%Y-%m-%d") -> tuple[bool, Optional[str]]:
    """
    Validate date string format.

    Args:
        date_str: Date string to validate
        format: Expected format (default: YYYY-MM-DD)

    Returns:
        Tuple of (is_valid, error_message)
    """
    from datetime import datetime

    try:
        datetime.strptime(date_str, format)
        return True, None
    except ValueError:
        return False, f"Invalid date format. Expected: {format}"
