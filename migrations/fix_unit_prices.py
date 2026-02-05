"""
Migration: Fix incorrect unit prices in pending_invoice_items and invoice_history_items.

Some XML files contain incorrect precioUnitario values. The correct unit price
should be calculated as: total_price / quantity.

This migration fixes existing records where the unit_price differs significantly
from the calculated value (difference > 0.01).

Example case:
- XML precioUnitario: 5.94 (INCORRECT - double the actual price)
- XML precioTotalSinImpuesto: 89.10 (CORRECT)
- XML cantidad: 30
- Correct unit price: 89.10 / 30 = 2.97

Date: 2025-02-04
"""

from sqlalchemy import text


def is_postgres(engine):
    """Check if database is PostgreSQL"""
    return "postgresql" in str(engine.url)


def upgrade(engine):
    """Fix unit prices by recalculating from total_price / quantity"""
    is_pg = is_postgres(engine)

    with engine.begin() as conn:
        # Fix pending_invoice_items
        print("Fixing unit prices in pending_invoice_items...")

        if is_pg:
            # PostgreSQL syntax
            result = conn.execute(text("""
                UPDATE pending_invoice_items
                SET unit_price = total_price / quantity
                WHERE total_price IS NOT NULL
                  AND quantity > 0
                  AND unit_price IS NOT NULL
                  AND ABS(total_price / quantity - unit_price) > 0.01
            """))
        else:
            # SQLite syntax
            result = conn.execute(text("""
                UPDATE pending_invoice_items
                SET unit_price = total_price / quantity
                WHERE total_price IS NOT NULL
                  AND quantity > 0
                  AND unit_price IS NOT NULL
                  AND ABS(total_price / quantity - unit_price) > 0.01
            """))

        print(f"✅ Fixed {result.rowcount} rows in pending_invoice_items")

        # Fix invoice_history_items
        print("Fixing unit prices in invoice_history_items...")

        if is_pg:
            # PostgreSQL syntax
            result = conn.execute(text("""
                UPDATE invoice_history_items
                SET unit_price = total_value / quantity
                WHERE total_value IS NOT NULL
                  AND quantity > 0
                  AND unit_price IS NOT NULL
                  AND ABS(total_value / quantity - unit_price) > 0.01
            """))
        else:
            # SQLite syntax
            result = conn.execute(text("""
                UPDATE invoice_history_items
                SET unit_price = total_value / quantity
                WHERE total_value IS NOT NULL
                  AND quantity > 0
                  AND unit_price IS NOT NULL
                  AND ABS(total_value / quantity - unit_price) > 0.01
            """))

        print(f"✅ Fixed {result.rowcount} rows in invoice_history_items")

        print("\n✅ Migration completed successfully")
