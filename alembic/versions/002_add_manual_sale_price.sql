-- Migration: Add manual_sale_price to pending_invoice_items table
-- Date: 2025-12-23
-- Description: Allows admin to manually override calculated sale price

-- Add manual_sale_price column (nullable, only set when admin edits)
ALTER TABLE pending_invoice_items ADD COLUMN manual_sale_price REAL NULL;

-- Note: This field stores the price WITH IVA included (the display price)
-- When syncing to Odoo, we subtract IVA if apply_iva is enabled
