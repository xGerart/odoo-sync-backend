"""
Odoo locations configuration service.
"""
from typing import Dict, List
from pydantic import BaseModel
from .config import settings


class OdooLocation(BaseModel):
    """Odoo location configuration."""
    id: str
    name: str
    url: str
    database: str
    port: int


class LocationService:
    """Service for managing Odoo locations."""

    @staticmethod
    def get_available_locations() -> List[OdooLocation]:
        """
        Get list of available Odoo locations from environment.

        Returns:
            List of OdooLocation objects
        """
        locations = []

        # Local Principal
        if settings.ODOO_PRINCIPAL_URL and settings.ODOO_PRINCIPAL_DB:
            locations.append(OdooLocation(
                id="principal",
                name="Local Principal",
                url=settings.ODOO_PRINCIPAL_URL,
                database=settings.ODOO_PRINCIPAL_DB,
                port=settings.ODOO_PRINCIPAL_PORT
            ))

        # Local Sucursal
        if settings.ODOO_SUCURSAL_URL and settings.ODOO_SUCURSAL_DB:
            locations.append(OdooLocation(
                id="sucursal",
                name="Local Sucursal",
                url=settings.ODOO_SUCURSAL_URL,
                database=settings.ODOO_SUCURSAL_DB,
                port=settings.ODOO_SUCURSAL_PORT
            ))

        # Local Sucursal Sacha
        if settings.ODOO_SUCURSAL_SACHA_URL and settings.ODOO_SUCURSAL_SACHA_DB:
            locations.append(OdooLocation(
                id="sucursal_sacha",
                name="Local Sucursal Sacha",
                url=settings.ODOO_SUCURSAL_SACHA_URL,
                database=settings.ODOO_SUCURSAL_SACHA_DB,
                port=settings.ODOO_SUCURSAL_SACHA_PORT
            ))

        # Local Sucursal Lago
        if settings.ODOO_SUCURSAL_LAGO_URL and settings.ODOO_SUCURSAL_LAGO_DB:
            locations.append(OdooLocation(
                id="sucursal_lago",
                name="Local Sucursal Loreto",
                url=settings.ODOO_SUCURSAL_LAGO_URL,
                database=settings.ODOO_SUCURSAL_LAGO_DB,
                port=settings.ODOO_SUCURSAL_LAGO_PORT
            ))

        return locations

    @staticmethod
    def get_location_by_id(location_id: str) -> OdooLocation | None:
        """
        Get location configuration by ID.

        Args:
            location_id: Location identifier

        Returns:
            OdooLocation or None if not found
        """
        locations = LocationService.get_available_locations()
        for location in locations:
            if location.id == location_id:
                return location
        return None
