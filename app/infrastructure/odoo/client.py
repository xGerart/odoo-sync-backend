"""
Odoo XML-RPC client for communication with Odoo server.
Handles authentication and basic CRUD operations.
"""
import xmlrpc.client
import ssl
from typing import List, Optional, Dict, Any
from app.schemas.common import OdooCredentials
from app.core.exceptions import OdooConnectionError, OdooOperationError


class OdooClient:
    """
    Odoo XML-RPC client for interacting with Odoo server.

    Handles connection, authentication, and basic CRUD operations
    on Odoo models via XML-RPC protocol.
    """

    def __init__(self, credentials: OdooCredentials):
        """
        Initialize Odoo client with credentials.

        Args:
            credentials: Odoo connection credentials
        """
        self.url = credentials.url
        self.db = credentials.database
        self.username = credentials.username
        self.password = credentials.password
        self.port = credentials.port
        self.verify_ssl = credentials.verify_ssl

        self.uid: Optional[int] = None
        self.odoo_version: Optional[str] = None

        # Setup XML-RPC connections
        self._setup_connections()

    def _setup_connections(self) -> None:
        """Setup XML-RPC server proxies with appropriate SSL context."""
        if self.url.startswith('https://'):
            ssl_context = ssl.create_default_context()

            if not self.verify_ssl:
                # Allow self-signed certificates
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE

            self.common = xmlrpc.client.ServerProxy(
                f'{self.url}/xmlrpc/2/common',
                context=ssl_context
            )
            self.models = xmlrpc.client.ServerProxy(
                f'{self.url}/xmlrpc/2/object',
                context=ssl_context
            )
        else:
            # HTTP connections (development only)
            self.common = xmlrpc.client.ServerProxy(f'{self.url}/xmlrpc/2/common')
            self.models = xmlrpc.client.ServerProxy(f'{self.url}/xmlrpc/2/object')

    def authenticate(self) -> dict:
        """
        Authenticate with Odoo server and get user ID.

        Returns:
            Dict with success status and user info

        Raises:
            OdooConnectionError: If connection or authentication fails
        """
        try:
            # Get version info
            version_info = self.common.version()
            if not version_info:
                raise OdooConnectionError("Could not retrieve Odoo version info")

            self.odoo_version = version_info.get('server_version', 'unknown')

            # Authenticate
            self.uid = self.common.authenticate(
                self.db, self.username, self.password, {}
            )

            if not self.uid:
                raise OdooConnectionError(
                    "Authentication failed - invalid credentials",
                    details={
                        "url": self.url,
                        "database": self.db,
                        "username": self.username
                    }
                )

            return {
                "success": True,
                "user_id": self.uid,
                "version": self.odoo_version,
                "database": self.db
            }

        except xmlrpc.client.Fault as e:
            raise OdooConnectionError(
                f"Odoo XML-RPC Fault: {e.faultString}",
                details={"fault_code": e.faultCode}
            )
        except Exception as e:
            raise OdooConnectionError(
                f"Failed to connect to Odoo: {str(e)}",
                details={"url": self.url, "error": str(e)}
            )

    def test_connection(self) -> bool:
        """
        Test if connection is alive and authenticated.

        Returns:
            True if connected and authenticated
        """
        try:
            if not self.uid:
                return False

            # Try a simple operation to verify connection
            self.execute_kw('res.users', 'check_access_rights', ['read'])
            return True
        except Exception:
            return False

    def execute_kw(
        self,
        model: str,
        method: str,
        args: List = None,
        kwargs: Dict = None,
        retry: int = 1
    ) -> Any:
        """
        Execute a method on an Odoo model.

        Args:
            model: Odoo model name (e.g., 'product.product')
            method: Method name (e.g., 'search', 'read', 'create')
            args: Positional arguments for the method
            kwargs: Keyword arguments for the method
            retry: Number of retries for connection errors

        Returns:
            Result from Odoo method execution

        Raises:
            OdooOperationError: If operation fails
        """
        if not self.uid:
            raise OdooConnectionError("Not authenticated - call authenticate() first")

        last_error = None
        for attempt in range(retry + 1):
            try:
                return self.models.execute_kw(
                    self.db,
                    self.uid,
                    self.password,
                    model,
                    method,
                    args or [],
                    kwargs or {}
                )
            except xmlrpc.client.Fault as e:
                raise OdooOperationError(
                    operation=f"{model}.{method}",
                    message=e.faultString,
                    details={
                        "fault_code": e.faultCode,
                        "args": args,
                        "kwargs": kwargs
                    }
                )
            except Exception as e:
                last_error = e
                error_str = str(e).lower()

                # Retry on connection errors (Idle, ConnectionReset, etc.)
                if attempt < retry and ('idle' in error_str or 'connection' in error_str or 'reset' in error_str):
                    # Recreate connections on idle/connection errors
                    self._setup_connections()
                    continue

                # No more retries or not a connection error
                raise OdooOperationError(
                    operation=f"{model}.{method}",
                    message=str(e)
                )

        # If we exhausted retries
        raise OdooOperationError(
            operation=f"{model}.{method}",
            message=f"Failed after {retry} retries: {str(last_error)}"
        )

    def search(
        self,
        model: str,
        domain: List = None,
        limit: Optional[int] = None,
        offset: int = 0,
        order: Optional[str] = None
    ) -> List[int]:
        """
        Search for records in Odoo.

        Args:
            model: Odoo model name
            domain: Search domain (Odoo format)
            limit: Maximum number of records to return
            offset: Number of records to skip
            order: Sort order

        Returns:
            List of record IDs
        """
        kwargs = {'offset': offset}
        if limit:
            kwargs['limit'] = limit
        if order:
            kwargs['order'] = order

        return self.execute_kw(
            model,
            'search',
            [domain or []],
            kwargs
        )

    def read(
        self,
        model: str,
        ids: List[int],
        fields: Optional[List[str]] = None
    ) -> List[Dict]:
        """
        Read records from Odoo.

        Args:
            model: Odoo model name
            ids: List of record IDs to read
            fields: List of field names to retrieve (None = all fields)

        Returns:
            List of record dictionaries
        """
        kwargs = {}
        if fields:
            kwargs['fields'] = fields

        return self.execute_kw(model, 'read', [ids], kwargs)

    def search_read(
        self,
        model: str,
        domain: List = None,
        fields: Optional[List[str]] = None,
        limit: Optional[int] = None,
        offset: int = 0,
        order: Optional[str] = None
    ) -> List[Dict]:
        """
        Search and read records in one operation.

        Args:
            model: Odoo model name
            domain: Search domain
            fields: Fields to retrieve
            limit: Maximum records
            offset: Skip records
            order: Sort order

        Returns:
            List of record dictionaries
        """
        kwargs = {'offset': offset}
        if fields:
            kwargs['fields'] = fields
        if limit:
            kwargs['limit'] = limit
        if order:
            kwargs['order'] = order

        return self.execute_kw(
            model,
            'search_read',
            [domain or []],
            kwargs
        )

    def create(self, model: str, values: Dict) -> int:
        """
        Create a new record in Odoo.

        Args:
            model: Odoo model name
            values: Field values for the new record

        Returns:
            ID of created record
        """
        return self.execute_kw(model, 'create', [values])

    def write(self, model: str, ids: List[int], values: Dict) -> bool:
        """
        Update existing records in Odoo.

        Args:
            model: Odoo model name
            ids: List of record IDs to update
            values: Field values to update

        Returns:
            True if successful
        """
        return self.execute_kw(model, 'write', [ids, values])

    def unlink(self, model: str, ids: List[int]) -> bool:
        """
        Delete records from Odoo.

        Args:
            model: Odoo model name
            ids: List of record IDs to delete

        Returns:
            True if successful
        """
        return self.execute_kw(model, 'unlink', [ids])

    def search_count(self, model: str, domain: List = None) -> int:
        """
        Count records matching domain.

        Args:
            model: Odoo model name
            domain: Search domain

        Returns:
            Number of matching records
        """
        return self.execute_kw(model, 'search_count', [domain or []])

    def fields_get(
        self,
        model: str,
        fields: Optional[List[str]] = None,
        attributes: Optional[List[str]] = None
    ) -> Dict:
        """
        Get field information for a model.

        Args:
            model: Odoo model name
            fields: Specific fields to get info for (None = all)
            attributes: Specific attributes to retrieve

        Returns:
            Dictionary of field information
        """
        args = []
        kwargs = {}

        if fields:
            args.append(fields)
        if attributes:
            kwargs['attributes'] = attributes

        return self.execute_kw(model, 'fields_get', args, kwargs)

    def get_odoo_version_major(self) -> int:
        """
        Get major version number of Odoo.

        Returns:
            Major version number (e.g., 18 for Odoo 18.0)
        """
        if not self.odoo_version:
            return 18  # Default to latest

        try:
            version_str = self.odoo_version

            # Handle saas format: "saas~18.2+e"
            if 'saas~' in version_str:
                version_str = version_str.split('saas~')[1].split('+')[0]

            major = int(version_str.split('.')[0])
            return major
        except (ValueError, AttributeError, IndexError):
            return 18  # Default

    def is_authenticated(self) -> bool:
        """Check if client is authenticated."""
        return self.uid is not None

    def update_stock_quantity(
        self,
        product_id: int,
        quantity: float,
        mode: str = 'replace',
        product_name: str = None
    ) -> None:
        """
        Update product stock quantity using stock.quant.

        Args:
            product_id: Product ID
            quantity: Quantity to set or add
            mode: 'replace' to set quantity, 'add' to add to existing quantity
            product_name: Product name for logging
        """
        # Get default internal location
        location_ids = self.search(
            'stock.location',
            domain=[['usage', '=', 'internal']],
            limit=1
        )

        if not location_ids:
            raise OdooOperationError(
                operation="update_stock_quantity",
                message="No internal stock location found"
            )

        location_id = location_ids[0]

        # Check if quant already exists
        quant_ids = self.search(
            'stock.quant',
            domain=[
                ['product_id', '=', product_id],
                ['location_id', '=', location_id]
            ]
        )

        final_quantity = quantity

        if quant_ids:
            if mode == 'add':
                # Get current quantity and add to it
                current_quant = self.read('stock.quant', [quant_ids[0]], fields=['quantity'])
                if current_quant:
                    current_qty = current_quant[0].get('quantity', 0)
                    final_quantity = current_qty + quantity

            # Update existing quant
            self.write('stock.quant', [quant_ids[0]], {'quantity': final_quantity})
        else:
            # Create new quant
            self.create('stock.quant', {
                'product_id': product_id,
                'location_id': location_id,
                'quantity': final_quantity
            })
