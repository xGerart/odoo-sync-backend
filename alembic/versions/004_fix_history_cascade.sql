-- Fix foreign key constraint to prevent history deletion when pending invoice is deleted
-- SQLite requires recreating the table to modify foreign key constraints

PRAGMA foreign_keys=off;

BEGIN TRANSACTION;

-- Create new table with correct foreign key constraint
CREATE TABLE invoice_history_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pending_invoice_id INTEGER,
    invoice_number VARCHAR(50) NOT NULL,
    supplier_name VARCHAR(255),
    invoice_date DATETIME,
    uploaded_by VARCHAR(50) NOT NULL,
    synced_by VARCHAR(50) NOT NULL,
    synced_at DATETIME NOT NULL,
    total_items INTEGER DEFAULT 0 NOT NULL,
    successful_items INTEGER DEFAULT 0 NOT NULL,
    failed_items INTEGER DEFAULT 0 NOT NULL,
    total_quantity REAL DEFAULT 0 NOT NULL,
    total_value REAL,
    xml_content TEXT,
    has_errors BOOLEAN DEFAULT 0 NOT NULL,
    error_summary TEXT,
    created_at DATETIME NOT NULL,
    FOREIGN KEY (pending_invoice_id) REFERENCES pending_invoices(id) ON DELETE SET NULL
);

-- Copy data from old table
INSERT INTO invoice_history_new
SELECT * FROM invoice_history;

-- Drop old table
DROP TABLE invoice_history;

-- Rename new table
ALTER TABLE invoice_history_new RENAME TO invoice_history;

-- Recreate indexes
CREATE INDEX ix_invoice_history_id ON invoice_history(id);
CREATE INDEX ix_invoice_history_pending_invoice_id ON invoice_history(pending_invoice_id);
CREATE INDEX ix_invoice_history_synced_at ON invoice_history(synced_at);

COMMIT;

PRAGMA foreign_keys=on;
