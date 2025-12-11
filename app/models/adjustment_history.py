"""
Adjustment History Models
Stores complete historical records of executed adjustments with all details.
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.utils.timezone import get_ecuador_now
import json


class AdjustmentHistory(Base):
    """
    Complete historical record of an executed adjustment.
    Stores all details including snapshots, PDFs, and error information.
    """
    __tablename__ = "adjustment_history"

    id = Column(Integer, primary_key=True, index=True)
    pending_adjustment_id = Column(Integer, ForeignKey("pending_adjustments.id"), nullable=True)

    # Location info
    location = Column(String(50), default='principal')
    location_name = Column(String(100), nullable=True)

    # Execution info
    executed_by = Column(String(50), nullable=False)
    executed_at = Column(DateTime, nullable=False)

    # Summary counts
    total_items = Column(Integer, nullable=False)
    successful_items = Column(Integer, nullable=False)
    failed_items = Column(Integer, nullable=False)
    total_quantity_requested = Column(Integer, nullable=False)
    total_quantity_adjusted = Column(Integer, nullable=False)

    # Generated reports (stored as base64/text)
    pdf_content = Column(Text, nullable=True)  # Base64 encoded PDF
    pdf_filename = Column(String(255), nullable=True)
    xml_content = Column(Text, nullable=True)

    # Stock snapshots (stored as JSON)
    snapshots_before = Column(Text, nullable=True)  # JSON array
    snapshots_after = Column(Text, nullable=True)

    # Error tracking
    has_errors = Column(Boolean, default=False)
    error_summary = Column(Text, nullable=True)

    created_at = Column(DateTime, default=get_ecuador_now)

    # Relationships
    items = relationship("AdjustmentHistoryItem", back_populates="history", cascade="all, delete-orphan")
    pending_adjustment = relationship("PendingAdjustment", foreign_keys=[pending_adjustment_id])

    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            "id": self.id,
            "pending_adjustment_id": self.pending_adjustment_id,
            "location": self.location,
            "location_name": self.location_name,
            "executed_by": self.executed_by,
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
            "total_items": self.total_items,
            "successful_items": self.successful_items,
            "failed_items": self.failed_items,
            "total_quantity_requested": self.total_quantity_requested,
            "total_quantity_adjusted": self.total_quantity_adjusted,
            "pdf_filename": self.pdf_filename,
            "has_errors": self.has_errors,
            "error_summary": self.error_summary,
            "items": [item.to_dict() for item in self.items] if self.items else [],
            "snapshots_before": json.loads(self.snapshots_before) if self.snapshots_before else [],
            "snapshots_after": json.loads(self.snapshots_after) if self.snapshots_after else [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AdjustmentHistoryItem(Base):
    """
    Individual product item within an adjustment history record.
    Stores detailed result for each product including stock changes and errors.
    """
    __tablename__ = "adjustment_history_items"

    id = Column(Integer, primary_key=True, index=True)
    history_id = Column(Integer, ForeignKey("adjustment_history.id"), nullable=False, index=True)

    # Product identification
    barcode = Column(String(100), nullable=False, index=True)
    product_id = Column(Integer, nullable=False)
    product_name = Column(String(255), nullable=False)

    # Quantities
    quantity_requested = Column(Integer, nullable=False)
    quantity_adjusted = Column(Integer, nullable=False)  # 0 if failed

    # Adjustment info
    adjustment_type = Column(String(50), nullable=False)  # 'increase', 'decrease'
    reason = Column(String(100), nullable=True)

    # Result
    success = Column(Boolean, nullable=False)
    error_message = Column(Text, nullable=True)  # NULL if success=True

    # Stock tracking
    stock_before = Column(Integer, nullable=True)
    stock_after = Column(Integer, nullable=True)

    # Pricing
    unit_price = Column(Float, nullable=True)
    total_value = Column(Float, nullable=True)  # quantity_adjusted * unit_price

    created_at = Column(DateTime, default=get_ecuador_now)

    # Relationship
    history = relationship("AdjustmentHistory", back_populates="items")

    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            "id": self.id,
            "history_id": self.history_id,
            "barcode": self.barcode,
            "product_id": self.product_id,
            "product_name": self.product_name,
            "quantity_requested": self.quantity_requested,
            "quantity_adjusted": self.quantity_adjusted,
            "adjustment_type": self.adjustment_type,
            "reason": self.reason,
            "success": self.success,
            "error_message": self.error_message,
            "stock_before": self.stock_before,
            "stock_after": self.stock_after,
            "unit_price": self.unit_price,
            "total_value": self.total_value,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
