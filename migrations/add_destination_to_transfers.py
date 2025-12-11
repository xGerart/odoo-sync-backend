"""
Migration: Add destination fields to pending_transfers table.

This migration adds the following columns to support destination tracking:
- destination_location_id: VARCHAR(50) - ID of destination location (e.g., 'sucursal', 'sucursal_sacha')
- destination_location_name: VARCHAR(100) - Human-readable name of destination location

Date: 2025-12-10
"""

from sqlalchemy import text


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
    """Add destination fields to pending_transfers table"""
    is_pg = is_postgres(engine)

    with engine.begin() as conn:
        # Check if table exists first
        if not table_exists(conn, 'pending_transfers', is_pg):
            print("⚠️  Table pending_transfers does not exist yet, skipping migration")
            print("    This migration will run automatically after the table is created")
            return

        # Check and add destination_location_id column
        if not check_column_exists(conn, 'pending_transfers', 'destination_location_id', is_pg):
            print("Adding column: destination_location_id")
            conn.execute(text(
                "ALTER TABLE pending_transfers ADD COLUMN destination_location_id VARCHAR(50)"
            ))
            print("✓ Column destination_location_id added")
        else:
            print("✓ Column destination_location_id already exists")

        # Check and add destination_location_name column
        if not check_column_exists(conn, 'pending_transfers', 'destination_location_name', is_pg):
            print("Adding column: destination_location_name")
            conn.execute(text(
                "ALTER TABLE pending_transfers ADD COLUMN destination_location_name VARCHAR(100)"
            ))
            print("✓ Column destination_location_name added")
        else:
            print("✓ Column destination_location_name already exists")

        # Commit is automatic when exiting the context manager
        print("✅ Migration add_destination_to_transfers completed successfully!")


def downgrade(engine):
    """Remove destination fields (optional)"""
    with engine.begin() as conn:
        if is_postgres(engine):
            # PostgreSQL supports DROP COLUMN
            conn.execute(text("""
                ALTER TABLE pending_transfers
                DROP COLUMN IF EXISTS destination_location_id,
                DROP COLUMN IF EXISTS destination_location_name
            """))
            print("✅ Dropped destination fields from pending_transfers")
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
