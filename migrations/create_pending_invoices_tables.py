"""
Migration: Create pending_invoices and invoice_history tables.

This migration creates comprehensive tracking tables for invoices from SRI:
- pending_invoices: Invoices uploaded by admin, pending bodeguero review
- pending_invoice_items: Individual product items within each invoice
- invoice_history: Historical record of synced invoices
- invoice_history_items: Individual items within historical records

Date: 2025-12-18
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
    """Create pending invoices and history tables"""
    is_pg = is_postgres(engine)

    with engine.begin() as conn:
        # Create pending_invoices table
        if not table_exists(conn, 'pending_invoices', is_pg):
            print("Creating table: pending_invoices")

            if is_pg:
                conn.execute(text("""
                    CREATE TABLE pending_invoices (
                        id SERIAL PRIMARY KEY,

                        invoice_number VARCHAR(50),
                        supplier_name VARCHAR(255),
                        invoice_date TIMESTAMP,

                        uploaded_by_id INTEGER REFERENCES users(id),
                        uploaded_by_username VARCHAR(50) NOT NULL,
                        xml_filename VARCHAR(255) NOT NULL,
                        xml_content TEXT NOT NULL,

                        status VARCHAR(50) NOT NULL DEFAULT 'pendiente_revision',

                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,

                        submitted_at TIMESTAMP,
                        submitted_by VARCHAR(50),

                        synced_at TIMESTAMP,
                        synced_by VARCHAR(50),

                        notes TEXT
                    )
                """))

                # Create indexes
                conn.execute(text("CREATE INDEX idx_pending_invoices_status ON pending_invoices(status)"))
                conn.execute(text("CREATE INDEX idx_pending_invoices_uploaded_by_id ON pending_invoices(uploaded_by_id)"))
                conn.execute(text("CREATE INDEX idx_pending_invoices_created_at ON pending_invoices(created_at)"))
            else:
                # SQLite
                conn.execute(text("""
                    CREATE TABLE pending_invoices (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,

                        invoice_number VARCHAR(50),
                        supplier_name VARCHAR(255),
                        invoice_date TIMESTAMP,

                        uploaded_by_id INTEGER,
                        uploaded_by_username VARCHAR(50) NOT NULL,
                        xml_filename VARCHAR(255) NOT NULL,
                        xml_content TEXT NOT NULL,

                        status VARCHAR(50) NOT NULL DEFAULT 'pendiente_revision',

                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,

                        submitted_at TIMESTAMP,
                        submitted_by VARCHAR(50),

                        synced_at TIMESTAMP,
                        synced_by VARCHAR(50),

                        notes TEXT,

                        FOREIGN KEY (uploaded_by_id) REFERENCES users(id)
                    )
                """))

                # Create indexes
                conn.execute(text("CREATE INDEX idx_pending_invoices_status ON pending_invoices(status)"))
                conn.execute(text("CREATE INDEX idx_pending_invoices_uploaded_by_id ON pending_invoices(uploaded_by_id)"))
                conn.execute(text("CREATE INDEX idx_pending_invoices_created_at ON pending_invoices(created_at)"))

        # Create pending_invoice_items table
        if not table_exists(conn, 'pending_invoice_items', is_pg):
            print("Creating table: pending_invoice_items")

            if is_pg:
                conn.execute(text("""
                    CREATE TABLE pending_invoice_items (
                        id SERIAL PRIMARY KEY,
                        invoice_id INTEGER NOT NULL REFERENCES pending_invoices(id) ON DELETE CASCADE,

                        codigo_original VARCHAR(100) NOT NULL,
                        product_name VARCHAR(255) NOT NULL,

                        quantity FLOAT NOT NULL,
                        cantidad_original FLOAT NOT NULL,

                        barcode VARCHAR(100),

                        unit_price FLOAT,
                        total_price FLOAT,

                        modified_by_bodeguero BOOLEAN DEFAULT FALSE NOT NULL,

                        product_id INTEGER,
                        sync_success BOOLEAN,
                        sync_error TEXT
                    )
                """))

                # Create indexes
                conn.execute(text("CREATE INDEX idx_pending_invoice_items_invoice_id ON pending_invoice_items(invoice_id)"))
                conn.execute(text("CREATE INDEX idx_pending_invoice_items_barcode ON pending_invoice_items(barcode)"))
            else:
                # SQLite
                conn.execute(text("""
                    CREATE TABLE pending_invoice_items (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        invoice_id INTEGER NOT NULL,

                        codigo_original VARCHAR(100) NOT NULL,
                        product_name VARCHAR(255) NOT NULL,

                        quantity FLOAT NOT NULL,
                        cantidad_original FLOAT NOT NULL,

                        barcode VARCHAR(100),

                        unit_price FLOAT,
                        total_price FLOAT,

                        modified_by_bodeguero BOOLEAN DEFAULT 0 NOT NULL,

                        product_id INTEGER,
                        sync_success BOOLEAN,
                        sync_error TEXT,

                        FOREIGN KEY (invoice_id) REFERENCES pending_invoices(id) ON DELETE CASCADE
                    )
                """))

                # Create indexes
                conn.execute(text("CREATE INDEX idx_pending_invoice_items_invoice_id ON pending_invoice_items(invoice_id)"))
                conn.execute(text("CREATE INDEX idx_pending_invoice_items_barcode ON pending_invoice_items(barcode)"))

        # Create invoice_history table
        if not table_exists(conn, 'invoice_history', is_pg):
            print("Creating table: invoice_history")

            if is_pg:
                conn.execute(text("""
                    CREATE TABLE invoice_history (
                        id SERIAL PRIMARY KEY,
                        pending_invoice_id INTEGER REFERENCES pending_invoices(id),

                        invoice_number VARCHAR(50) NOT NULL,
                        supplier_name VARCHAR(255),
                        invoice_date TIMESTAMP,

                        uploaded_by VARCHAR(50) NOT NULL,
                        synced_by VARCHAR(50) NOT NULL,
                        synced_at TIMESTAMP NOT NULL,

                        total_items INTEGER DEFAULT 0 NOT NULL,
                        successful_items INTEGER DEFAULT 0 NOT NULL,
                        failed_items INTEGER DEFAULT 0 NOT NULL,
                        total_quantity FLOAT DEFAULT 0 NOT NULL,
                        total_value FLOAT,

                        xml_content TEXT,

                        has_errors BOOLEAN DEFAULT FALSE NOT NULL,
                        error_summary TEXT,

                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
                    )
                """))

                # Create indexes
                conn.execute(text("CREATE INDEX idx_invoice_history_pending_invoice_id ON invoice_history(pending_invoice_id)"))
                conn.execute(text("CREATE INDEX idx_invoice_history_synced_at ON invoice_history(synced_at)"))
            else:
                # SQLite
                conn.execute(text("""
                    CREATE TABLE invoice_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        pending_invoice_id INTEGER,

                        invoice_number VARCHAR(50) NOT NULL,
                        supplier_name VARCHAR(255),
                        invoice_date TIMESTAMP,

                        uploaded_by VARCHAR(50) NOT NULL,
                        synced_by VARCHAR(50) NOT NULL,
                        synced_at TIMESTAMP NOT NULL,

                        total_items INTEGER DEFAULT 0 NOT NULL,
                        successful_items INTEGER DEFAULT 0 NOT NULL,
                        failed_items INTEGER DEFAULT 0 NOT NULL,
                        total_quantity FLOAT DEFAULT 0 NOT NULL,
                        total_value FLOAT,

                        xml_content TEXT,

                        has_errors BOOLEAN DEFAULT 0 NOT NULL,
                        error_summary TEXT,

                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,

                        FOREIGN KEY (pending_invoice_id) REFERENCES pending_invoices(id)
                    )
                """))

                # Create indexes
                conn.execute(text("CREATE INDEX idx_invoice_history_pending_invoice_id ON invoice_history(pending_invoice_id)"))
                conn.execute(text("CREATE INDEX idx_invoice_history_synced_at ON invoice_history(synced_at)"))

        # Create invoice_history_items table
        if not table_exists(conn, 'invoice_history_items', is_pg):
            print("Creating table: invoice_history_items")

            if is_pg:
                conn.execute(text("""
                    CREATE TABLE invoice_history_items (
                        id SERIAL PRIMARY KEY,
                        history_id INTEGER NOT NULL REFERENCES invoice_history(id) ON DELETE CASCADE,

                        codigo_original VARCHAR(100) NOT NULL,
                        barcode VARCHAR(100),
                        product_id INTEGER,
                        product_name VARCHAR(255) NOT NULL,
                        quantity FLOAT NOT NULL,

                        unit_price FLOAT,
                        total_value FLOAT,

                        success BOOLEAN DEFAULT FALSE NOT NULL,
                        error_message TEXT,

                        was_modified BOOLEAN DEFAULT FALSE NOT NULL,

                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
                    )
                """))

                # Create indexes
                conn.execute(text("CREATE INDEX idx_invoice_history_items_history_id ON invoice_history_items(history_id)"))
                conn.execute(text("CREATE INDEX idx_invoice_history_items_barcode ON invoice_history_items(barcode)"))
            else:
                # SQLite
                conn.execute(text("""
                    CREATE TABLE invoice_history_items (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        history_id INTEGER NOT NULL,

                        codigo_original VARCHAR(100) NOT NULL,
                        barcode VARCHAR(100),
                        product_id INTEGER,
                        product_name VARCHAR(255) NOT NULL,
                        quantity FLOAT NOT NULL,

                        unit_price FLOAT,
                        total_value FLOAT,

                        success BOOLEAN DEFAULT 0 NOT NULL,
                        error_message TEXT,

                        was_modified BOOLEAN DEFAULT 0 NOT NULL,

                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,

                        FOREIGN KEY (history_id) REFERENCES invoice_history(id) ON DELETE CASCADE
                    )
                """))

                # Create indexes
                conn.execute(text("CREATE INDEX idx_invoice_history_items_history_id ON invoice_history_items(history_id)"))
                conn.execute(text("CREATE INDEX idx_invoice_history_items_barcode ON invoice_history_items(barcode)"))

        print("✅ Invoice tables created successfully")
