"""
Product Sync History Models
Stores complete historical records of product synchronizations from XML files.
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.utils.timezone import get_ecuador_now


class ProductSyncHistory(Base):
    """
    Complete historical record of a product synchronization from XML.
    Stores all details including file info, configuration, results, and PDFs.
    """
    __tablename__ = "product_sync_history"

    id = Column(Integer, primary_key=True, index=True)

    # XML File info
    xml_filename = Column(String(255), nullable=False)
    xml_provider = Column(String(50), nullable=False)  # 'D''Mujeres', 'LANSEY', 'Generic'

    # Sync configuration
    profit_margin = Column(Float, nullable=True)
    quantity_mode = Column(String(10), nullable=False)  # 'replace' or 'add'
    apply_iva = Column(Boolean, default=True)

    # Execution info
    executed_by = Column(String(50), nullable=False)
    executed_at = Column(DateTime, nullable=False)

    # Summary counts
    total_items = Column(Integer, nullable=False)
    successful_items = Column(Integer, nullable=False)
    failed_items = Column(Integer, nullable=False)
    created_count = Column(Integer, nullable=False)
    updated_count = Column(Integer, nullable=False)

    # Generated reports (stored as base64/text)
    pdf_content = Column(Text, nullable=True)  # Base64 encoded PDF
    pdf_filename = Column(String(255), nullable=True)
    xml_content = Column(Text, nullable=True)  # Original XML content

    # Error tracking
    has_errors = Column(Boolean, default=False)
    error_summary = Column(Text, nullable=True)

    created_at = Column(DateTime, default=get_ecuador_now)

    # Relationships
    items = relationship("ProductSyncHistoryItem", back_populates="history", cascade="all, delete-orphan")

    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            "id": self.id,
            "xml_filename": self.xml_filename,
            "xml_provider": self.xml_provider,
            "profit_margin": self.profit_margin,
            "quantity_mode": self.quantity_mode,
            "apply_iva": self.apply_iva,
            "executed_by": self.executed_by,
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
            "total_items": self.total_items,
            "successful_items": self.successful_items,
            "failed_items": self.failed_items,
            "created_count": self.created_count,
            "updated_count": self.updated_count,
            "pdf_filename": self.pdf_filename,
            "has_errors": self.has_errors,
            "error_summary": self.error_summary,
            "items": [item.to_dict() for item in self.items] if self.items else [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class ProductSyncHistoryItem(Base):
    """
    Individual product item within a product sync history record.
    Stores detailed result for each product including price and stock changes.
    """
    __tablename__ = "product_sync_history_items"

    id = Column(Integer, primary_key=True, index=True)
    history_id = Column(Integer, ForeignKey("product_sync_history.id"), nullable=False, index=True)

    # Product identification
    barcode = Column(String(100), nullable=False, index=True)
    product_id = Column(Integer, nullable=False)
    product_name = Column(String(255), nullable=False)

    # Action and quantity
    action = Column(String(20), nullable=False, index=True)  # 'created', 'updated', 'error'
    quantity_processed = Column(Float, nullable=False)

    # Result
    success = Column(Boolean, nullable=False)
    error_message = Column(Text, nullable=True)

    # Stock tracking
    stock_before = Column(Float, nullable=True)
    stock_after = Column(Float, nullable=True)
    stock_updated = Column(Boolean, default=False)

    # Price tracking
    old_standard_price = Column(Float, nullable=True)
    new_standard_price = Column(Float, nullable=True)
    old_list_price = Column(Float, nullable=True)
    new_list_price = Column(Float, nullable=True)
    price_updated = Column(Boolean, default=False)

    # Metadata
    is_new_product = Column(Boolean, default=False)

    created_at = Column(DateTime, default=get_ecuador_now)

    # Relationship
    history = relationship("ProductSyncHistory", back_populates="items")

    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            "id": self.id,
            "history_id": self.history_id,
            "barcode": self.barcode,
            "product_id": self.product_id,
            "product_name": self.product_name,
            "action": self.action,
            "quantity_processed": self.quantity_processed,
            "success": self.success,
            "error_message": self.error_message,
            "stock_before": self.stock_before,
            "stock_after": self.stock_after,
            "stock_updated": self.stock_updated,
            "old_standard_price": self.old_standard_price,
            "new_standard_price": self.new_standard_price,
            "old_list_price": self.old_list_price,
            "new_list_price": self.new_list_price,
            "price_updated": self.price_updated,
            "is_new_product": self.is_new_product,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
