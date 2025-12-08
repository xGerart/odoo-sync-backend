"""
Migration: Add verification fields to pending_transfers table.

This migration adds the following columns to support transfer verification workflow:
- created_by_role: VARCHAR(20) - Role of user who created the transfer ('admin', 'bodeguero', 'cajero')
- verified_at: DATETIME - Timestamp when transfer was verified by bodeguero
- verified_by: VARCHAR(50) - Username of bodeguero who verified the transfer

Date: 2025-12-07
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from sqlalchemy import text, inspect
from app.core.database import engine


def check_column_exists(table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table."""
    inspector = inspect(engine)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


def run_migration():
    """Execute the migration."""
    print("Starting migration: add_transfer_verification_fields")

    with engine.connect() as connection:
        # Start transaction
        trans = connection.begin()

        try:
            # Check and add created_by_role column
            if not check_column_exists('pending_transfers', 'created_by_role'):
                print("Adding column: created_by_role")
                connection.execute(text(
                    "ALTER TABLE pending_transfers ADD COLUMN created_by_role VARCHAR(20)"
                ))
                # Set default value for existing records
                connection.execute(text(
                    "UPDATE pending_transfers SET created_by_role = 'bodeguero' WHERE created_by_role IS NULL"
                ))
                print("✓ Column created_by_role added")
            else:
                print("✓ Column created_by_role already exists")

            # Check and add verified_at column
            if not check_column_exists('pending_transfers', 'verified_at'):
                print("Adding column: verified_at")
                connection.execute(text(
                    "ALTER TABLE pending_transfers ADD COLUMN verified_at DATETIME"
                ))
                print("✓ Column verified_at added")
            else:
                print("✓ Column verified_at already exists")

            # Check and add verified_by column
            if not check_column_exists('pending_transfers', 'verified_by'):
                print("Adding column: verified_by")
                connection.execute(text(
                    "ALTER TABLE pending_transfers ADD COLUMN verified_by VARCHAR(50)"
                ))
                print("✓ Column verified_by added")
            else:
                print("✓ Column verified_by already exists")

            # Commit transaction
            trans.commit()
            print("\n✅ Migration completed successfully!")

        except Exception as e:
            # Rollback on error
            trans.rollback()
            print(f"\n❌ Migration failed: {e}")
            raise


def rollback_migration():
    """Rollback the migration (remove added columns)."""
    print("Starting rollback: add_transfer_verification_fields")

    with engine.connect() as connection:
        trans = connection.begin()

        try:
            # SQLite doesn't support DROP COLUMN directly
            # In production with PostgreSQL, you would use:
            # ALTER TABLE pending_transfers DROP COLUMN column_name

            print("⚠️  Note: SQLite doesn't support DROP COLUMN.")
            print("To rollback, you need to recreate the table without these columns.")
            print("This is a destructive operation and should be done manually if needed.")

            trans.commit()

        except Exception as e:
            trans.rollback()
            print(f"\n❌ Rollback failed: {e}")
            raise


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Run database migration')
    parser.add_argument('--rollback', action='store_true', help='Rollback the migration')
    args = parser.parse_args()

    if args.rollback:
        rollback_migration()
    else:
        run_migration()
