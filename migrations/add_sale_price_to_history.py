"""
Migration: Add sale_price column to invoice_history_items table.

This migration adds a column to store the sale price that was synced to Odoo
for each item in the invoice history.

Date: 2024-12-24
"""

from sqlalchemy import text


def is_postgres(engine):
    """Check if database is PostgreSQL"""
    return "postgresql" in str(engine.url)


def column_exists(conn, table_name: str, column_name: str, is_postgres: bool) -> bool:
    """Check if a column exists in a table."""
    if is_postgres:
        result = conn.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.columns
                WHERE table_name = :table_name
                AND column_name = :column_name
            )
        """), {"table_name": table_name, "column_name": column_name})
        return result.scalar()
    else:
        result = conn.execute(text(f"PRAGMA table_info({table_name})"))
        columns = [row[1] for row in result.fetchall()]
        return column_name in columns


def upgrade(engine):
    """Add sale_price column to invoice_history_items"""
    is_pg = is_postgres(engine)

    with engine.begin() as conn:
        # Check if column already exists
        if not column_exists(conn, 'invoice_history_items', 'sale_price', is_pg):
            print("Adding column: sale_price to invoice_history_items")

            # Add sale_price column
            if is_pg:
                conn.execute(text("""
                    ALTER TABLE invoice_history_items
                    ADD COLUMN sale_price DOUBLE PRECISION NULL
                """))
            else:
                conn.execute(text("""
                    ALTER TABLE invoice_history_items
                    ADD COLUMN sale_price REAL NULL
                """))

            print("✅ Column sale_price added successfully")
        else:
            print("⏭️  Column sale_price already exists, skipping")
