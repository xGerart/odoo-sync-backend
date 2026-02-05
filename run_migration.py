"""
Standalone script to run database migrations.
This can be used to manually run migrations, especially useful for production.

Usage:
    python run_migration.py
"""
import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.migrations.runner import run_migrations

if __name__ == "__main__":
    print("="*60)
    print("DATABASE MIGRATION RUNNER")
    print("="*60)
    
    try:
        run_migrations()
        print("\n✅ Migration process completed successfully")
    except Exception as e:
        print(f"\n❌ Migration process failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
