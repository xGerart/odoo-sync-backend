"""
Odoo integration infrastructure.
"""
from app.infrastructure.odoo.client import OdooClient
from app.infrastructure.odoo.connection import OdooConnectionManager, odoo_manager, get_odoo_manager

__all__ = [
    "OdooClient",
    "OdooConnectionManager",
    "odoo_manager",
    "get_odoo_manager",
]
