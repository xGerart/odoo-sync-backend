"""
Application settings model for storing configurable settings in database.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime
from app.core.database import Base


class AppSetting(Base):
    """Key-value store for application settings."""

    __tablename__ = "app_settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, nullable=False, index=True)
    value = Column(String(500), nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    updated_by = Column(String(50), nullable=True)

    def __repr__(self) -> str:
        return f"<AppSetting(key='{self.key}', value='{self.value}')>"
