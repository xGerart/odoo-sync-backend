"""
Migration: Create adjustment_history and adjustment_history_items tables.

This migration creates comprehensive historical tracking tables for adjustments:
- adjustment_history: Main record of each executed adjustment
- adjustment_history_items: Individual product items within each adjustment

Date: 2025-12-10
"""

from sqlalchemy import text


def is_postgres(engine):
    """Check if database is PostgreSQL"""
    return "postgresql" in str(engine.url)


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


def upgrade(engine):
    """Create adjustment history tables"""
    is_pg = is_postgres(engine)

    with engine.begin() as conn:
        # Create adjustment_history table
        if not table_exists(conn, 'adjustment_history', is_pg):
            print("Creating table: adjustment_history")

            if is_pg:
                conn.execute(text("""
                    CREATE TABLE adjustment_history (
                        id SERIAL PRIMARY KEY,
                        pending_adjustment_id INTEGER REFERENCES pending_adjustments(id),

                        location VARCHAR(50) DEFAULT 'principal',
                        location_name VARCHAR(100),

                        executed_by VARCHAR(50) NOT NULL,
                        executed_at TIMESTAMP NOT NULL,

                        total_items INTEGER NOT NULL,
                        successful_items INTEGER NOT NULL,
                        failed_items INTEGER NOT NULL,
                        total_quantity_requested INTEGER NOT NULL,
                        total_quantity_adjusted INTEGER NOT NULL,

                        pdf_content TEXT,
                        pdf_filename VARCHAR(255),
                        xml_content TEXT,

                        snapshots_before TEXT,
                        snapshots_after TEXT,

                        has_errors BOOLEAN DEFAULT FALSE,
                        error_summary TEXT,

                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))

                # Create indexes for PostgreSQL
                conn.execute(text("CREATE INDEX idx_adjustment_history_pending ON adjustment_history(pending_adjustment_id)"))
                conn.execute(text("CREATE INDEX idx_adjustment_history_location ON adjustment_history(location)"))
                conn.execute(text("CREATE INDEX idx_adjustment_history_executed_by ON adjustment_history(executed_by)"))
                conn.execute(text("CREATE INDEX idx_adjustment_history_executed_at ON adjustment_history(executed_at)"))

            else:  # SQLite
                conn.execute(text("""
                    CREATE TABLE adjustment_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        pending_adjustment_id INTEGER REFERENCES pending_adjustments(id),

                        location VARCHAR(50) DEFAULT 'principal',
                        location_name VARCHAR(100),

                        executed_by VARCHAR(50) NOT NULL,
                        executed_at DATETIME NOT NULL,

                        total_items INTEGER NOT NULL,
                        successful_items INTEGER NOT NULL,
                        failed_items INTEGER NOT NULL,
                        total_quantity_requested INTEGER NOT NULL,
                        total_quantity_adjusted INTEGER NOT NULL,

                        pdf_content TEXT,
                        pdf_filename VARCHAR(255),
                        xml_content TEXT,

                        snapshots_before TEXT,
                        snapshots_after TEXT,

                        has_errors BOOLEAN DEFAULT 0,
                        error_summary TEXT,

                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """))

                # Create indexes for SQLite
                conn.execute(text("CREATE INDEX idx_adjustment_history_pending ON adjustment_history(pending_adjustment_id)"))
                conn.execute(text("CREATE INDEX idx_adjustment_history_location ON adjustment_history(location)"))
                conn.execute(text("CREATE INDEX idx_adjustment_history_executed_by ON adjustment_history(executed_by)"))
                conn.execute(text("CREATE INDEX idx_adjustment_history_executed_at ON adjustment_history(executed_at)"))

            print("✓ Table adjustment_history created")
        else:
            print("✓ Table adjustment_history already exists")

        # Create adjustment_history_items table
        if not table_exists(conn, 'adjustment_history_items', is_pg):
            print("Creating table: adjustment_history_items")

            if is_pg:
                conn.execute(text("""
                    CREATE TABLE adjustment_history_items (
                        id SERIAL PRIMARY KEY,
                        history_id INTEGER REFERENCES adjustment_history(id) NOT NULL,

                        barcode VARCHAR(100) NOT NULL,
                        product_id INTEGER NOT NULL,
                        product_name VARCHAR(255) NOT NULL,

                        quantity_requested INTEGER NOT NULL,
                        quantity_adjusted INTEGER NOT NULL,

                        adjustment_type VARCHAR(50) NOT NULL,
                        reason VARCHAR(100),

                        success BOOLEAN NOT NULL,
                        error_message TEXT,

                        stock_before INTEGER,
                        stock_after INTEGER,

                        unit_price FLOAT,
                        total_value FLOAT,

                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))

                # Create indexes for PostgreSQL
                conn.execute(text("CREATE INDEX idx_adjustment_history_items_history ON adjustment_history_items(history_id)"))
                conn.execute(text("CREATE INDEX idx_adjustment_history_items_barcode ON adjustment_history_items(barcode)"))

            else:  # SQLite
                conn.execute(text("""
                    CREATE TABLE adjustment_history_items (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        history_id INTEGER REFERENCES adjustment_history(id) NOT NULL,

                        barcode VARCHAR(100) NOT NULL,
                        product_id INTEGER NOT NULL,
                        product_name VARCHAR(255) NOT NULL,

                        quantity_requested INTEGER NOT NULL,
                        quantity_adjusted INTEGER NOT NULL,

                        adjustment_type VARCHAR(50) NOT NULL,
                        reason VARCHAR(100),

                        success BOOLEAN NOT NULL,
                        error_message TEXT,

                        stock_before INTEGER,
                        stock_after INTEGER,

                        unit_price REAL,
                        total_value REAL,

                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """))

                # Create indexes for SQLite
                conn.execute(text("CREATE INDEX idx_adjustment_history_items_history ON adjustment_history_items(history_id)"))
                conn.execute(text("CREATE INDEX idx_adjustment_history_items_barcode ON adjustment_history_items(barcode)"))

            print("✓ Table adjustment_history_items created")
        else:
            print("✓ Table adjustment_history_items already exists")

        # Commit is automatic when exiting the context manager
        print("✅ Migration create_adjustment_history_tables completed successfully!")


def downgrade(engine):
    """Drop adjustment history tables"""
    with engine.begin() as conn:
        # Drop in reverse order (items first due to foreign key)
        conn.execute(text("DROP TABLE IF EXISTS adjustment_history_items"))
        print("✓ Dropped table adjustment_history_items")

        conn.execute(text("DROP TABLE IF EXISTS adjustment_history"))
        print("✓ Dropped table adjustment_history")

        print("✅ Migration rollback completed")


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
