"""
Migration: Add is_excluded and excluded_reason columns to pending_invoice_items.

Allows admin to exclude items from sync (e.g., "TRANSPORTE", services, discounts).

Date: 2025-02-04
"""

from sqlalchemy import text


def is_postgres(engine):
    """Check if database is PostgreSQL"""
    return "postgresql" in str(engine.url)


def column_exists(conn, table_name: str, column_name: str, is_pg: bool) -> bool:
    """Check if a column exists in a table."""
    if is_pg:
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
    """Add is_excluded and excluded_reason columns to pending_invoice_items"""
    is_pg = is_postgres(engine)

    with engine.begin() as conn:
        # Add is_excluded column
        if not column_exists(conn, 'pending_invoice_items', 'is_excluded', is_pg):
            print("Adding column: is_excluded to pending_invoice_items")

            if is_pg:
                conn.execute(text("""
                    ALTER TABLE pending_invoice_items
                    ADD COLUMN is_excluded BOOLEAN DEFAULT FALSE NOT NULL
                """))
            else:
                conn.execute(text("""
                    ALTER TABLE pending_invoice_items
                    ADD COLUMN is_excluded BOOLEAN DEFAULT 0 NOT NULL
                """))

            print("  Column is_excluded added successfully")
        else:
            print("  Column is_excluded already exists, skipping")

        # Add excluded_reason column
        if not column_exists(conn, 'pending_invoice_items', 'excluded_reason', is_pg):
            print("Adding column: excluded_reason to pending_invoice_items")

            conn.execute(text("""
                ALTER TABLE pending_invoice_items
                ADD COLUMN excluded_reason VARCHAR(255) NULL
            """))

            print("  Column excluded_reason added successfully")
        else:
            print("  Column excluded_reason already exists, skipping")

        print("\nMigration completed successfully")
