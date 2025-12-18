"""
Migration: Create product_sync_history and product_sync_history_items tables.

This migration creates comprehensive historical tracking tables for product synchronizations:
- product_sync_history: Main record of each XML sync execution
- product_sync_history_items: Individual product items within each sync

Date: 2025-12-17
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
    """Create product sync history tables"""
    is_pg = is_postgres(engine)

    with engine.begin() as conn:
        # Create product_sync_history table
        if not table_exists(conn, 'product_sync_history', is_pg):
            print("Creating table: product_sync_history")

            if is_pg:
                conn.execute(text("""
                    CREATE TABLE product_sync_history (
                        id SERIAL PRIMARY KEY,

                        xml_filename VARCHAR(255) NOT NULL,
                        xml_provider VARCHAR(50) NOT NULL,

                        profit_margin FLOAT,
                        quantity_mode VARCHAR(10) NOT NULL,
                        apply_iva BOOLEAN DEFAULT TRUE,

                        executed_by VARCHAR(50) NOT NULL,
                        executed_at TIMESTAMP NOT NULL,

                        total_items INTEGER NOT NULL,
                        successful_items INTEGER NOT NULL,
                        failed_items INTEGER NOT NULL,
                        created_count INTEGER NOT NULL,
                        updated_count INTEGER NOT NULL,

                        pdf_content TEXT,
                        pdf_filename VARCHAR(255),
                        xml_content TEXT,

                        has_errors BOOLEAN DEFAULT FALSE,
                        error_summary TEXT,

                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))

                # Create indexes for PostgreSQL
                conn.execute(text("CREATE INDEX idx_product_sync_history_executed_by ON product_sync_history(executed_by)"))
                conn.execute(text("CREATE INDEX idx_product_sync_history_executed_at ON product_sync_history(executed_at)"))
                conn.execute(text("CREATE INDEX idx_product_sync_history_provider ON product_sync_history(xml_provider)"))

            else:  # SQLite
                conn.execute(text("""
                    CREATE TABLE product_sync_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,

                        xml_filename VARCHAR(255) NOT NULL,
                        xml_provider VARCHAR(50) NOT NULL,

                        profit_margin REAL,
                        quantity_mode VARCHAR(10) NOT NULL,
                        apply_iva BOOLEAN DEFAULT 1,

                        executed_by VARCHAR(50) NOT NULL,
                        executed_at DATETIME NOT NULL,

                        total_items INTEGER NOT NULL,
                        successful_items INTEGER NOT NULL,
                        failed_items INTEGER NOT NULL,
                        created_count INTEGER NOT NULL,
                        updated_count INTEGER NOT NULL,

                        pdf_content TEXT,
                        pdf_filename VARCHAR(255),
                        xml_content TEXT,

                        has_errors BOOLEAN DEFAULT 0,
                        error_summary TEXT,

                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """))

                # Create indexes for SQLite
                conn.execute(text("CREATE INDEX idx_product_sync_history_executed_by ON product_sync_history(executed_by)"))
                conn.execute(text("CREATE INDEX idx_product_sync_history_executed_at ON product_sync_history(executed_at)"))
                conn.execute(text("CREATE INDEX idx_product_sync_history_provider ON product_sync_history(xml_provider)"))

            print("✓ Table product_sync_history created")
        else:
            print("✓ Table product_sync_history already exists")

        # Create product_sync_history_items table
        if not table_exists(conn, 'product_sync_history_items', is_pg):
            print("Creating table: product_sync_history_items")

            if is_pg:
                conn.execute(text("""
                    CREATE TABLE product_sync_history_items (
                        id SERIAL PRIMARY KEY,
                        history_id INTEGER REFERENCES product_sync_history(id) NOT NULL,

                        barcode VARCHAR(100) NOT NULL,
                        product_id INTEGER NOT NULL,
                        product_name VARCHAR(255) NOT NULL,

                        action VARCHAR(20) NOT NULL,
                        quantity_processed FLOAT NOT NULL,

                        success BOOLEAN NOT NULL,
                        error_message TEXT,

                        stock_before FLOAT,
                        stock_after FLOAT,
                        stock_updated BOOLEAN DEFAULT FALSE,

                        old_standard_price FLOAT,
                        new_standard_price FLOAT,
                        old_list_price FLOAT,
                        new_list_price FLOAT,
                        price_updated BOOLEAN DEFAULT FALSE,

                        is_new_product BOOLEAN DEFAULT FALSE,

                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))

                # Create indexes for PostgreSQL
                conn.execute(text("CREATE INDEX idx_product_sync_history_items_history ON product_sync_history_items(history_id)"))
                conn.execute(text("CREATE INDEX idx_product_sync_history_items_barcode ON product_sync_history_items(barcode)"))
                conn.execute(text("CREATE INDEX idx_product_sync_history_items_action ON product_sync_history_items(action)"))

            else:  # SQLite
                conn.execute(text("""
                    CREATE TABLE product_sync_history_items (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        history_id INTEGER REFERENCES product_sync_history(id) NOT NULL,

                        barcode VARCHAR(100) NOT NULL,
                        product_id INTEGER NOT NULL,
                        product_name VARCHAR(255) NOT NULL,

                        action VARCHAR(20) NOT NULL,
                        quantity_processed REAL NOT NULL,

                        success BOOLEAN NOT NULL,
                        error_message TEXT,

                        stock_before REAL,
                        stock_after REAL,
                        stock_updated BOOLEAN DEFAULT 0,

                        old_standard_price REAL,
                        new_standard_price REAL,
                        old_list_price REAL,
                        new_list_price REAL,
                        price_updated BOOLEAN DEFAULT 0,

                        is_new_product BOOLEAN DEFAULT 0,

                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """))

                # Create indexes for SQLite
                conn.execute(text("CREATE INDEX idx_product_sync_history_items_history ON product_sync_history_items(history_id)"))
                conn.execute(text("CREATE INDEX idx_product_sync_history_items_barcode ON product_sync_history_items(barcode)"))
                conn.execute(text("CREATE INDEX idx_product_sync_history_items_action ON product_sync_history_items(action)"))

            print("✓ Table product_sync_history_items created")
        else:
            print("✓ Table product_sync_history_items already exists")

        # Commit is automatic when exiting the context manager
        print("✅ Migration create_product_sync_history_tables completed successfully!")


def downgrade(engine):
    """Drop product sync history tables"""
    with engine.begin() as conn:
        # Drop in reverse order (items first due to foreign key)
        conn.execute(text("DROP TABLE IF EXISTS product_sync_history_items"))
        print("✓ Dropped table product_sync_history_items")

        conn.execute(text("DROP TABLE IF EXISTS product_sync_history"))
        print("✓ Dropped table product_sync_history")

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
