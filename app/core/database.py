"""
Database configuration and session management using SQLAlchemy.
"""
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from app.core.config import settings


# Create database engine
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,  # Verify connections before using
    pool_size=5,
    max_overflow=10,
    echo=settings.DEBUG  # Log SQL queries in debug mode
)

# Session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# Base class for ORM models
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """
    Dependency that provides a database session.

    Yields:
        Database session

    Usage:
        @router.get("/items")
        def get_items(db: Session = Depends(get_db)):
            return db.query(Item).all()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """
    Initialize database tables.
    Creates all tables defined in models.

    This should be called on application startup.
    In production, use Alembic migrations instead.
    """
    from app.models import user, odoo_connection, audit_log, pending_transfer, pending_adjustment  # noqa
    Base.metadata.create_all(bind=engine)


def close_db() -> None:
    """
    Close database connections.
    Should be called on application shutdown.
    """
    engine.dispose()
