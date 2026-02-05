"""
Migration: Add PARCIALMENTE_SINCRONIZADA status to invoicestatus enum

This migration adds the missing 'parcialmente_sincronizada' value to the
invoicestatus enum type in PostgreSQL.

Date: 2026-01-15
"""

from sqlalchemy import text


def is_postgres(engine):
    """Check if database is PostgreSQL"""
    return "postgresql" in str(engine.url)


def enum_type_exists(conn, type_name: str) -> bool:
    """Check if an enum type exists in PostgreSQL."""
    result = conn.execute(text("""
        SELECT EXISTS (
            SELECT 1 FROM pg_type
            WHERE typname = :type_name
        )
    """), {"type_name": type_name})
    return result.scalar()


def enum_value_exists(conn, type_name: str, value: str) -> bool:
    """Check if a value exists in a PostgreSQL enum type."""
    result = conn.execute(text("""
        SELECT EXISTS (
            SELECT 1 FROM pg_enum
            WHERE enumtypid = (SELECT oid FROM pg_type WHERE typname = :type_name)
            AND enumlabel = :value
        )
    """), {"type_name": type_name, "value": value})
    return result.scalar()


def upgrade(engine):
    """Add parcialmente_sincronizada to invoicestatus enum"""
    is_pg = is_postgres(engine)

    if not is_pg:
        print("Skipping: This migration is for PostgreSQL only (SQLite uses VARCHAR)")
        return

    with engine.begin() as conn:
        # Check if invoicestatus enum type exists
        if not enum_type_exists(conn, 'invoicestatus'):
            print("Creating invoicestatus enum type...")
            # Create the enum with all values
            conn.execute(text("""
                CREATE TYPE invoicestatus AS ENUM (
                    'pendiente_revision',
                    'en_revision',
                    'corregida',
                    'parcialmente_sincronizada',
                    'sincronizada'
                )
            """))
            print("✅ Created invoicestatus enum type")
            
            # Now we need to convert the existing VARCHAR column to use the enum
            print("Converting pending_invoices.status column to use enum...")
            conn.execute(text("""
                ALTER TABLE pending_invoices 
                ALTER COLUMN status TYPE invoicestatus 
                USING status::invoicestatus
            """))
            print("✅ Converted pending_invoices.status to enum type")
            
            # Same for invoice_history if it exists
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'invoice_history'
                )
            """))
            if result.scalar():
                print("Converting invoice_history.status column to use enum...")
                conn.execute(text("""
                    ALTER TABLE invoice_history 
                    ALTER COLUMN status TYPE invoicestatus 
                    USING status::invoicestatus
                """))
                print("✅ Converted invoice_history.status to enum type")
        else:
            # Enum already exists, check if value is present
            if enum_value_exists(conn, 'invoicestatus', 'parcialmente_sincronizada'):
                print("✓ Value 'parcialmente_sincronizada' already exists in invoicestatus enum")
            else:
                print("Adding 'parcialmente_sincronizada' to invoicestatus enum...")
                conn.execute(text("""
                    ALTER TYPE invoicestatus ADD VALUE 'parcialmente_sincronizada'
                """))
                print("✅ Added 'parcialmente_sincronizada' to invoicestatus enum")


def downgrade(engine):
    """
    Note: PostgreSQL does not support removing values from enum types.
    To remove a value, you would need to:
    1. Create a new enum without the value
    2. Convert all columns to the new enum
    3. Drop the old enum
    4. Rename the new enum
    This is complex and risky, so we don't implement a downgrade.
    """
    print("⚠️  Downgrade not supported for enum value additions in PostgreSQL")
