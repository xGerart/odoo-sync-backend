-- Migration: Add PARCIALMENTE_SINCRONIZADA status to invoicestatus enum
-- Date: 2026-01-15
-- Description: Adds the missing 'parcialmente_sincronizada' value to the invoicestatus enum type
--
-- IMPORTANT: This migration is for PostgreSQL only and must be run in production
--
-- Instructions for Render:
-- 1. Go to your database dashboard in Render
-- 2. Connect to the database using psql or the web interface
-- 3. Run these commands in order

-- Check if the enum type exists
DO $$ 
BEGIN
    -- Check if invoicestatus enum exists
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'invoicestatus') THEN
        -- Create the enum with all values
        RAISE NOTICE 'Creating invoicestatus enum type...';
        CREATE TYPE invoicestatus AS ENUM (
            'pendiente_revision',
            'en_revision',
            'corregida',
            'parcialmente_sincronizada',
            'sincronizada'
        );
        
        -- Convert the existing VARCHAR column to use the enum
        RAISE NOTICE 'Converting pending_invoices.status to enum...';
        ALTER TABLE pending_invoices 
        ALTER COLUMN status TYPE invoicestatus 
        USING status::invoicestatus;
        
        -- Convert invoice_history.status if the table exists
        IF EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'invoice_history') THEN
            RAISE NOTICE 'Converting invoice_history.status to enum...';
            ALTER TABLE invoice_history 
            ALTER COLUMN status TYPE invoicestatus 
            USING status::invoicestatus;
        END IF;
        
        RAISE NOTICE 'Successfully created invoicestatus enum and converted columns';
    ELSE
        -- Enum exists, check if value is already present
        IF EXISTS (
            SELECT 1 FROM pg_enum
            WHERE enumtypid = (SELECT oid FROM pg_type WHERE typname = 'invoicestatus')
            AND enumlabel = 'parcialmente_sincronizada'
        ) THEN
            RAISE NOTICE 'Value parcialmente_sincronizada already exists in invoicestatus enum';
        ELSE
            -- Add the missing value
            RAISE NOTICE 'Adding parcialmente_sincronizada to invoicestatus enum...';
            ALTER TYPE invoicestatus ADD VALUE 'parcialmente_sincronizada';
            RAISE NOTICE 'Successfully added parcialmente_sincronizada value';
        END IF;
    END IF;
END $$;

-- Verify the enum values
SELECT enumlabel FROM pg_enum 
WHERE enumtypid = (SELECT oid FROM pg_type WHERE typname = 'invoicestatus')
ORDER BY enumsortorder;
