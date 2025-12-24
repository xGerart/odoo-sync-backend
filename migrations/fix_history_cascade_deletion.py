"""
Migration: Fix cascade deletion for invoice history.

This migration changes the foreign key constraint on invoice_history.pending_invoice_id
from CASCADE to SET NULL, ensuring history is preserved when pending invoices are deleted.

Date: 2024-12-24
"""

from sqlalchemy import text


def is_postgres(engine):
    """Check if database is PostgreSQL"""
    return "postgresql" in str(engine.url)


def upgrade(engine):
    """Fix foreign key constraint to preserve history on delete"""
    is_pg = is_postgres(engine)

    with engine.begin() as conn:
        if is_pg:
            print("Fixing foreign key constraint for PostgreSQL...")

            # Drop existing constraint
            conn.execute(text("""
                ALTER TABLE invoice_history
                DROP CONSTRAINT IF EXISTS invoice_history_pending_invoice_id_fkey
            """))

            # Add new constraint with ON DELETE SET NULL
            conn.execute(text("""
                ALTER TABLE invoice_history
                ADD CONSTRAINT invoice_history_pending_invoice_id_fkey
                FOREIGN KEY (pending_invoice_id)
                REFERENCES pending_invoices(id)
                ON DELETE SET NULL
            """))

            print("✅ Foreign key constraint updated successfully")
        else:
            print("⚠️  SQLite foreign key modification not supported in migrations")
            print("⚠️  Manual migration required - see alembic/versions/004_fix_history_cascade.sql")
            print("✅ Skipping for SQLite")
