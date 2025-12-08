"""
Migration: Add verification fields to pending_transfers table.

This migration adds the following columns to support transfer verification workflow:
- created_by_role: VARCHAR(20) - Role of user who created the transfer ('admin', 'bodeguero', 'cajero')
- verified_at: TIMESTAMP - Timestamp when transfer was verified by bodeguero
- verified_by: VARCHAR(50) - Username of bodeguero who verified the transfer

Date: 2025-12-07
"""

from sqlalchemy import text, inspect


def is_postgres(engine):
    """Check if database is PostgreSQL"""
    return "postgresql" in str(engine.url)


def is_sqlite(engine):
    """Check if database is SQLite"""
    return "sqlite" in str(engine.url)


def table_exists(conn, table_name: str, is_postgres: bool) -> bool:
    """Check if a table exists."""
    if is_postgres:
        result = conn.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = :table_name
            )
        """), {"table_name": table_name})
        return result.scalar()
    else:
        result = conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=:table_name"
        ), {"table_name": table_name})
        return result.fetchone() is not None


def check_column_exists(conn, table_name: str, column_name: str, is_postgres: bool) -> bool:
    """Check if a column exists in a table using the provided connection."""
    if is_postgres:
        # PostgreSQL: query information_schema
        result = conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = :table_name AND column_name = :column_name
        """), {"table_name": table_name, "column_name": column_name})
        return result.fetchone() is not None
    else:
        # SQLite: use PRAGMA
        result = conn.execute(text(f"PRAGMA table_info({table_name})"))
        columns = [row[1] for row in result.fetchall()]
        return column_name in columns


def upgrade(engine):
    """Add verification fields to pending_transfers table"""
    is_pg = is_postgres(engine)

    with engine.begin() as conn:
        # Check if table exists first
        if not table_exists(conn, 'pending_transfers', is_pg):
            print("⚠️  Table pending_transfers does not exist yet, skipping migration")
            print("    This migration will run automatically after the table is created")
            return

        # Check and add created_by_role column
        if not check_column_exists(conn, 'pending_transfers', 'created_by_role', is_pg):
            print("Adding column: created_by_role")
            conn.execute(text(
                "ALTER TABLE pending_transfers ADD COLUMN created_by_role VARCHAR(20)"
            ))
            # Set default value for existing records
            conn.execute(text(
                "UPDATE pending_transfers SET created_by_role = 'bodeguero' WHERE created_by_role IS NULL"
            ))
            print("✓ Column created_by_role added")
        else:
            print("✓ Column created_by_role already exists")

        # Check and add verified_at column
        if not check_column_exists(conn, 'pending_transfers', 'verified_at', is_pg):
            print("Adding column: verified_at")
            if is_pg:
                conn.execute(text(
                    "ALTER TABLE pending_transfers ADD COLUMN verified_at TIMESTAMP"
                ))
            else:  # SQLite
                conn.execute(text(
                    "ALTER TABLE pending_transfers ADD COLUMN verified_at DATETIME"
                ))
            print("✓ Column verified_at added")
        else:
            print("✓ Column verified_at already exists")

        # Check and add verified_by column
        if not check_column_exists(conn, 'pending_transfers', 'verified_by', is_pg):
            print("Adding column: verified_by")
            conn.execute(text(
                "ALTER TABLE pending_transfers ADD COLUMN verified_by VARCHAR(50)"
            ))
            print("✓ Column verified_by added")
        else:
            print("✓ Column verified_by already exists")

        # Commit is automatic when exiting the context manager
        print("✅ Migration add_transfer_verification_fields completed successfully!")


def downgrade(engine):
    """Remove verification fields (optional)"""
    with engine.begin() as conn:
        if is_postgres(engine):
            # PostgreSQL supports DROP COLUMN
            conn.execute(text("""
                ALTER TABLE pending_transfers
                DROP COLUMN IF EXISTS created_by_role,
                DROP COLUMN IF EXISTS verified_at,
                DROP COLUMN IF EXISTS verified_by
            """))
            print("✅ Dropped verification fields from pending_transfers")
        else:
            # SQLite doesn't support DROP COLUMN easily
            print("⚠️  Note: SQLite doesn't support DROP COLUMN.")
            print("To rollback, you need to recreate the table without these columns.")
            print("This is a destructive operation and should be done manually if needed.")


# Support for running directly as a script
if __name__ == "__main__":
    import argparse
    import sys
    from pathlib import Path

    # Add parent directory to path for imports
    sys.path.append(str(Path(__file__).parent.parent))
    from app.core.database import engine

    parser = argparse.ArgumentParser(description='Run database migration')
    parser.add_argument('--rollback', action='store_true', help='Rollback the migration')
    args = parser.parse_args()

    if args.rollback:
        downgrade(engine)
    else:
        upgrade(engine)
