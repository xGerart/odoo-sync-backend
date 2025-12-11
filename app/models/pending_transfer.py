"""
Pending Transfer models for database persistence.
Stores transfers prepared by bodeguero awaiting admin confirmation.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Enum as SQLEnum, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.utils.timezone import get_ecuador_now
from enum import Enum


def _get_ecuador_now():
    """Wrapper for SQLAlchemy default."""
    return get_ecuador_now().replace(tzinfo=None)  # SQLite needs naive datetime


class TransferStatus(str, Enum):
    """Transfer status enum."""
    PENDING_VERIFICATION = "pending_verification"  # Awaiting bodeguero verification (cajero transfers)
    PENDING = "pending"  # Awaiting admin confirmation
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class PendingTransfer(Base):
    """
    Main transfer record prepared by bodeguero.
    Contains metadata about the transfer and references to items.
    """

    __tablename__ = "pending_transfers"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # Nullable for Odoo admins
    username = Column(String(50), nullable=False)  # For easy display
    created_by_role = Column(String(20), nullable=True)  # 'admin', 'bodeguero', 'cajero'
    status = Column(
        SQLEnum(TransferStatus, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=TransferStatus.PENDING,
        index=True
    )
    created_at = Column(DateTime, default=_get_ecuador_now, nullable=False)
    updated_at = Column(DateTime, default=_get_ecuador_now, onupdate=_get_ecuador_now, nullable=False)
    verified_at = Column(DateTime, nullable=True)
    verified_by = Column(String(50), nullable=True)  # Bodeguero username who verified
    confirmed_at = Column(DateTime, nullable=True)
    confirmed_by = Column(String(50), nullable=True)  # Admin username who confirmed

    # Destination tracking
    destination_location_id = Column(String(50), nullable=True)  # e.g., 'sucursal', 'sucursal_sacha'
    destination_location_name = Column(String(100), nullable=True)  # Human-readable name

    # Relationship to items
    items = relationship("PendingTransferItem", back_populates="transfer", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<PendingTransfer(id={self.id}, user='{self.username}', status='{self.status}', items={len(self.items)})>"

    def to_dict(self) -> dict:
        """Convert transfer to dictionary representation."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "username": self.username,
            "created_by_role": self.created_by_role,
            "status": self.status.value if isinstance(self.status, TransferStatus) else self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "verified_at": self.verified_at.isoformat() if self.verified_at else None,
            "verified_by": self.verified_by,
            "confirmed_at": self.confirmed_at.isoformat() if self.confirmed_at else None,
            "confirmed_by": self.confirmed_by,
            "destination_location_id": self.destination_location_id,
            "destination_location_name": self.destination_location_name,
            "items": [item.to_dict() for item in self.items] if self.items else []
        }


class PendingTransferItem(Base):
    """
    Individual product item in a pending transfer.
    Stores product details and quantities at time of preparation.
    """

    __tablename__ = "pending_transfer_items"

    id = Column(Integer, primary_key=True, index=True)
    transfer_id = Column(Integer, ForeignKey("pending_transfers.id"), nullable=False)
    barcode = Column(String(100), nullable=False, index=True)
    product_id = Column(Integer, nullable=False)  # Odoo product ID
    product_name = Column(String(255), nullable=False)
    quantity = Column(Integer, nullable=False)
    available_stock = Column(Integer, nullable=False)  # Stock at time of preparation
    unit_price = Column(Float, nullable=True)

    # Relationship to transfer
    transfer = relationship("PendingTransfer", back_populates="items")

    def __repr__(self) -> str:
        return f"<PendingTransferItem(id={self.id}, barcode='{self.barcode}', qty={self.quantity})>"

    def to_dict(self) -> dict:
        """Convert item to dictionary representation."""
        return {
            "id": self.id,
            "transfer_id": self.transfer_id,
            "barcode": self.barcode,
            "product_id": self.product_id,
            "product_name": self.product_name,
            "quantity": self.quantity,
            "available_stock": self.available_stock,
            "unit_price": self.unit_price
        }
