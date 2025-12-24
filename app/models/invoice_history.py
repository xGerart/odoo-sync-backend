"""
Invoice History models for tracking completed invoice syncs.
Stores historical record of invoice synchronizations to Odoo.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.utils.timezone import get_ecuador_now


def _get_ecuador_now():
    """Wrapper for SQLAlchemy default."""
    return get_ecuador_now().replace(tzinfo=None)  # SQLite needs naive datetime


class InvoiceHistory(Base):
    """
    Historical record of invoice synchronization.
    Created when admin successfully (or attempts to) sync invoice to Odoo.
    """

    __tablename__ = "invoice_history"

    id = Column(Integer, primary_key=True, index=True)

    # Link to original pending invoice (nullable if pending is deleted)
    pending_invoice_id = Column(Integer, ForeignKey("pending_invoices.id", ondelete="SET NULL"), nullable=True, index=True)

    # Invoice metadata (snapshot)
    invoice_number = Column(String(50), nullable=False)
    supplier_name = Column(String(255), nullable=True)
    invoice_date = Column(DateTime, nullable=True)

    # Tracking
    uploaded_by = Column(String(50), nullable=False)
    synced_by = Column(String(50), nullable=False)
    synced_at = Column(DateTime, default=_get_ecuador_now, nullable=False, index=True)

    # Summary statistics
    total_items = Column(Integer, default=0, nullable=False)
    successful_items = Column(Integer, default=0, nullable=False)
    failed_items = Column(Integer, default=0, nullable=False)
    total_quantity = Column(Float, default=0, nullable=False)
    total_value = Column(Float, nullable=True)

    # XML content (optional, can be large)
    xml_content = Column(Text, nullable=True)

    # Error tracking
    has_errors = Column(Boolean, default=False, nullable=False)
    error_summary = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=_get_ecuador_now, nullable=False)

    # Relationship to items
    items = relationship("InvoiceHistoryItem", back_populates="history", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<InvoiceHistory(id={self.id}, invoice='{self.invoice_number}', items={self.total_items}, success={self.successful_items}, failed={self.failed_items})>"

    def to_dict(self) -> dict:
        """Convert history to dictionary representation."""
        return {
            "id": self.id,
            "pending_invoice_id": self.pending_invoice_id,
            "invoice_number": self.invoice_number,
            "supplier_name": self.supplier_name,
            "invoice_date": self.invoice_date.isoformat() if self.invoice_date else None,
            "uploaded_by": self.uploaded_by,
            "synced_by": self.synced_by,
            "synced_at": self.synced_at.isoformat() if self.synced_at else None,
            "total_items": self.total_items,
            "successful_items": self.successful_items,
            "failed_items": self.failed_items,
            "total_quantity": self.total_quantity,
            "total_value": self.total_value,
            "has_errors": self.has_errors,
            "error_summary": self.error_summary,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "items": [item.to_dict() for item in self.items] if self.items else []
        }


class InvoiceHistoryItem(Base):
    """
    Individual product item in invoice history.
    Records result of each product sync attempt.
    """

    __tablename__ = "invoice_history_items"

    id = Column(Integer, primary_key=True, index=True)
    history_id = Column(Integer, ForeignKey("invoice_history.id"), nullable=False)

    # Product info (snapshot)
    codigo_original = Column(String(100), nullable=False)
    barcode = Column(String(100), nullable=True, index=True)
    product_id = Column(Integer, nullable=True)  # Odoo product ID if found
    product_name = Column(String(255), nullable=False)
    quantity = Column(Float, nullable=False)

    # Prices
    unit_price = Column(Float, nullable=True)  # Cost
    sale_price = Column(Float, nullable=True)  # Sale price that was synced to Odoo
    total_value = Column(Float, nullable=True)  # Total cost (unit_price * quantity)

    # Sync result
    success = Column(Boolean, default=False, nullable=False)
    error_message = Column(Text, nullable=True)

    # Was item modified by bodeguero?
    was_modified = Column(Boolean, default=False, nullable=False)

    # Timestamp
    created_at = Column(DateTime, default=_get_ecuador_now, nullable=False)

    # Relationship to history
    history = relationship("InvoiceHistory", back_populates="items")

    def __repr__(self) -> str:
        return f"<InvoiceHistoryItem(id={self.id}, codigo='{self.codigo_original}', success={self.success})>"

    def to_dict(self) -> dict:
        """Convert item to dictionary representation."""
        return {
            "id": self.id,
            "history_id": self.history_id,
            "codigo_original": self.codigo_original,
            "barcode": self.barcode,
            "product_id": self.product_id,
            "product_name": self.product_name,
            "quantity": self.quantity,
            "unit_price": self.unit_price,
            "sale_price": self.sale_price,
            "total_value": self.total_value,
            "success": self.success,
            "error_message": self.error_message,
            "was_modified": self.was_modified,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
