# Fix: Invalid Enum Value "parcialmente_sincronizada"

## Problem

The application is trying to use the status value `"parcialmente_sincronizada"` but the PostgreSQL database enum type `invoicestatus` doesn't include this value, causing the error:

```
invalid input value for enum invoicestatus: "parcialmente_sincronizada"
```

## Root Cause

The `InvoiceStatus` enum in the Python code includes `PARCIALMENTE_SINCRONIZADA`, but the PostgreSQL database was created before this value was added. PostgreSQL requires explicit migration to add new enum values.

## Solution

You need to run a database migration to add the missing enum value. There are three ways to do this:

### Option 1: Run the SQL Migration Directly (Recommended for Render)

1. Go to your Render dashboard
2. Navigate to your PostgreSQL database
3. Click on "Connect" → "External Connection" or use the web SQL interface
4. Run the SQL file: `alembic/versions/005_add_parcialmente_sincronizada_status.sql`

The SQL will:
- Check if the enum type exists
- If not, create it with all values and convert the columns
- If yes, add the missing value if needed

### Option 2: Use the Python Migration Runner (Local/Development)

Run the standalone migration script:

```bash
cd backend
python run_migration.py
```

This will execute all pending migrations including the new one that adds `parcialmente_sincronizada`.

### Option 3: Enable Auto-Migrations in Production

Uncomment the migration code in `app/main.py`:

```python
# Run database migrations after tables are created
try:
    run_migrations()
except Exception as e:
    print(f"❌ Migration failed: {e}")
    print(f"⚠️  Continuing startup, but some features may not work correctly")
```

Then redeploy the application. Migrations will run automatically on startup.

## Verification

After running the migration, verify it worked by checking the enum values:

```sql
SELECT enumlabel FROM pg_enum 
WHERE enumtypid = (SELECT oid FROM pg_type WHERE typname = 'invoicestatus')
ORDER BY enumsortorder;
```

You should see:
- `pendiente_revision`
- `en_revision`
- `corregida`
- `parcialmente_sincronizada` ← This should now be present
- `sincronizada`

## Testing

After the migration, test the invoice sync functionality:
1. Upload an invoice with multiple items
2. Sync only some of the items (partial sync)
3. Verify the invoice status becomes `parcialmente_sincronizada`
4. No database errors should occur

## Files Created/Modified

1. **`migrations/add_parcialmente_sincronizada_status.py`** - Python migration script
2. **`alembic/versions/005_add_parcialmente_sincronizada_status.sql`** - SQL migration for direct execution
3. **`run_migration.py`** - Standalone script to run migrations
4. **`MIGRATION_FIX.md`** - This documentation

## Additional Notes

- PostgreSQL does NOT support removing enum values once added
- If you need to remove a value, you must create a new enum type and migrate all data
- SQLite doesn't use enum types, so this issue only affects PostgreSQL deployments
- The migration is idempotent - safe to run multiple times

## Quick Fix Command (Copy-Paste for Render)

If you have psql access to your Render database:

```sql
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_enum
        WHERE enumtypid = (SELECT oid FROM pg_type WHERE typname = 'invoicestatus')
        AND enumlabel = 'parcialmente_sincronizada'
    ) THEN
        ALTER TYPE invoicestatus ADD VALUE 'parcialmente_sincronizada';
        RAISE NOTICE 'Added parcialmente_sincronizada to invoicestatus enum';
    ELSE
        RAISE NOTICE 'Value already exists';
    END IF;
END $$;
```
