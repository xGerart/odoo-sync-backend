"""
Migration: Add sync configuration columns to pending_invoices table.

This migration adds columns to store sync configuration (profit_margin, apply_iva, quantity_mode)
that can be configured per invoice before syncing to Odoo.

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
    """Add sync configuration columns to pending_invoices"""
    is_pg = is_postgres(engine)

    with engine.begin() as conn:
        # Add profit_margin column
        if not column_exists(conn, 'pending_invoices', 'profit_margin', is_pg):
            print("Adding column: profit_margin to pending_invoices")
            if is_pg:
                conn.execute(text("""
                    ALTER TABLE pending_invoices
                    ADD COLUMN profit_margin DOUBLE PRECISION DEFAULT 0.5 NOT NULL
                """))
            else:
                conn.execute(text("""
                    ALTER TABLE pending_invoices
                    ADD COLUMN profit_margin REAL DEFAULT 0.5 NOT NULL
                """))
            print("✅ Column profit_margin added")
        else:
            print("⏭️  Column profit_margin already exists")

        # Add apply_iva column
        if not column_exists(conn, 'pending_invoices', 'apply_iva', is_pg):
            print("Adding column: apply_iva to pending_invoices")
            conn.execute(text("""
                ALTER TABLE pending_invoices
                ADD COLUMN apply_iva BOOLEAN DEFAULT TRUE NOT NULL
            """))
            print("✅ Column apply_iva added")
        else:
            print("⏭️  Column apply_iva already exists")

        # Add quantity_mode column
        if not column_exists(conn, 'pending_invoices', 'quantity_mode', is_pg):
            print("Adding column: quantity_mode to pending_invoices")
            conn.execute(text("""
                ALTER TABLE pending_invoices
                ADD COLUMN quantity_mode VARCHAR(10) DEFAULT 'add' NOT NULL
            """))
            print("✅ Column quantity_mode added")
        else:
            print("⏭️  Column quantity_mode already exists")

        print("✅ All sync config columns added successfully")
