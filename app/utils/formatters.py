"""
Formatting utilities for numbers, prices, and Ecuador-specific formats.
"""
import locale
from decimal import Decimal, ROUND_HALF_UP
from typing import Union
from app.core.constants import VALID_PRICE_ENDINGS, IVA_RATE


def format_decimal_for_odoo(value: Union[float, Decimal]) -> float:
    """
    Format decimal number for Odoo XML-RPC.

    Odoo expects float values with high precision to avoid rounding errors
    in IVA calculations.

    Args:
        value: Decimal or float value

    Returns:
        Float with 8 decimal precision
    """
    return round(float(value), 8)


def round_price_ecuador(price: float) -> float:
    """
    Round price to Ecuador-specific endings (.00 or .05).

    Ecuador commonly uses prices ending in .00 or .05 for cash transactions.

    Args:
        price: Original price

    Returns:
        Rounded price to nearest .00 or .05

    Examples:
        >>> round_price_ecuador(10.03)
        10.05
        >>> round_price_ecuador(10.02)
        10.00
        >>> round_price_ecuador(10.48)
        10.50
    """
    # Round to nearest 0.05
    price_decimal = Decimal(str(price))
    rounded = (price_decimal / Decimal('0.05')).quantize(
        Decimal('1'),
        rounding=ROUND_HALF_UP
    ) * Decimal('0.05')

    return float(rounded)


def round_to_half_dollar(price: float) -> float:
    """
    Round price UP to nearest 50 cents (0.50).

    Always rounds up to the next .00 or .50 ending.

    Args:
        price: Original price

    Returns:
        Rounded price to next .00 or .50

    Examples:
        >>> round_to_half_dollar(12.06)
        12.50
        >>> round_to_half_dollar(12.25)
        12.50
        >>> round_to_half_dollar(12.51)
        13.00
        >>> round_to_half_dollar(12.00)
        12.00
    """
    import math
    # Round UP to nearest 0.50
    return math.ceil(price / 0.5) * 0.5


def calculate_price_with_iva(price_without_iva: float, iva_rate: float = IVA_RATE) -> float:
    """
    Calculate price including IVA.

    Args:
        price_without_iva: Base price
        iva_rate: IVA tax rate (default: 15%)

    Returns:
        Price with IVA applied
    """
    return price_without_iva * (1 + iva_rate)


def calculate_price_without_iva(price_with_iva: float, iva_rate: float = IVA_RATE) -> float:
    """
    Calculate base price from price including IVA.

    Args:
        price_with_iva: Price including IVA
        iva_rate: IVA tax rate (default: 15%)

    Returns:
        Base price without IVA
    """
    return price_with_iva / (1 + iva_rate)


def apply_profit_margin(cost_price: float, margin: float) -> float:
    """
    Apply profit margin to cost price.

    Args:
        cost_price: Original cost
        margin: Profit margin (0-1, e.g., 0.50 for 50%)

    Returns:
        Sale price with margin applied
    """
    return cost_price * (1 + margin)


def calculate_sale_price(
    cost_price: float,
    profit_margin: float,
    include_iva: bool = False,
    round_ecuador: bool = True
) -> float:
    """
    Calculate final sale price from cost with margin and IVA.

    Args:
        cost_price: Original cost price
        profit_margin: Profit margin (0-1)
        include_iva: Whether to include IVA in final price
        round_ecuador: Whether to round to nearest 50 cents (.00 or .50)

    Returns:
        Final sale price

    Example:
        >>> calculate_sale_price(10.00, 0.50, include_iva=True, round_ecuador=True)
        17.50  # (10 * 1.5 * 1.15 = 17.25 rounded to 17.50)
    """
    # Apply margin
    price = apply_profit_margin(cost_price, profit_margin)

    # Apply IVA if requested
    if include_iva:
        price = calculate_price_with_iva(price)

    # Round to nearest 50 cents if requested
    if round_ecuador:
        price = round_to_half_dollar(price)

    return price


def format_currency_ecuador(amount: float) -> str:
    """
    Format amount as Ecuador currency (USD).

    Args:
        amount: Amount to format

    Returns:
        Formatted currency string

    Example:
        >>> format_currency_ecuador(1234.56)
        '$1,234.56'
    """
    try:
        # Try to use locale formatting
        locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
        return locale.currency(amount, grouping=True)
    except:
        # Fallback to simple formatting
        return f"${amount:,.2f}"


def parse_ecuadorian_number(value: str) -> float:
    """
    Parse Ecuador number format (dot as thousand separator, comma as decimal).

    Args:
        value: String like "1.234,56"

    Returns:
        Float value

    Example:
        >>> parse_ecuadorian_number("1.234,56")
        1234.56
    """
    # Remove thousand separators (dots)
    value = value.replace('.', '')
    # Replace decimal comma with dot
    value = value.replace(',', '.')

    return float(value)


def format_ecuadorian_number(value: float, decimals: int = 2) -> str:
    """
    Format number in Ecuador format (dot as thousand separator, comma as decimal).

    Args:
        value: Number to format
        decimals: Number of decimal places

    Returns:
        Formatted string

    Example:
        >>> format_ecuadorian_number(1234.56)
        '1.234,56'
    """
    # Format with comma as thousand separator
    formatted = f"{value:,.{decimals}f}"

    # Swap separators (comma <-> dot)
    formatted = formatted.replace(',', 'TEMP')
    formatted = formatted.replace('.', ',')
    formatted = formatted.replace('TEMP', '.')

    return formatted
