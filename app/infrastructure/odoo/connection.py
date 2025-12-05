"""
Odoo connection manager.
Manages global Odoo client instances for principal and branch.
"""
from typing import Optional
from app.infrastructure.odoo.client import OdooClient
from app.schemas.common import OdooCredentials
from app.core.exceptions import OdooConnectionError


class OdooConnectionManager:
    """
    Manages Odoo client connections for principal and branch locations.

    This replaces the global odoo_client and branch_client variables
    with a more structured approach.
    """

    def __init__(self):
        self._principal_client: Optional[OdooClient] = None
        self._branch_client: Optional[OdooClient] = None

    def connect_principal(self, credentials: OdooCredentials) -> dict:
        """
        Connect to principal Odoo instance.

        Args:
            credentials: Odoo credentials for principal

        Returns:
            Connection result with user info

        Raises:
            OdooConnectionError: If connection fails
        """
        client = OdooClient(credentials)
        result = client.authenticate()

        self._principal_client = client
        return result

    def connect_branch(self, credentials: OdooCredentials) -> dict:
        """
        Connect to branch Odoo instance.

        Args:
            credentials: Odoo credentials for branch

        Returns:
            Connection result with user info

        Raises:
            OdooConnectionError: If connection fails
        """
        client = OdooClient(credentials)
        result = client.authenticate()

        self._branch_client = client
        return result

    def get_principal_client(self) -> OdooClient:
        """
        Get principal Odoo client.

        Returns:
            Principal Odoo client

        Raises:
            OdooConnectionError: If not connected
        """
        if not self._principal_client:
            raise OdooConnectionError(
                "No hay conexión a Odoo. Un administrador debe iniciar sesión primero.",
                is_session_expired=False  # Not a session expiry, just not connected yet
            )

        if not self._principal_client.is_authenticated():
            raise OdooConnectionError(
                "Sesión de Odoo expirada",
                is_session_expired=True  # This IS a session expiry
            )

        return self._principal_client

    def get_branch_client(self) -> OdooClient:
        """
        Get branch Odoo client.

        Returns:
            Branch Odoo client

        Raises:
            OdooConnectionError: If not connected
        """
        if not self._branch_client:
            raise OdooConnectionError(
                "Branch Odoo not connected - call connect_branch() first",
                is_session_expired=True
            )

        if not self._branch_client.is_authenticated():
            raise OdooConnectionError(
                "Branch Odoo session expired",
                is_session_expired=True
            )

        return self._branch_client

    def is_principal_connected(self) -> bool:
        """Check if principal is connected."""
        return self._principal_client is not None and self._principal_client.is_authenticated()

    def is_branch_connected(self) -> bool:
        """Check if branch is connected."""
        return self._branch_client is not None and self._branch_client.is_authenticated()

    def disconnect_principal(self) -> None:
        """Disconnect from principal."""
        self._principal_client = None

    def disconnect_branch(self) -> None:
        """Disconnect from branch."""
        self._branch_client = None

    def disconnect_all(self) -> None:
        """Disconnect from all Odoo instances."""
        self._principal_client = None
        self._branch_client = None

    def get_connection_status(self) -> dict:
        """
        Get status of all connections.

        Returns:
            Dictionary with connection status
        """
        return {
            "principal": {
                "connected": self.is_principal_connected(),
                "version": self._principal_client.odoo_version if self._principal_client else None,
                "database": self._principal_client.db if self._principal_client else None
            },
            "branch": {
                "connected": self.is_branch_connected(),
                "version": self._branch_client.odoo_version if self._branch_client else None,
                "database": self._branch_client.db if self._branch_client else None
            }
        }


# Global connection manager instance
odoo_manager = OdooConnectionManager()


def get_odoo_manager() -> OdooConnectionManager:
    """
    Dependency to get Odoo connection manager.

    Usage:
        @router.post("/sync")
        def sync_products(
            manager: OdooConnectionManager = Depends(get_odoo_manager)
        ):
            client = manager.get_principal_client()
            ...
    """
    return odoo_manager
