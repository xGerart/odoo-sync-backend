"""
Migration: Add barcode_source column to pending_invoices table.

This migration adds a column to store which XML field (codigoPrincipal or codigoAuxiliar)
was used as the barcode source when parsing the invoice.

Date: 2025-12-22
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
    """Add barcode_source column to pending_invoices"""
    is_pg = is_postgres(engine)

    with engine.begin() as conn:
        # Check if column already exists
        if not column_exists(conn, 'pending_invoices', 'barcode_source', is_pg):
            print("Adding column: barcode_source to pending_invoices")

            # Add barcode_source column
            conn.execute(text("""
                ALTER TABLE pending_invoices
                ADD COLUMN barcode_source VARCHAR(20) DEFAULT 'codigoAuxiliar'
            """))

            print("✅ Column barcode_source added successfully")
        else:
            print("⏭️  Column barcode_source already exists, skipping")
