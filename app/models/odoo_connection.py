"""
Odoo connection configuration model.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from app.core.database import Base


class OdooConnection(Base):
    """
    Stores Odoo connection configurations.
    Can be used to cache connection details for different locations.
    """

    __tablename__ = "odoo_connections"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), nullable=False, unique=True)  # 'principal' or 'sucursal'
    url = Column(String(255), nullable=False)
    database = Column(String(100), nullable=False)
    port = Column(Integer, default=443, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self) -> str:
        return f"<OdooConnection(id={self.id}, name='{self.name}', url='{self.url}')>"

    def to_dict(self) -> dict:
        """Convert connection to dictionary representation."""
        return {
            "id": self.id,
            "name": self.name,
            "url": self.url,
            "database": self.database,
            "port": self.port,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
