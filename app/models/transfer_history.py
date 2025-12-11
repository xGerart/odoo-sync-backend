"""
Transfer History Models
Stores complete historical records of executed transfers with all details.
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.utils.timezone import get_ecuador_now
import json


class TransferHistory(Base):
    """
    Complete historical record of an executed transfer.
    Stores all details including snapshots, PDFs, and error information.
    """
    __tablename__ = "transfer_history"

    id = Column(Integer, primary_key=True, index=True)
    pending_transfer_id = Column(Integer, ForeignKey("pending_transfers.id"), nullable=True)

    # Origin and Destination
    origin_location = Column(String(50), default='principal')
    destination_location_id = Column(String(50), nullable=False)
    destination_location_name = Column(String(100), nullable=False)

    # Execution info
    executed_by = Column(String(50), nullable=False)
    executed_at = Column(DateTime, nullable=False)

    # Summary counts
    total_items = Column(Integer, nullable=False)
    successful_items = Column(Integer, nullable=False)
    failed_items = Column(Integer, nullable=False)
    total_quantity_requested = Column(Integer, nullable=False)
    total_quantity_transferred = Column(Integer, nullable=False)

    # Generated reports (stored as base64/text)
    pdf_content = Column(Text, nullable=True)  # Base64 encoded PDF
    pdf_filename = Column(String(255), nullable=True)
    xml_content = Column(Text, nullable=True)

    # Stock snapshots (stored as JSON)
    origin_snapshots_before = Column(Text, nullable=True)  # JSON array
    origin_snapshots_after = Column(Text, nullable=True)
    destination_snapshots_before = Column(Text, nullable=True)
    destination_snapshots_after = Column(Text, nullable=True)
    new_products = Column(Text, nullable=True)  # JSON array of newly created products

    # Error tracking
    has_errors = Column(Boolean, default=False)
    error_summary = Column(Text, nullable=True)

    created_at = Column(DateTime, default=get_ecuador_now)

    # Relationships
    items = relationship("TransferHistoryItem", back_populates="history", cascade="all, delete-orphan")
    pending_transfer = relationship("PendingTransfer", foreign_keys=[pending_transfer_id])

    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            "id": self.id,
            "pending_transfer_id": self.pending_transfer_id,
            "origin_location": self.origin_location,
            "destination_location_id": self.destination_location_id,
            "destination_location_name": self.destination_location_name,
            "executed_by": self.executed_by,
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
            "total_items": self.total_items,
            "successful_items": self.successful_items,
            "failed_items": self.failed_items,
            "total_quantity_requested": self.total_quantity_requested,
            "total_quantity_transferred": self.total_quantity_transferred,
            "pdf_filename": self.pdf_filename,
            "has_errors": self.has_errors,
            "error_summary": self.error_summary,
            "items": [item.to_dict() for item in self.items] if self.items else [],
            "origin_snapshots_before": json.loads(self.origin_snapshots_before) if self.origin_snapshots_before else [],
            "origin_snapshots_after": json.loads(self.origin_snapshots_after) if self.origin_snapshots_after else [],
            "destination_snapshots_before": json.loads(self.destination_snapshots_before) if self.destination_snapshots_before else [],
            "destination_snapshots_after": json.loads(self.destination_snapshots_after) if self.destination_snapshots_after else [],
            "new_products": json.loads(self.new_products) if self.new_products else [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class TransferHistoryItem(Base):
    """
    Individual product item within a transfer history record.
    Stores detailed result for each product including stock changes and errors.
    """
    __tablename__ = "transfer_history_items"

    id = Column(Integer, primary_key=True, index=True)
    history_id = Column(Integer, ForeignKey("transfer_history.id"), nullable=False, index=True)

    # Product identification
    barcode = Column(String(100), nullable=False, index=True)
    product_id = Column(Integer, nullable=False)
    product_name = Column(String(255), nullable=False)

    # Quantities
    quantity_requested = Column(Integer, nullable=False)
    quantity_transferred = Column(Integer, nullable=False)  # 0 if failed

    # Result
    success = Column(Boolean, nullable=False)
    error_message = Column(Text, nullable=True)  # NULL if success=True

    # Stock tracking
    stock_origin_before = Column(Integer, nullable=True)
    stock_origin_after = Column(Integer, nullable=True)
    stock_destination_before = Column(Integer, nullable=True)
    stock_destination_after = Column(Integer, nullable=True)

    # Pricing
    unit_price = Column(Float, nullable=True)
    total_value = Column(Float, nullable=True)  # quantity_transferred * unit_price

    # Metadata
    is_new_product = Column(Boolean, default=False)  # Created in destination during transfer

    created_at = Column(DateTime, default=get_ecuador_now)

    # Relationship
    history = relationship("TransferHistory", back_populates="items")

    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            "id": self.id,
            "history_id": self.history_id,
            "barcode": self.barcode,
            "product_id": self.product_id,
            "product_name": self.product_name,
            "quantity_requested": self.quantity_requested,
            "quantity_transferred": self.quantity_transferred,
            "success": self.success,
            "error_message": self.error_message,
            "stock_origin_before": self.stock_origin_before,
            "stock_origin_after": self.stock_origin_after,
            "stock_destination_before": self.stock_destination_before,
            "stock_destination_after": self.stock_destination_after,
            "unit_price": self.unit_price,
            "total_value": self.total_value,
            "is_new_product": self.is_new_product,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
