"""
Transfer service for managing product transfers between principal and branch.
Two-step process: prepare (validate) then confirm (execute).
"""
from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from app.infrastructure.odoo import OdooClient
from app.schemas.transfer import (
    TransferItem,
    TransferResponse,
    TransferProductDetail,
    TransferValidationError,
    TransferValidationResponse,
    PendingTransferResponse,
    PendingTransferListResponse
)
from app.schemas.product import ProductInput
from app.schemas.auth import UserInfo
from app.core.constants import OdooModel, MAX_TRANSFER_PERCENTAGE
from app.core.exceptions import (
    TransferError,
    InsufficientStockError,
    ProductNotFoundError
)
from app.utils.formatters import format_decimal_for_odoo
from app.models import PendingTransfer, PendingTransferItem, TransferStatus


class TransferService:
    """Service for transfer operations between locations."""

    def __init__(self, principal_client: OdooClient, branch_client: OdooClient = None, db: Session = None):
        """
        Initialize transfer service.

        Args:
            principal_client: Authenticated principal Odoo client
            branch_client: Authenticated branch Odoo client (optional, for confirm)
            db: Database session (optional, for persistence)
        """
        self.principal_client = principal_client
        self.branch_client = branch_client
        self.db = db

    def prepare_transfer_with_details(self, items: List[TransferItem]) -> tuple[TransferResponse, List[Dict]]:
        """
        Prepare transfer and return both response and processed products.
        Used by router to save to database.
        """
        processed_products = []
        errors = []

        for item in items:
            try:
                # Search product
                products = self.principal_client.search_read(
                    OdooModel.PRODUCT_PRODUCT,
                    domain=[['barcode', '=', item.barcode]],
                    fields=['id', 'name', 'qty_available', 'standard_price',
                            'list_price', 'tracking', 'available_in_pos'],
                    limit=1
                )

                if not products:
                    errors.append(f"Product not found: {item.barcode}")
                    continue

                product = products[0]
                available_stock = product.get('qty_available', 0)
                max_allowed = int(available_stock * MAX_TRANSFER_PERCENTAGE)

                # Validate stock
                if item.quantity > available_stock:
                    errors.append(
                        f"Insufficient stock for {product['name']}: "
                        f"requested {item.quantity}, available {available_stock}"
                    )
                    continue

                if item.quantity > max_allowed:
                    errors.append(
                        f"Exceeds {int(MAX_TRANSFER_PERCENTAGE * 100)}% limit for {product['name']}: "
                        f"requested {item.quantity}, max allowed {max_allowed}"
                    )
                    continue

                # Add to processed list
                processed_products.append({
                    'product_id': product['id'],
                    'name': product['name'],
                    'barcode': item.barcode,
                    'quantity': item.quantity,
                    'standard_price': product['standard_price'],
                    'list_price': product['list_price'],
                    'tracking': product.get('tracking', 'none'),
                    'available_in_pos': product.get('available_in_pos', True),
                    'stock_before': available_stock
                })

            except Exception as e:
                errors.append(f"Error processing {item.barcode}: {str(e)}")

        if not processed_products:
            return TransferResponse(
                success=False,
                message="No products could be processed for transfer",
                processed_count=0,
                inventory_reduced=False
            ), []

        # Generate XML for branch upload
        xml_content = self._generate_transfer_xml(processed_products)

        # Create product details list
        product_details = [
            TransferProductDetail(
                barcode=p['barcode'],
                name=p['name'],
                quantity_requested=p['quantity'],
                quantity_transferred=0,
                stock_before=p['stock_before'],
                stock_after=p['stock_before'],
                success=True
            )
            for p in processed_products
        ]

        message = f"Transfer prepared: {len(processed_products)} products. "
        if errors:
            message += f"{len(errors)} errors. "
        message += "INVENTORY NOT REDUCED - requires confirmation."

        response = TransferResponse(
            success=True,
            message=message,
            xml_content=xml_content,
            processed_count=len(processed_products),
            inventory_reduced=False,
            products=product_details
        )

        return response, processed_products

    def prepare_transfer(self, items: List[TransferItem]) -> TransferResponse:
        """
        Prepare transfer - validate stock but DO NOT reduce inventory.

        Args:
            items: List of transfer items

        Returns:
            Transfer response with validation results

        Raises:
            TransferError: If validation fails
        """
        processed_products = []
        errors = []

        for item in items:
            try:
                # Search product
                products = self.principal_client.search_read(
                    OdooModel.PRODUCT_PRODUCT,
                    domain=[['barcode', '=', item.barcode]],
                    fields=['id', 'name', 'qty_available', 'standard_price',
                            'list_price', 'tracking', 'available_in_pos'],
                    limit=1
                )

                if not products:
                    errors.append(f"Product not found: {item.barcode}")
                    continue

                product = products[0]
                available_stock = product.get('qty_available', 0)
                max_allowed = int(available_stock * MAX_TRANSFER_PERCENTAGE)

                # Validate stock
                if item.quantity > available_stock:
                    errors.append(
                        f"Insufficient stock for {product['name']}: "
                        f"requested {item.quantity}, available {available_stock}"
                    )
                    continue

                if item.quantity > max_allowed:
                    errors.append(
                        f"Exceeds {int(MAX_TRANSFER_PERCENTAGE * 100)}% limit for {product['name']}: "
                        f"requested {item.quantity}, max allowed {max_allowed}"
                    )
                    continue

                # Add to processed list
                processed_products.append({
                    'product_id': product['id'],
                    'name': product['name'],
                    'barcode': item.barcode,
                    'quantity': item.quantity,
                    'standard_price': product['standard_price'],
                    'list_price': product['list_price'],
                    'tracking': product.get('tracking', 'none'),
                    'available_in_pos': product.get('available_in_pos', True),
                    'stock_before': available_stock
                })

            except Exception as e:
                errors.append(f"Error processing {item.barcode}: {str(e)}")

        if not processed_products:
            return TransferResponse(
                success=False,
                message="No products could be processed for transfer",
                processed_count=0,
                inventory_reduced=False
            )

        # Generate XML for branch upload
        xml_content = self._generate_transfer_xml(processed_products)

        # Create product details list
        product_details = [
            TransferProductDetail(
                barcode=p['barcode'],
                name=p['name'],
                quantity_requested=p['quantity'],
                quantity_transferred=0,  # Not transferred yet
                stock_before=p['stock_before'],
                stock_after=p['stock_before'],  # Not changed yet
                success=True
            )
            for p in processed_products
        ]

        message = f"Transfer prepared: {len(processed_products)} products. "
        if errors:
            message += f"{len(errors)} errors. "
        message += "INVENTORY NOT REDUCED - requires confirmation."

        return TransferResponse(
            success=True,
            message=message,
            xml_content=xml_content,
            processed_count=len(processed_products),
            inventory_reduced=False,
            products=product_details
        )

    def confirm_transfer(self, items: List[TransferItem]) -> TransferResponse:
        """
        Confirm transfer - ACTUALLY reduce inventory in principal and add to branch.

        Requires both principal and branch clients to be authenticated.

        Args:
            items: List of transfer items

        Returns:
            Transfer response with execution results

        Raises:
            TransferError: If branch client not provided or transfer fails
        """
        if not self.branch_client:
            raise TransferError("Branch client required for transfer confirmation")

        processed_products = []
        errors = []

        for item in items:
            try:
                # Get product from principal
                principal_products = self.principal_client.search_read(
                    OdooModel.PRODUCT_PRODUCT,
                    domain=[['barcode', '=', item.barcode]],
                    fields=['id', 'name', 'qty_available', 'standard_price',
                            'list_price', 'tracking', 'available_in_pos'],
                    limit=1
                )

                if not principal_products:
                    errors.append(f"Product not found in principal: {item.barcode}")
                    continue

                principal_product = principal_products[0]
                principal_stock_before = principal_product.get('qty_available', 0)

                # Validate stock again
                if item.quantity > principal_stock_before:
                    errors.append(
                        f"Insufficient stock in principal for {principal_product['name']}: "
                        f"requested {item.quantity}, available {principal_stock_before}"
                    )
                    continue

                # STEP 1: Reduce inventory in principal
                self._reduce_stock(
                    self.principal_client,
                    principal_product['id'],
                    item.quantity
                )

                # STEP 2: Find or create product in branch
                branch_products = self.branch_client.search_read(
                    OdooModel.PRODUCT_PRODUCT,
                    domain=[['barcode', '=', item.barcode]],
                    fields=['id', 'name', 'qty_available'],
                    limit=1
                )

                if not branch_products:
                    # Create product in branch
                    branch_product_id = self._create_product_in_branch(
                        item.barcode,
                        principal_product
                    )
                    branch_stock_before = 0
                else:
                    branch_product_id = branch_products[0]['id']
                    branch_stock_before = branch_products[0].get('qty_available', 0)

                    # Sync product data with principal
                    self._sync_product_data(
                        branch_product_id,
                        principal_product
                    )

                # STEP 3: Add inventory to branch
                self._add_stock(
                    self.branch_client,
                    branch_product_id,
                    item.quantity
                )

                # Add to processed list
                processed_products.append({
                    'name': principal_product['name'],
                    'barcode': item.barcode,
                    'quantity': item.quantity,
                    'standard_price': principal_product['standard_price'],
                    'list_price': principal_product['list_price'],
                    'stock_before_principal': principal_stock_before,
                    'stock_before_branch': branch_stock_before
                })

            except Exception as e:
                errors.append(f"Error confirming {item.barcode}: {str(e)}")
                # Try to rollback if possible (this is basic, not transactional)

        if not processed_products:
            return TransferResponse(
                success=False,
                message="No products could be confirmed for transfer",
                processed_count=0,
                inventory_reduced=False
            )

        # Generate XML for record
        xml_content = self._generate_transfer_xml(processed_products)

        message = f"Transfer CONFIRMED! {len(processed_products)} products. "
        message += "Inventory reduced in principal and added to branch."
        if errors:
            message += f" {len(errors)} errors occurred."

        return TransferResponse(
            success=True,
            message=message,
            xml_content=xml_content,
            processed_count=len(processed_products),
            inventory_reduced=True
        )

    def validate_transfer(self, items: List[TransferItem]) -> TransferValidationResponse:
        """
        Validate transfer items without making changes.

        Args:
            items: List of transfer items

        Returns:
            Validation response with errors and warnings
        """
        errors = []
        warnings = []

        for item in items:
            try:
                products = self.principal_client.search_read(
                    OdooModel.PRODUCT_PRODUCT,
                    domain=[['barcode', '=', item.barcode]],
                    fields=['id', 'name', 'qty_available'],
                    limit=1
                )

                if not products:
                    errors.append(TransferValidationError(
                        barcode=item.barcode,
                        product_name="Unknown",
                        error_type="not_found",
                        requested_quantity=item.quantity,
                        available_quantity=0
                    ))
                    continue

                product = products[0]
                available = product.get('qty_available', 0)
                max_allowed = int(available * MAX_TRANSFER_PERCENTAGE)

                if item.quantity > available:
                    errors.append(TransferValidationError(
                        barcode=item.barcode,
                        product_name=product['name'],
                        error_type="insufficient_stock",
                        requested_quantity=item.quantity,
                        available_quantity=available
                    ))
                elif item.quantity > max_allowed:
                    errors.append(TransferValidationError(
                        barcode=item.barcode,
                        product_name=product['name'],
                        error_type="exceeds_limit",
                        requested_quantity=item.quantity,
                        available_quantity=available,
                        max_allowed_quantity=max_allowed
                    ))
                elif item.quantity > available * 0.3:
                    # Warning for transfers > 30%
                    warnings.append(
                        f"{product['name']}: transferring {item.quantity}/{available} "
                        f"({int(item.quantity/available*100)}%)"
                    )

            except Exception as e:
                errors.append(TransferValidationError(
                    barcode=item.barcode,
                    product_name="Unknown",
                    error_type="error",
                    requested_quantity=item.quantity,
                    available_quantity=0
                ))

        return TransferValidationResponse(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )

    # Persistence methods for pending transfers

    def save_pending_transfer(
        self,
        items: List[TransferItem],
        user: UserInfo,
        product_details: List[Dict]
    ) -> PendingTransferResponse:
        """
        Save a prepared transfer to database for later confirmation.

        Args:
            items: List of transfer items
            user: User who prepared the transfer
            product_details: Detailed product information from validation

        Returns:
            Created pending transfer

        Raises:
            TransferError: If database save fails
        """
        if not self.db:
            raise TransferError("Database session required for saving transfers")

        try:
            # Create pending transfer
            pending_transfer = PendingTransfer(
                user_id=user.user_id,
                username=user.username,
                status=TransferStatus.PENDING
            )
            self.db.add(pending_transfer)
            self.db.flush()  # Get the ID

            # Create transfer items
            for item, details in zip(items, product_details):
                transfer_item = PendingTransferItem(
                    transfer_id=pending_transfer.id,
                    barcode=item.barcode,
                    product_id=details.get('product_id', 0),
                    product_name=details['name'],
                    quantity=item.quantity,
                    available_stock=int(details['stock_before']),
                    unit_price=details.get('list_price', 0)
                )
                self.db.add(transfer_item)

            self.db.commit()
            self.db.refresh(pending_transfer)

            return PendingTransferResponse.model_validate(pending_transfer)

        except Exception as e:
            self.db.rollback()
            raise TransferError(f"Failed to save pending transfer: {str(e)}")

    def get_pending_transfers(self, status: Optional[str] = None) -> PendingTransferListResponse:
        """
        Get list of pending transfers from database.

        Args:
            status: Optional status filter (pending, confirmed, cancelled)

        Returns:
            List of pending transfers
        """
        if not self.db:
            raise TransferError("Database session required for fetching transfers")

        query = self.db.query(PendingTransfer)

        if status:
            query = query.filter(PendingTransfer.status == status)
        else:
            # Default to only pending if no status specified
            query = query.filter(PendingTransfer.status == TransferStatus.PENDING)

        transfers = query.order_by(PendingTransfer.created_at.desc()).all()

        return PendingTransferListResponse(
            transfers=[PendingTransferResponse.model_validate(t) for t in transfers],
            total=len(transfers)
        )

    def get_pending_transfer_by_id(self, transfer_id: int) -> Optional[PendingTransferResponse]:
        """
        Get a specific pending transfer by ID.

        Args:
            transfer_id: Transfer ID

        Returns:
            Pending transfer or None if not found
        """
        if not self.db:
            raise TransferError("Database session required")

        transfer = self.db.query(PendingTransfer).filter(
            PendingTransfer.id == transfer_id
        ).first()

        if not transfer:
            return None

        return PendingTransferResponse.model_validate(transfer)

    def update_transfer_status(
        self,
        transfer_id: int,
        status: TransferStatus,
        confirmed_by: Optional[str] = None
    ) -> PendingTransferResponse:
        """
        Update the status of a pending transfer.

        Args:
            transfer_id: Transfer ID
            status: New status
            confirmed_by: Username of admin who confirmed (if confirming)

        Returns:
            Updated pending transfer

        Raises:
            TransferError: If transfer not found or update fails
        """
        if not self.db:
            raise TransferError("Database session required")

        transfer = self.db.query(PendingTransfer).filter(
            PendingTransfer.id == transfer_id
        ).first()

        if not transfer:
            raise TransferError(f"Transfer {transfer_id} not found")

        try:
            from app.utils.timezone import get_ecuador_now

            transfer.status = status
            transfer.updated_at = get_ecuador_now().replace(tzinfo=None)

            if status == TransferStatus.CONFIRMED and confirmed_by:
                transfer.confirmed_at = get_ecuador_now().replace(tzinfo=None)
                transfer.confirmed_by = confirmed_by

            self.db.commit()
            self.db.refresh(transfer)

            return PendingTransferResponse.model_validate(transfer)

        except Exception as e:
            self.db.rollback()
            raise TransferError(f"Failed to update transfer status: {str(e)}")

    # Private helper methods

    def _reduce_stock(self, client: OdooClient, product_id: int, quantity: float) -> None:
        """Reduce stock quantity in a location."""
        # Get stock location
        locations = client.search(
            OdooModel.STOCK_LOCATION,
            domain=[['usage', '=', 'internal']],
            limit=1
        )

        if not locations:
            raise TransferError("Stock location not found")

        location_id = locations[0]

        # Get quant
        quants = client.search_read(
            OdooModel.STOCK_QUANT,
            domain=[
                ['product_id', '=', product_id],
                ['location_id', '=', location_id]
            ],
            fields=['quantity'],
            limit=1
        )

        if not quants:
            raise TransferError(f"No stock quant found for product {product_id}")

        current_qty = quants[0]['quantity']
        new_qty = current_qty - quantity

        if new_qty < 0:
            raise InsufficientStockError("Product", current_qty, quantity)

        # Update quant
        client.write(
            OdooModel.STOCK_QUANT,
            [quants[0]['id']],
            {'quantity': format_decimal_for_odoo(new_qty)}
        )

    def _add_stock(self, client: OdooClient, product_id: int, quantity: float) -> None:
        """Add stock quantity in a location."""
        # Get stock location
        locations = client.search(
            OdooModel.STOCK_LOCATION,
            domain=[['usage', '=', 'internal']],
            limit=1
        )

        if not locations:
            raise TransferError("Stock location not found")

        location_id = locations[0]

        # Get or create quant
        quants = client.search_read(
            OdooModel.STOCK_QUANT,
            domain=[
                ['product_id', '=', product_id],
                ['location_id', '=', location_id]
            ],
            fields=['quantity'],
            limit=1
        )

        if quants:
            # Update existing
            current_qty = quants[0]['quantity']
            new_qty = current_qty + quantity

            client.write(
                OdooModel.STOCK_QUANT,
                [quants[0]['id']],
                {'quantity': format_decimal_for_odoo(new_qty)}
            )
        else:
            # Create new
            client.create(
                OdooModel.STOCK_QUANT,
                {
                    'product_id': product_id,
                    'location_id': location_id,
                    'quantity': format_decimal_for_odoo(quantity)
                }
            )

    def _create_product_in_branch(self, barcode: str, principal_product: Dict) -> int:
        """Create product in branch with data from principal."""
        product_data = {
            'name': principal_product['name'],
            'barcode': barcode,
            'standard_price': format_decimal_for_odoo(principal_product['standard_price']),
            'list_price': format_decimal_for_odoo(principal_product['list_price']),
            'type': 'consu',
            'tracking': 'none',  # Default for branch
            'available_in_pos': True
        }

        return self.branch_client.create(OdooModel.PRODUCT_PRODUCT, product_data)

    def _sync_product_data(self, branch_product_id: int, principal_product: Dict) -> None:
        """Sync product data from principal to branch."""
        update_data = {
            'name': principal_product['name'],
            'standard_price': format_decimal_for_odoo(principal_product['standard_price']),
            'list_price': format_decimal_for_odoo(principal_product['list_price'])
        }

        self.branch_client.write(
            OdooModel.PRODUCT_PRODUCT,
            [branch_product_id],
            update_data
        )

    def _generate_transfer_xml(self, products: List[Dict]) -> str:
        """Generate XML content for transfer."""
        xml_lines = ['<?xml version="1.0" encoding="UTF-8"?>']
        xml_lines.append('<transfer>')

        for product in products:
            xml_lines.append('  <product>')
            xml_lines.append(f'    <name>{product["name"]}</name>')
            xml_lines.append(f'    <barcode>{product["barcode"]}</barcode>')
            xml_lines.append(f'    <quantity>{product["quantity"]}</quantity>')
            xml_lines.append(f'    <standard_price>{product["standard_price"]}</standard_price>')
            xml_lines.append(f'    <list_price>{product["list_price"]}</list_price>')
            xml_lines.append('  </product>')

        xml_lines.append('</transfer>')

        return '\n'.join(xml_lines)
