"""
Timezone utilities for Ecuador (UTC-5).
"""
from datetime import datetime, timedelta, date
from typing import Optional
import pytz
from app.core.config import settings


# Ecuador timezone
ECUADOR_TZ = pytz.timezone(settings.ECUADOR_TIMEZONE)
UTC_TZ = pytz.UTC


def get_ecuador_now() -> datetime:
    """
    Get current datetime in Ecuador timezone.

    Returns:
        Current datetime in Ecuador
    """
    return datetime.now(ECUADOR_TZ)


def utc_to_ecuador(dt: datetime) -> datetime:
    """
    Convert UTC datetime to Ecuador timezone.

    Args:
        dt: UTC datetime

    Returns:
        Datetime in Ecuador timezone
    """
    if dt.tzinfo is None:
        dt = UTC_TZ.localize(dt)

    return dt.astimezone(ECUADOR_TZ)


def ecuador_to_utc(dt: datetime) -> datetime:
    """
    Convert Ecuador datetime to UTC.

    Args:
        dt: Ecuador datetime

    Returns:
        Datetime in UTC
    """
    if dt.tzinfo is None:
        dt = ECUADOR_TZ.localize(dt)

    return dt.astimezone(UTC_TZ)


def get_date_range_ecuador(date_str: str) -> tuple[datetime, datetime]:
    """
    Get start and end datetime for a date in Ecuador timezone.

    Args:
        date_str: Date string in format YYYY-MM-DD

    Returns:
        Tuple of (start_datetime, end_datetime) in UTC

    Example:
        >>> get_date_range_ecuador("2024-01-15")
        (datetime(2024-01-15 00:00:00 UTC-5), datetime(2024-01-15 23:59:59 UTC-5))
    """
    # Parse date
    target_date = datetime.strptime(date_str, "%Y-%m-%d").date()

    # Create start of day in Ecuador timezone
    start_dt = ECUADOR_TZ.localize(
        datetime.combine(target_date, datetime.min.time())
    )

    # Create end of day in Ecuador timezone
    end_dt = ECUADOR_TZ.localize(
        datetime.combine(target_date, datetime.max.time())
    )

    # Convert to UTC for Odoo queries
    start_utc = start_dt.astimezone(UTC_TZ)
    end_utc = end_dt.astimezone(UTC_TZ)

    return start_utc, end_utc


def format_datetime_ecuador(dt: datetime, format: str = "%Y-%m-%d %H:%M:%S") -> str:
    """
    Format datetime in Ecuador timezone.

    Args:
        dt: Datetime to format
        format: Format string

    Returns:
        Formatted datetime string
    """
    if dt.tzinfo is None:
        dt = UTC_TZ.localize(dt)

    ecuador_dt = dt.astimezone(ECUADOR_TZ)
    return ecuador_dt.strftime(format)


def parse_odoo_datetime(odoo_datetime: str) -> datetime:
    """
    Parse Odoo datetime string (UTC) to Ecuador timezone.

    Odoo stores datetimes in UTC format: "2024-01-15 10:30:00"

    Args:
        odoo_datetime: Odoo datetime string

    Returns:
        Datetime in Ecuador timezone
    """
    # Parse UTC datetime
    dt = datetime.strptime(odoo_datetime, "%Y-%m-%d %H:%M:%S")
    dt = UTC_TZ.localize(dt)

    # Convert to Ecuador timezone
    return dt.astimezone(ECUADOR_TZ)


def get_time_only_ecuador(dt: datetime) -> str:
    """
    Get only time part of datetime in Ecuador timezone.

    Args:
        dt: Datetime

    Returns:
        Time string in format HH:MM:SS
    """
    ecuador_dt = utc_to_ecuador(dt) if dt.tzinfo else ECUADOR_TZ.localize(dt)
    return ecuador_dt.strftime("%H:%M:%S")


def get_date_only_ecuador(dt: datetime) -> str:
    """
    Get only date part of datetime in Ecuador timezone.

    Args:
        dt: Datetime

    Returns:
        Date string in format YYYY-MM-DD
    """
    ecuador_dt = utc_to_ecuador(dt) if dt.tzinfo else ECUADOR_TZ.localize(dt)
    return ecuador_dt.strftime("%Y-%m-%d")


def is_same_date_ecuador(dt1: datetime, dt2: datetime) -> bool:
    """
    Check if two datetimes are on the same date in Ecuador timezone.

    Args:
        dt1: First datetime
        dt2: Second datetime

    Returns:
        True if same date in Ecuador
    """
    date1 = get_date_only_ecuador(dt1)
    date2 = get_date_only_ecuador(dt2)
    return date1 == date2


def get_today_ecuador() -> str:
    """
    Get today's date in Ecuador timezone.

    Returns:
        Date string in format YYYY-MM-DD
    """
    return get_ecuador_now().strftime("%Y-%m-%d")


def get_yesterday_ecuador() -> str:
    """
    Get yesterday's date in Ecuador timezone.

    Returns:
        Date string in format YYYY-MM-DD
    """
    yesterday = get_ecuador_now() - timedelta(days=1)
    return yesterday.strftime("%Y-%m-%d")
