"""
Migration runner for automatic database migrations
"""
import importlib.util
import logging
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from app.core.config import settings

logger = logging.getLogger(__name__)


def is_postgres(engine):
    """Check if database is PostgreSQL"""
    return "postgresql" in str(engine.url)


def is_sqlite(engine):
    """Check if database is SQLite"""
    return "sqlite" in str(engine.url)


def get_migration_files(migrations_dir: Path) -> list[Path]:
    """Get all .py migration files sorted by name"""
    migrations = [
        f for f in migrations_dir.glob("*.py")
        if f.name != "__init__.py" and not f.name.startswith("_")
    ]
    return sorted(migrations)


def has_migration_run(session: Session, migration_name: str) -> bool:
    """Check if migration has been applied"""
    result = session.execute(
        text("SELECT 1 FROM migration_history WHERE migration_name = :name"),
        {"name": migration_name}
    )
    return result.fetchone() is not None


def record_migration(session: Session, migration_name: str):
    """Record that a migration has been applied"""
    session.execute(
        text("INSERT INTO migration_history (migration_name) VALUES (:name)"),
        {"name": migration_name}
    )
    session.commit()


def create_migration_table(engine):
    """Create migration_history table if it doesn't exist"""
    with engine.connect() as conn:
        if is_postgres(engine):
            # PostgreSQL version
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS migration_history (
                    id SERIAL PRIMARY KEY,
                    migration_name VARCHAR(255) UNIQUE NOT NULL,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
        else:
            # SQLite version
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS migration_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    migration_name VARCHAR(255) UNIQUE NOT NULL,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
        conn.commit()


def run_migrations():
    """Run all pending migrations"""
    logger.info("🔄 Checking for pending migrations...")

    # Create engine
    engine = create_engine(settings.DATABASE_URL)

    # Ensure migration_history table exists
    create_migration_table(engine)

    # Get migrations directory
    migrations_dir = Path(__file__).parent.parent.parent / "migrations"

    if not migrations_dir.exists():
        logger.info("No migrations directory found")
        return

    migration_files = get_migration_files(migrations_dir)

    if not migration_files:
        logger.info("No migration files found")
        return

    with Session(engine) as session:
        pending_count = 0

        for migration_file in migration_files:
            migration_name = migration_file.stem

            if has_migration_run(session, migration_name):
                logger.debug(f"✓ Migration already applied: {migration_name}")
                continue

            logger.info(f"▶ Running migration: {migration_name}")
            pending_count += 1

            try:
                # Load and execute migration
                spec = importlib.util.spec_from_file_location(migration_name, migration_file)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                # Execute upgrade function
                if hasattr(module, 'upgrade'):
                    module.upgrade(engine)
                    record_migration(session, migration_name)
                    logger.info(f"✅ Migration completed: {migration_name}")
                else:
                    logger.warning(f"⚠️  Migration {migration_name} has no upgrade() function")

            except Exception as e:
                logger.error(f"❌ Migration failed: {migration_name}")
                logger.error(f"Error: {str(e)}")
                raise

        if pending_count == 0:
            logger.info("✅ All migrations up to date")
        else:
            logger.info(f"✅ Applied {pending_count} migration(s)")
