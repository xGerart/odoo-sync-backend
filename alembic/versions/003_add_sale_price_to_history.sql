-- Add sale_price column to invoice_history_items table
-- This stores the sale price that was synced to Odoo for each item

ALTER TABLE invoice_history_items ADD COLUMN sale_price REAL NULL;
