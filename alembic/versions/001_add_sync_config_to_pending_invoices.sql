-- Migration: Add sync configuration fields to pending_invoices table
-- Date: 2025-12-23
-- Description: Adds profit_margin, apply_iva, and quantity_mode fields for price calculation

-- Add profit_margin column (default 0.5 = 50%)
ALTER TABLE pending_invoices ADD COLUMN profit_margin REAL NOT NULL DEFAULT 0.5;

-- Add apply_iva column (default TRUE)
ALTER TABLE pending_invoices ADD COLUMN apply_iva BOOLEAN NOT NULL DEFAULT 1;

-- Add quantity_mode column (default 'add')
ALTER TABLE pending_invoices ADD COLUMN quantity_mode VARCHAR(10) NOT NULL DEFAULT 'add';

-- Note: SQLite uses 1 for TRUE and 0 for FALSE
