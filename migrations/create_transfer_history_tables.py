"""
Migration: Create transfer_history and transfer_history_items tables.

This migration creates comprehensive historical tracking tables for transfers:
- transfer_history: Main record of each executed transfer
- transfer_history_items: Individual product items within each transfer

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
    """Create transfer history tables"""
    is_pg = is_postgres(engine)

    with engine.begin() as conn:
        # Create transfer_history table
        if not table_exists(conn, 'transfer_history', is_pg):
            print("Creating table: transfer_history")

            if is_pg:
                conn.execute(text("""
                    CREATE TABLE transfer_history (
                        id SERIAL PRIMARY KEY,
                        pending_transfer_id INTEGER REFERENCES pending_transfers(id),

                        origin_location VARCHAR(50) DEFAULT 'principal',
                        destination_location_id VARCHAR(50) NOT NULL,
                        destination_location_name VARCHAR(100) NOT NULL,

                        executed_by VARCHAR(50) NOT NULL,
                        executed_at TIMESTAMP NOT NULL,

                        total_items INTEGER NOT NULL,
                        successful_items INTEGER NOT NULL,
                        failed_items INTEGER NOT NULL,
                        total_quantity_requested INTEGER NOT NULL,
                        total_quantity_transferred INTEGER NOT NULL,

                        pdf_content TEXT,
                        pdf_filename VARCHAR(255),
                        xml_content TEXT,

                        origin_snapshots_before TEXT,
                        origin_snapshots_after TEXT,
                        destination_snapshots_before TEXT,
                        destination_snapshots_after TEXT,
                        new_products TEXT,

                        has_errors BOOLEAN DEFAULT FALSE,
                        error_summary TEXT,

                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))

                # Create indexes for PostgreSQL
                conn.execute(text("CREATE INDEX idx_transfer_history_pending ON transfer_history(pending_transfer_id)"))
                conn.execute(text("CREATE INDEX idx_transfer_history_destination ON transfer_history(destination_location_id)"))
                conn.execute(text("CREATE INDEX idx_transfer_history_executed_by ON transfer_history(executed_by)"))
                conn.execute(text("CREATE INDEX idx_transfer_history_executed_at ON transfer_history(executed_at)"))

            else:  # SQLite
                conn.execute(text("""
                    CREATE TABLE transfer_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        pending_transfer_id INTEGER REFERENCES pending_transfers(id),

                        origin_location VARCHAR(50) DEFAULT 'principal',
                        destination_location_id VARCHAR(50) NOT NULL,
                        destination_location_name VARCHAR(100) NOT NULL,

                        executed_by VARCHAR(50) NOT NULL,
                        executed_at DATETIME NOT NULL,

                        total_items INTEGER NOT NULL,
                        successful_items INTEGER NOT NULL,
                        failed_items INTEGER NOT NULL,
                        total_quantity_requested INTEGER NOT NULL,
                        total_quantity_transferred INTEGER NOT NULL,

                        pdf_content TEXT,
                        pdf_filename VARCHAR(255),
                        xml_content TEXT,

                        origin_snapshots_before TEXT,
                        origin_snapshots_after TEXT,
                        destination_snapshots_before TEXT,
                        destination_snapshots_after TEXT,
                        new_products TEXT,

                        has_errors BOOLEAN DEFAULT 0,
                        error_summary TEXT,

                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """))

                # Create indexes for SQLite
                conn.execute(text("CREATE INDEX idx_transfer_history_pending ON transfer_history(pending_transfer_id)"))
                conn.execute(text("CREATE INDEX idx_transfer_history_destination ON transfer_history(destination_location_id)"))
                conn.execute(text("CREATE INDEX idx_transfer_history_executed_by ON transfer_history(executed_by)"))
                conn.execute(text("CREATE INDEX idx_transfer_history_executed_at ON transfer_history(executed_at)"))

            print("✓ Table transfer_history created")
        else:
            print("✓ Table transfer_history already exists")

        # Create transfer_history_items table
        if not table_exists(conn, 'transfer_history_items', is_pg):
            print("Creating table: transfer_history_items")

            if is_pg:
                conn.execute(text("""
                    CREATE TABLE transfer_history_items (
                        id SERIAL PRIMARY KEY,
                        history_id INTEGER REFERENCES transfer_history(id) NOT NULL,

                        barcode VARCHAR(100) NOT NULL,
                        product_id INTEGER NOT NULL,
                        product_name VARCHAR(255) NOT NULL,

                        quantity_requested INTEGER NOT NULL,
                        quantity_transferred INTEGER NOT NULL,

                        success BOOLEAN NOT NULL,
                        error_message TEXT,

                        stock_origin_before INTEGER,
                        stock_origin_after INTEGER,
                        stock_destination_before INTEGER,
                        stock_destination_after INTEGER,

                        unit_price FLOAT,
                        total_value FLOAT,

                        is_new_product BOOLEAN DEFAULT FALSE,

                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))

                # Create indexes for PostgreSQL
                conn.execute(text("CREATE INDEX idx_transfer_history_items_history ON transfer_history_items(history_id)"))
                conn.execute(text("CREATE INDEX idx_transfer_history_items_barcode ON transfer_history_items(barcode)"))

            else:  # SQLite
                conn.execute(text("""
                    CREATE TABLE transfer_history_items (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        history_id INTEGER REFERENCES transfer_history(id) NOT NULL,

                        barcode VARCHAR(100) NOT NULL,
                        product_id INTEGER NOT NULL,
                        product_name VARCHAR(255) NOT NULL,

                        quantity_requested INTEGER NOT NULL,
                        quantity_transferred INTEGER NOT NULL,

                        success BOOLEAN NOT NULL,
                        error_message TEXT,

                        stock_origin_before INTEGER,
                        stock_origin_after INTEGER,
                        stock_destination_before INTEGER,
                        stock_destination_after INTEGER,

                        unit_price REAL,
                        total_value REAL,

                        is_new_product BOOLEAN DEFAULT 0,

                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """))

                # Create indexes for SQLite
                conn.execute(text("CREATE INDEX idx_transfer_history_items_history ON transfer_history_items(history_id)"))
                conn.execute(text("CREATE INDEX idx_transfer_history_items_barcode ON transfer_history_items(barcode)"))

            print("✓ Table transfer_history_items created")
        else:
            print("✓ Table transfer_history_items already exists")

        # Commit is automatic when exiting the context manager
        print("✅ Migration create_transfer_history_tables completed successfully!")


def downgrade(engine):
    """Drop transfer history tables"""
    with engine.begin() as conn:
        # Drop in reverse order (items first due to foreign key)
        conn.execute(text("DROP TABLE IF EXISTS transfer_history_items"))
        print("✓ Dropped table transfer_history_items")

        conn.execute(text("DROP TABLE IF EXISTS transfer_history"))
        print("✓ Dropped table transfer_history")

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
