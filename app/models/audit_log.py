"""
Audit log model for tracking important actions.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from app.core.database import Base


class AuditLog(Base):
    """
    Audit log for tracking user actions.
    Useful for security and compliance.
    """

    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    action = Column(String(100), nullable=False)  # e.g., "product_sync", "transfer_confirm"
    resource = Column(String(100), nullable=True)  # e.g., "product", "transfer"
    details = Column(JSON, nullable=True)  # Additional context as JSON
    ip_address = Column(String(45), nullable=True)  # IPv4 or IPv6
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Relationship to user (optional since admins don't have user_id)
    user = relationship("User", backref="audit_logs", foreign_keys=[user_id])

    def __repr__(self) -> str:
        return f"<AuditLog(id={self.id}, action='{self.action}', user_id={self.user_id})>"

    def to_dict(self) -> dict:
        """Convert audit log to dictionary representation."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "action": self.action,
            "resource": self.resource,
            "details": self.details,
            "ip_address": self.ip_address,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
