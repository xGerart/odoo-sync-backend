"""
Quick diagnostic script to check the invoicestatus enum in PostgreSQL.
This script connects to the database and shows the current enum values.

Usage:
    python check_enum_status.py
"""
import sys
import os
from sqlalchemy import create_engine, text

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.config import settings

def check_enum_status():
    """Check the current state of the invoicestatus enum"""
    print("="*60)
    print("ENUM STATUS CHECKER")
    print("="*60)
    
    if "postgresql" not in settings.DATABASE_URL.lower():
        print("⚠️  Database is not PostgreSQL. This check is only for PostgreSQL.")
        print(f"Current database: {settings.DATABASE_URL}")
        return
    
    print(f"Database: {settings.DATABASE_URL.split('@')[1] if '@' in settings.DATABASE_URL else 'hidden'}")
    print()
    
    try:
        engine = create_engine(settings.DATABASE_URL)
        
        with engine.connect() as conn:
            # Check if enum type exists
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT 1 FROM pg_type WHERE typname = 'invoicestatus'
                )
            """))
            enum_exists = result.scalar()
            
            if not enum_exists:
                print("❌ invoicestatus enum type does NOT exist")
                print("\nThe enum needs to be created. Run this SQL:")
                print("-" * 60)
                print("""
CREATE TYPE invoicestatus AS ENUM (
    'pendiente_revision',
    'en_revision',
    'corregida',
    'parcialmente_sincronizada',
    'sincronizada'
);

ALTER TABLE pending_invoices 
ALTER COLUMN status TYPE invoicestatus 
USING status::invoicestatus;
                """)
                print("-" * 60)
                return
            
            print("✅ invoicestatus enum type exists")
            print()
            
            # Get all enum values
            result = conn.execute(text("""
                SELECT enumlabel FROM pg_enum
                WHERE enumtypid = (SELECT oid FROM pg_type WHERE typname = 'invoicestatus')
                ORDER BY enumsortorder
            """))
            values = [row[0] for row in result]
            
            print("Current enum values:")
            for i, value in enumerate(values, 1):
                print(f"  {i}. {value}")
            
            print()
            
            # Check for the specific value
            has_parcialmente = 'parcialmente_sincronizada' in values
            
            if has_parcialmente:
                print("✅ 'parcialmente_sincronizada' value EXISTS")
                print("\nNo migration needed! The enum is correctly configured.")
            else:
                print("❌ 'parcialmente_sincronizada' value is MISSING")
                print("\nRun this SQL to add it:")
                print("-" * 60)
                print("ALTER TYPE invoicestatus ADD VALUE 'parcialmente_sincronizada';")
                print("-" * 60)
            
            print()
            
            # Check which columns use this enum
            result = conn.execute(text("""
                SELECT table_name, column_name 
                FROM information_schema.columns
                WHERE udt_name = 'invoicestatus'
                ORDER BY table_name, column_name
            """))
            columns = result.fetchall()
            
            if columns:
                print("Columns using invoicestatus enum:")
                for table, column in columns:
                    print(f"  - {table}.{column}")
            
    except Exception as e:
        print(f"❌ Error connecting to database: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(check_enum_status())
