"""
Migration: Expand photo_url column from VARCHAR(500) to TEXT in pending_adjustment_items table.

This migration changes the photo_url column type to accommodate full base64-encoded images
instead of just URLs. Base64 images can be several MB in size, requiring TEXT instead of VARCHAR(500).

Date: 2026-01-06
"""

from sqlalchemy import text


def is_postgres(engine):
    """Check if database is PostgreSQL"""
    return "postgresql" in str(engine.url)


def upgrade(engine):
    """Expand photo_url column from VARCHAR(500) to TEXT"""
    is_pg = is_postgres(engine)

    with engine.begin() as conn:
        print("Expanding photo_url column from VARCHAR(500) to TEXT in pending_adjustment_items")

        if is_pg:
            # PostgreSQL: Alter column type
            conn.execute(text("""
                ALTER TABLE pending_adjustment_items
                ALTER COLUMN photo_url TYPE TEXT
            """))
        else:
            # SQLite: Need to recreate the table because SQLite doesn't support ALTER COLUMN TYPE
            # First check if the table exists
            result = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='pending_adjustment_items'"))
            if result.fetchone() is None:
                print("⏭️  Table pending_adjustment_items doesn't exist yet, skipping")
                return

            print("SQLite detected: recreating table with TEXT column...")

            # SQLite workaround: Create new table, copy data, drop old, rename new
            conn.execute(text("""
                CREATE TABLE pending_adjustment_items_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    adjustment_id INTEGER NOT NULL,
                    barcode VARCHAR(100) NOT NULL,
                    product_id INTEGER NOT NULL,
                    product_name VARCHAR(255) NOT NULL,
                    quantity INTEGER NOT NULL,
                    available_stock INTEGER NOT NULL,
                    adjustment_type VARCHAR(50) NOT NULL,
                    reason VARCHAR(50) NOT NULL,
                    description TEXT,
                    unit_price REAL,
                    new_product_name VARCHAR(255),
                    photo_url TEXT,
                    FOREIGN KEY (adjustment_id) REFERENCES pending_adjustments(id)
                )
            """))

            # Copy data from old table to new
            conn.execute(text("""
                INSERT INTO pending_adjustment_items_new
                SELECT id, adjustment_id, barcode, product_id, product_name, quantity,
                       available_stock, adjustment_type, reason, description, unit_price,
                       new_product_name, photo_url
                FROM pending_adjustment_items
            """))

            # Drop old table
            conn.execute(text("DROP TABLE pending_adjustment_items"))

            # Rename new table
            conn.execute(text("ALTER TABLE pending_adjustment_items_new RENAME TO pending_adjustment_items"))

            # Recreate indexes
            conn.execute(text("CREATE INDEX ix_pending_adjustment_items_barcode ON pending_adjustment_items(barcode)"))

        print("✅ photo_url column successfully expanded to TEXT")
