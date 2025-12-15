"""
Migration: Add LOCAL_SERVICE_USE and EXPIRED to AdjustmentReason ENUM

This migration adds two new values to the PostgreSQL adjustmentreason ENUM type:
- local_service_use: For local service use exits
- expired: For expired product exits

Date: 2025-12-15
"""

from sqlalchemy import text


def is_postgres(engine):
    """Check if database is PostgreSQL"""
    return "postgresql" in str(engine.url)


def enum_value_exists(conn, enum_name: str, value: str) -> bool:
    """Check if an enum value already exists in PostgreSQL."""
    result = conn.execute(text("""
        SELECT EXISTS (
            SELECT 1 FROM pg_enum
            WHERE enumlabel = :value
            AND enumtypid = (
                SELECT oid FROM pg_type WHERE typname = :enum_name
            )
        )
    """), {"value": value, "enum_name": enum_name})
    return result.scalar()


def upgrade(engine):
    """Add new values to adjustmentreason ENUM type"""
    is_pg = is_postgres(engine)

    # SQLite uses VARCHAR, no migration needed
    if not is_pg:
        print("✓ SQLite detected - no ENUM migration needed (uses VARCHAR)")
        return

    with engine.begin() as conn:
        print("PostgreSQL detected - adding new enum values to adjustmentreason")

        # Add 'local_service_use' if it doesn't exist
        if not enum_value_exists(conn, 'adjustmentreason', 'local_service_use'):
            print("Adding enum value: local_service_use")
            # Note: ALTER TYPE ADD VALUE cannot run inside a transaction block in some PG versions
            # We use COMMIT to ensure it's applied
            conn.execute(text(
                "ALTER TYPE adjustmentreason ADD VALUE 'local_service_use'"
            ))
            print("✓ Added 'local_service_use' to adjustmentreason enum")
        else:
            print("✓ Enum value 'local_service_use' already exists")

        # Add 'expired' if it doesn't exist
        if not enum_value_exists(conn, 'adjustmentreason', 'expired'):
            print("Adding enum value: expired")
            conn.execute(text(
                "ALTER TYPE adjustmentreason ADD VALUE 'expired'"
            ))
            print("✓ Added 'expired' to adjustmentreason enum")
        else:
            print("✓ Enum value 'expired' already exists")

        print("✅ Migration add_service_and_expiry_reasons completed successfully!")


def downgrade(engine):
    """
    Rollback not supported for PostgreSQL ENUM values.

    PostgreSQL does not support removing values from ENUM types.
    To remove these values, you would need to:
    1. Create a new ENUM type without these values
    2. Migrate all data to use the new type
    3. Drop the old ENUM type

    This is a destructive operation and should be done manually if needed.
    """
    print("⚠️  WARNING: Cannot remove values from PostgreSQL ENUM types")
    print("   PostgreSQL does not support ALTER TYPE ... DROP VALUE")
    print("   If rollback is required, manual intervention is needed:")
    print("   1. Create new ENUM type without these values")
    print("   2. Migrate data to new type")
    print("   3. Drop old ENUM type and rename new one")
    print("   This is a destructive operation - proceed with caution!")


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
