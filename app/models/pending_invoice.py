"""
Pending Invoice models for database persistence.
Stores invoices from SRI pending bodeguero review and admin sync.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Text, DateTime, Boolean, Enum as SQLEnum, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.utils.timezone import get_ecuador_now
from enum import Enum


def _get_ecuador_now():
    """Wrapper for SQLAlchemy default."""
    return get_ecuador_now().replace(tzinfo=None)  # SQLite needs naive datetime


class InvoiceStatus(str, Enum):
    """Invoice processing status enum."""
    PENDIENTE_REVISION = "pendiente_revision"  # Admin uploaded, waiting for bodeguero
    EN_REVISION = "en_revision"  # Bodeguero working on it
    CORREGIDA = "corregida"  # Bodeguero finished, waiting for admin sync
    PARCIALMENTE_SINCRONIZADA = "parcialmente_sincronizada"  # Some items synced, others pending
    SINCRONIZADA = "sincronizada"  # All items synced to Odoo


class PendingInvoice(Base):
    """
    Main invoice record from SRI XML.
    Contains metadata about the invoice and references to items.
    """

    __tablename__ = "pending_invoices"

    id = Column(Integer, primary_key=True, index=True)

    # Invoice metadata
    invoice_number = Column(String(50), nullable=True)
    supplier_name = Column(String(255), nullable=True)
    invoice_date = Column(DateTime, nullable=True)

    # Upload tracking
    uploaded_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    uploaded_by_username = Column(String(50), nullable=False)
    xml_filename = Column(String(255), nullable=False)
    xml_content = Column(Text, nullable=False)

    # Barcode extraction preference
    barcode_source = Column(String(20), nullable=True, default='codigoAuxiliar')  # 'codigoPrincipal' or 'codigoAuxiliar'

    # Status tracking
    status = Column(
        SQLEnum(InvoiceStatus, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=InvoiceStatus.PENDIENTE_REVISION,
        index=True
    )

    # Timestamps
    created_at = Column(DateTime, default=_get_ecuador_now, nullable=False)
    updated_at = Column(DateTime, default=_get_ecuador_now, onupdate=_get_ecuador_now, nullable=False)

    # Bodeguero submission
    submitted_at = Column(DateTime, nullable=True)
    submitted_by = Column(String(50), nullable=True)

    # Admin sync
    synced_at = Column(DateTime, nullable=True)
    synced_by = Column(String(50), nullable=True)

    # Notes
    notes = Column(Text, nullable=True)

    # Sync configuration (for price calculation)
    profit_margin = Column(Float, default=0.5, nullable=False)  # 50% default margin
    apply_iva = Column(Boolean, default=True, nullable=False)  # Apply IVA to sale price
    quantity_mode = Column(String(10), default='add', nullable=False)  # 'add' or 'replace' stock

    # Relationship to items
    items = relationship("PendingInvoiceItem", back_populates="invoice", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<PendingInvoice(id={self.id}, number='{self.invoice_number}', status='{self.status}', items={len(self.items)})>"

    def to_dict(self) -> dict:
        """Convert invoice to dictionary representation."""
        return {
            "id": self.id,
            "invoice_number": self.invoice_number,
            "supplier_name": self.supplier_name,
            "invoice_date": self.invoice_date.isoformat() if self.invoice_date else None,
            "uploaded_by_id": self.uploaded_by_id,
            "uploaded_by_username": self.uploaded_by_username,
            "xml_filename": self.xml_filename,
            "barcode_source": self.barcode_source,
            "status": self.status.value if isinstance(self.status, InvoiceStatus) else self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "submitted_at": self.submitted_at.isoformat() if self.submitted_at else None,
            "submitted_by": self.submitted_by,
            "synced_at": self.synced_at.isoformat() if self.synced_at else None,
            "synced_by": self.synced_by,
            "notes": self.notes,
            "items": [item.to_dict() for item in self.items] if self.items else [],
            "total_items": len(self.items) if self.items else 0,
            "total_quantity": sum(item.quantity for item in self.items) if self.items else 0
        }


class PendingInvoiceItem(Base):
    """
    Individual product item in a pending invoice.
    Stores product details from XML with bodeguero corrections.
    """

    __tablename__ = "pending_invoice_items"

    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey("pending_invoices.id"), nullable=False)

    # Product info from XML
    codigo_original = Column(String(100), nullable=False)
    product_name = Column(String(255), nullable=False)

    # Quantities (editable by bodeguero)
    quantity = Column(Float, nullable=False)  # Current quantity (bodeguero can edit)
    cantidad_original = Column(Float, nullable=False)  # Original from XML (reference)

    # Barcode (editable by bodeguero)
    barcode = Column(String(100), nullable=True, index=True)

    # Prices (hidden from bodeguero)
    unit_price = Column(Float, nullable=True)
    total_price = Column(Float, nullable=True)

    # Manual sale price (editable by admin, overrides calculated price)
    manual_sale_price = Column(Float, nullable=True)  # Price with IVA, manually set by admin

    # Tracking
    modified_by_bodeguero = Column(Boolean, default=False, nullable=False)

    # Exclusion (admin can exclude items like "TRANSPORTE" from sync)
    is_excluded = Column(Boolean, default=False, nullable=False)
    excluded_reason = Column(String(255), nullable=True)

    # Odoo sync results
    product_id = Column(Integer, nullable=True)  # Odoo product ID after sync
    sync_success = Column(Boolean, nullable=True)
    sync_error = Column(Text, nullable=True)

    # Relationship to invoice
    invoice = relationship("PendingInvoice", back_populates="items")

    def __repr__(self) -> str:
        return f"<PendingInvoiceItem(id={self.id}, codigo='{self.codigo_original}', qty={self.quantity})>"

    def to_dict(self) -> dict:
        """Convert item to dictionary representation."""
        return {
            "id": self.id,
            "invoice_id": self.invoice_id,
            "codigo_original": self.codigo_original,
            "product_name": self.product_name,
            "quantity": self.quantity,
            "cantidad_original": self.cantidad_original,
            "barcode": self.barcode,
            "unit_price": self.unit_price,
            "total_price": self.total_price,
            "manual_sale_price": self.manual_sale_price,
            "modified_by_bodeguero": self.modified_by_bodeguero,
            "is_excluded": self.is_excluded,
            "excluded_reason": self.excluded_reason,
            "product_id": self.product_id,
            "sync_success": self.sync_success,
            "sync_error": self.sync_error
        }
