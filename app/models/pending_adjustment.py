"""
Pending Adjustment models for database persistence.
Stores inventory adjustments prepared by bodeguero awaiting admin confirmation.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Enum as SQLEnum, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.utils.timezone import get_ecuador_now
from enum import Enum


def _get_ecuador_now():
    """Wrapper for SQLAlchemy default."""
    return get_ecuador_now().replace(tzinfo=None)  # SQLite needs naive datetime


class AdjustmentStatus(str, Enum):
    """Adjustment status enum."""
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class AdjustmentType(str, Enum):
    """Adjustment type enum."""
    ENTRY = "entry"
    EXIT = "exit"
    ADJUSTMENT = "adjustment"


class AdjustmentReason(str, Enum):
    """Adjustment reason enum."""
    # ENTRY reasons
    PURCHASE = "purchase"
    RETURN_IN = "return_in"
    CORRECTION_IN = "correction_in"
    # EXIT reasons
    SALE = "sale"
    DAMAGE = "damage"
    LOSS = "loss"
    THEFT = "theft"
    RETURN_OUT = "return_out"
    CORRECTION_OUT = "correction_out"
    # ADJUSTMENT reasons
    PHYSICAL_COUNT = "physical_count"
    SYSTEM_CORRECTION = "system_correction"


class PendingAdjustment(Base):
    """
    Main adjustment record prepared by bodeguero.
    Contains metadata about the adjustment and references to items.
    """

    __tablename__ = "pending_adjustments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # Nullable for Odoo admins
    username = Column(String(50), nullable=False)  # For easy display
    adjustment_type = Column(
        SQLEnum(AdjustmentType, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        index=True
    )
    status = Column(
        SQLEnum(AdjustmentStatus, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=AdjustmentStatus.PENDING,
        index=True
    )
    created_at = Column(DateTime, default=_get_ecuador_now, nullable=False)
    updated_at = Column(DateTime, default=_get_ecuador_now, onupdate=_get_ecuador_now, nullable=False)
    confirmed_at = Column(DateTime, nullable=True)
    confirmed_by = Column(String(50), nullable=True)  # Admin username who confirmed

    # Relationship to items
    items = relationship("PendingAdjustmentItem", back_populates="adjustment", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<PendingAdjustment(id={self.id}, user='{self.username}', type='{self.adjustment_type}', status='{self.status}', items={len(self.items)})>"

    def to_dict(self) -> dict:
        """Convert adjustment to dictionary representation."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "username": self.username,
            "adjustment_type": self.adjustment_type.value if isinstance(self.adjustment_type, AdjustmentType) else self.adjustment_type,
            "status": self.status.value if isinstance(self.status, AdjustmentStatus) else self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "confirmed_at": self.confirmed_at.isoformat() if self.confirmed_at else None,
            "confirmed_by": self.confirmed_by,
            "items": [item.to_dict() for item in self.items] if self.items else []
        }


class PendingAdjustmentItem(Base):
    """
    Individual product item in a pending adjustment.
    Stores product details, quantities, reason, and description at time of preparation.
    """

    __tablename__ = "pending_adjustment_items"

    id = Column(Integer, primary_key=True, index=True)
    adjustment_id = Column(Integer, ForeignKey("pending_adjustments.id"), nullable=False)
    barcode = Column(String(100), nullable=False, index=True)
    product_id = Column(Integer, nullable=False)  # Odoo product ID
    product_name = Column(String(255), nullable=False)
    quantity = Column(Integer, nullable=False)  # Can be negative for exits
    available_stock = Column(Integer, nullable=False)  # Stock at time of preparation
    adjustment_type = Column(
        SQLEnum(AdjustmentType, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False
    )
    reason = Column(
        SQLEnum(AdjustmentReason, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False
    )
    description = Column(Text, nullable=True)
    unit_price = Column(Float, nullable=True)
    new_product_name = Column(String(255), nullable=True)  # For ADJUSTMENT type: new name
    photo_url = Column(String(500), nullable=True)  # For ADJUSTMENT type: photo URL

    # Relationship to adjustment
    adjustment = relationship("PendingAdjustment", back_populates="items")

    def __repr__(self) -> str:
        return f"<PendingAdjustmentItem(id={self.id}, barcode='{self.barcode}', qty={self.quantity}, reason='{self.reason}')>"

    def to_dict(self) -> dict:
        """Convert item to dictionary representation."""
        return {
            "id": self.id,
            "adjustment_id": self.adjustment_id,
            "barcode": self.barcode,
            "product_id": self.product_id,
            "product_name": self.product_name,
            "quantity": self.quantity,
            "available_stock": self.available_stock,
            "adjustment_type": self.adjustment_type.value if isinstance(self.adjustment_type, AdjustmentType) else self.adjustment_type,
            "reason": self.reason.value if isinstance(self.reason, AdjustmentReason) else self.reason,
            "description": self.description,
            "unit_price": self.unit_price,
            "new_product_name": self.new_product_name,
            "photo_url": self.photo_url
        }
