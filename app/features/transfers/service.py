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
                            'list_price', 'type', 'tracking', 'available_in_pos'],
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
                            'list_price', 'type', 'tracking', 'available_in_pos'],
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

    def confirm_transfer(
        self,
        items: List[TransferItem],
        transfer_id: Optional[int] = None,
        username: str = "admin"
    ) -> TransferResponse:
        """
        Confirm transfer - ACTUALLY reduce inventory in principal and add to branch.
        Now also captures before/after data and generates PDF report.

        Requires both principal and branch clients to be authenticated.

        Args:
            items: List of transfer items
            transfer_id: Optional transfer ID for report
            username: Username confirming the transfer

        Returns:
            Transfer response with execution results and PDF report

        Raises:
            TransferError: If branch client not provided or transfer fails
        """
        import logging
        from datetime import datetime
        logger = logging.getLogger(__name__)

        logger.info(f"=== CONFIRM TRANSFER START ===")
        logger.info(f"Transfer ID: {transfer_id}")
        logger.info(f"User: {username}")
        logger.info(f"Items to transfer: {len(items)}")
        for idx, item in enumerate(items):
            logger.info(f"  Item {idx+1}: {item.barcode} x {item.quantity}")

        if not self.branch_client:
            raise TransferError("Branch client required for transfer confirmation")

        # Data for PDF report
        origin_before = []
        origin_after = []
        destination_before = []
        destination_after = []
        new_products = []

        processed_products = []
        errors = []

        for item in items:
            logger.info(f"Processing item: {item.barcode} x {item.quantity}")
            try:
                logger.info(f"  Step 1: Reading product from principal...")
                # Get product from principal
                # Try to read with both type fields for version compatibility
                base_fields = ['id', 'name', 'qty_available', 'standard_price',
                              'list_price', 'tracking', 'available_in_pos']

                principal_product = None

                # Try with 'detailed_type' first (Odoo 17+)
                try:
                    logger.debug(f"  Trying to read with 'detailed_type' field...")
                    principal_products = self.principal_client.search_read(
                        OdooModel.PRODUCT_PRODUCT,
                        domain=[['barcode', '=', item.barcode]],
                        fields=base_fields + ['detailed_type'],
                        limit=1
                    )
                    if principal_products:
                        principal_product = principal_products[0]
                        logger.info(f"  ✓ Product found with detailed_type field")
                except Exception as e:
                    logger.debug(f"  'detailed_type' not available: {str(e)[:100]}")
                    # Field doesn't exist, will try with 'type' instead
                    pass

                # Fallback to 'type' field (Odoo 16 and earlier)
                if not principal_product:
                    try:
                        logger.debug(f"  Trying to read with 'type' field...")
                        principal_products = self.principal_client.search_read(
                            OdooModel.PRODUCT_PRODUCT,
                            domain=[['barcode', '=', item.barcode]],
                            fields=base_fields + ['type'],
                            limit=1
                        )
                        if principal_products:
                            principal_product = principal_products[0]
                            logger.info(f"  ✓ Product found with type field")
                    except Exception as e:
                        logger.error(f"  ✗ Error reading product: {str(e)}")
                        errors.append(f"Error reading product {item.barcode}: {str(e)}")
                        continue

                if not principal_product:
                    logger.error(f"  ✗ Product not found in principal: {item.barcode}")
                    errors.append(f"Product not found in principal: {item.barcode}")
                    continue

                logger.info(f"  Step 2: Capturing origin snapshot BEFORE...")
                # CAPTURE: Origin BEFORE
                origin_snapshot_before = self._capture_product_snapshot(
                    self.principal_client,
                    item.barcode,
                    principal_product['id']
                )
                if origin_snapshot_before:
                    origin_snapshot_before['quantity'] = item.quantity  # Add transfer quantity
                    origin_before.append(origin_snapshot_before)
                    logger.info(f"  ✓ Origin snapshot captured")

                principal_stock_before = principal_product.get('qty_available', 0)
                logger.info(f"  Stock available: {principal_stock_before}")

                # Validate stock again
                if item.quantity > principal_stock_before:
                    logger.error(f"  ✗ Insufficient stock: requested {item.quantity}, available {principal_stock_before}")
                    errors.append(
                        f"Insufficient stock in principal for {principal_product['name']}: "
                        f"requested {item.quantity}, available {principal_stock_before}"
                    )
                    continue

                logger.info(f"  Step 3: Reducing inventory in principal ({item.quantity} units)...")
                # STEP 1: Reduce inventory in principal
                self._reduce_stock(
                    self.principal_client,
                    principal_product['id'],
                    item.quantity
                )
                logger.info(f"  ✓ Inventory reduced in principal")

                logger.info(f"  Step 4: Capturing origin snapshot AFTER...")
                # CAPTURE: Origin AFTER
                origin_snapshot_after = self._capture_product_snapshot(
                    self.principal_client,
                    item.barcode,
                    principal_product['id']
                )
                if origin_snapshot_after:
                    origin_after.append(origin_snapshot_after)
                    logger.info(f"  ✓ Origin AFTER snapshot captured")

                logger.info(f"  Step 5: Searching product in branch...")
                # STEP 2: Find or create product in branch
                branch_products = self.branch_client.search_read(
                    OdooModel.PRODUCT_PRODUCT,
                    domain=[['barcode', '=', item.barcode]],
                    fields=['id', 'name', 'qty_available', 'standard_price', 'list_price'],
                    limit=1
                )

                is_new_product = not branch_products

                if is_new_product:
                    logger.info(f"  → Product NOT found in branch - will create new")
                    # Product doesn't exist in branch - will be created
                    branch_product_id = self._create_product_in_branch(
                        item.barcode,
                        principal_product
                    )
                    branch_stock_before = 0

                    # Add to new products list for PDF
                    new_products.append({
                        'barcode': item.barcode,
                        'name': principal_product['name'],
                        'standard_price': principal_product['standard_price'],
                        'list_price': principal_product['list_price'],
                        'quantity': item.quantity
                    })
                else:
                    logger.info(f"  → Product FOUND in branch - will update")
                    # Product exists - capture BEFORE updating
                    branch_product = branch_products[0]
                    branch_product_id = branch_product['id']
                    logger.info(f"  Branch product ID: {branch_product_id}")

                    dest_snapshot_before = self._capture_product_snapshot(
                        self.branch_client,
                        item.barcode,
                        branch_product_id
                    )
                    if dest_snapshot_before:
                        destination_before.append(dest_snapshot_before)
                        logger.info(f"  ✓ Destination BEFORE snapshot captured")

                    branch_stock_before = branch_product.get('qty_available', 0)
                    logger.info(f"  Current branch stock: {branch_stock_before}")

                    # Sync product data with principal (updates prices)
                    logger.info(f"  Step 6: Syncing product data to branch...")
                    self._sync_product_data(
                        branch_product_id,
                        principal_product
                    )
                    logger.info(f"  ✓ Product data synced")

                logger.info(f"  Step 7: Adding inventory to branch ({item.quantity} units)...")
                # STEP 3: Add inventory to branch
                self._add_stock(
                    self.branch_client,
                    branch_product_id,
                    item.quantity
                )
                logger.info(f"  ✓ Inventory added to branch")

                # CAPTURE: Destination AFTER (for updated products)
                if not is_new_product:
                    dest_snapshot_after = self._capture_product_snapshot(
                        self.branch_client,
                        item.barcode,
                        branch_product_id
                    )
                    if dest_snapshot_after:
                        destination_after.append(dest_snapshot_after)

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
                logger.error(f"Error confirming {item.barcode}: {str(e)}")
                errors.append(f"Error confirming {item.barcode}: {str(e)}")

        if not processed_products:
            error_details = "; ".join(errors) if errors else "Unknown error"
            return TransferResponse(
                success=False,
                message=f"No products could be confirmed for transfer. Errors: {error_details}",
                processed_count=0,
                inventory_reduced=False
            )

        # Generate XML for record
        xml_content = self._generate_transfer_xml(processed_products)

        # Generate PDF report
        pdf_content = None
        pdf_filename = None
        try:
            transfer_data = {
                'id': transfer_id or 'new',
                'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'username': username,
                'confirmed_by': username,
                'destination': 'Sucursal',
                'total_items': len(processed_products),
                'total_quantity': sum(p['quantity'] for p in processed_products)
            }

            pdf_content, pdf_filename = self._generate_transfer_report_pdf(
                transfer_data=transfer_data,
                origin_before=origin_before,
                origin_after=origin_after,
                destination_before=destination_before,
                destination_after=destination_after,
                new_products=new_products
            )
            logger.info(f"PDF report generated: {pdf_filename}")
        except Exception as e:
            logger.error(f"Error generating PDF report: {str(e)}")
            # Continue even if PDF generation fails

        message = f"Transfer CONFIRMED! {len(processed_products)} products. "
        message += "Inventory reduced in principal and added to branch."
        if errors:
            message += f" {len(errors)} errors occurred."

        return TransferResponse(
            success=True,
            message=message,
            xml_content=xml_content,
            pdf_content=pdf_content,
            pdf_filename=pdf_filename,
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
        Status depends on user role:
        - CAJERO: PENDING_VERIFICATION (requires bodeguero verification)
        - BODEGUERO/ADMIN: PENDING (goes directly to admin for confirmation)

        Args:
            items: List of transfer items
            user: User who prepared the transfer
            product_details: Detailed product information from validation

        Returns:
            Created pending transfer

        Raises:
            TransferError: If database save fails
        """
        from app.core.constants import UserRole

        if not self.db:
            raise TransferError("Database session required for saving transfers")

        try:
            # Determine status based on user role
            if user.role == UserRole.CAJERO:
                status = TransferStatus.PENDING_VERIFICATION
            else:  # BODEGUERO or ADMIN
                status = TransferStatus.PENDING

            # Create pending transfer
            pending_transfer = PendingTransfer(
                user_id=user.user_id,
                username=user.username,
                created_by_role=user.role.value,  # Store role as string
                status=status
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

    def get_pending_transfers(
        self,
        status: Optional[str] = None,
        user: Optional[UserInfo] = None
    ) -> PendingTransferListResponse:
        """
        Get list of pending transfers from database.
        Filters based on user role:
        - Admin: only transfers with status='pending' (ready to confirm)
        - Bodeguero: only transfers with status='pending_verification' (from cajeros)
        - Cajero: only their own transfers

        Args:
            status: Optional status filter to override role-based filtering
            user: Optional user info for role-based filtering

        Returns:
            List of pending transfers
        """
        from sqlalchemy.orm import selectinload
        from app.core.constants import UserRole

        if not self.db:
            raise TransferError("Database session required for fetching transfers")

        query = self.db.query(PendingTransfer)

        # Apply status filter based on explicit parameter or user role
        if status:
            # Explicit status filter takes precedence
            query = query.filter(PendingTransfer.status == status)
        elif user:
            # Apply role-based filtering
            if user.role == UserRole.ADMIN:
                # Admin sees only transfers ready for confirmation
                query = query.filter(PendingTransfer.status == TransferStatus.PENDING)
            elif user.role == UserRole.BODEGUERO:
                # Bodeguero sees only transfers needing verification
                query = query.filter(PendingTransfer.status == TransferStatus.PENDING_VERIFICATION)
            elif user.role == UserRole.CAJERO:
                # Cajero sees only their own transfers
                query = query.filter(PendingTransfer.user_id == user.user_id)
        else:
            # Default to only pending if no user or status specified
            query = query.filter(PendingTransfer.status == TransferStatus.PENDING)

        # Eager load items to avoid lazy loading issues
        transfers = query.options(selectinload(PendingTransfer.items)).order_by(PendingTransfer.created_at.desc()).all()

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

    def verify_transfer(
        self,
        transfer_id: int,
        items: List[TransferItem],
        verified_by: str
    ) -> PendingTransferResponse:
        """
        Verify a transfer prepared by cajero (bodeguero verification step).
        Changes status from PENDING_VERIFICATION to PENDING.
        Allows editing quantities before passing to admin.

        Args:
            transfer_id: Transfer ID to verify
            items: List of verified transfer items (may be edited from original)
            verified_by: Username of bodeguero verifying

        Returns:
            Updated pending transfer

        Raises:
            TransferError: If transfer not found, wrong status, or verification fails
        """
        if not self.db:
            raise TransferError("Database session required")

        # Find transfer
        transfer = self.db.query(PendingTransfer).filter(
            PendingTransfer.id == transfer_id,
            PendingTransfer.status == TransferStatus.PENDING_VERIFICATION
        ).first()

        if not transfer:
            raise TransferError(
                f"Transfer {transfer_id} not found or not in pending_verification status"
            )

        try:
            from app.utils.timezone import get_ecuador_now

            # Update items if they were edited
            if items:
                # Clear existing items
                self.db.query(PendingTransferItem).filter(
                    PendingTransferItem.transfer_id == transfer_id
                ).delete()

                # Add verified items (re-validate against Odoo)
                for item in items:
                    # Search product to get current data
                    products = self.principal_client.search_read(
                        OdooModel.PRODUCT_PRODUCT,
                        domain=[['barcode', '=', item.barcode]],
                        fields=['id', 'name', 'qty_available', 'standard_price', 'list_price'],
                        limit=1
                    )

                    if not products:
                        raise TransferError(f"Product {item.barcode} not found in Odoo")

                    product = products[0]

                    # Create new transfer item
                    transfer_item = PendingTransferItem(
                        transfer_id=transfer_id,
                        barcode=item.barcode,
                        product_id=product['id'],
                        product_name=product['name'],
                        quantity=item.quantity,
                        available_stock=int(product.get('qty_available', 0)),
                        unit_price=product.get('list_price', 0)
                    )
                    self.db.add(transfer_item)

            # Update transfer status and verification fields
            transfer.status = TransferStatus.PENDING
            transfer.verified_at = get_ecuador_now().replace(tzinfo=None)
            transfer.verified_by = verified_by
            transfer.updated_at = get_ecuador_now().replace(tzinfo=None)

            self.db.commit()
            self.db.refresh(transfer)

            return PendingTransferResponse.model_validate(transfer)

        except Exception as e:
            self.db.rollback()
            raise TransferError(f"Failed to verify transfer: {str(e)}")

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

    def _get_product_type_field_for_branch(self) -> dict:
        """
        Auto-detect correct product type field based on Odoo version.
        This method queries Odoo to find which field and values are available.
        """
        import logging
        logger = logging.getLogger(__name__)

        try:
            # Get field info for product.template to detect available fields
            field_info = self.branch_client.execute_kw(
                OdooModel.PRODUCT_TEMPLATE,
                'fields_get',
                args=[],  # Get all fields
                kwargs={'attributes': ['type', 'selection', 'string']}
            )

            # Check 'type' field first
            if 'type' in field_info and 'selection' in field_info['type']:
                selection_values = field_info['type']['selection']
                logger.info(f"[TYPE_DETECT] Found 'type' field with values: {selection_values}")

                available_types = [v for v, l in selection_values]

                # Try different type values in order of preference for storable products
                test_types = ['product', 'consu', 'service']

                for test_type in test_types:
                    if test_type in available_types:
                        logger.info(f"[TYPE_DETECT] Will use: type='{test_type}'")

                        # For 'consu' type, check if we need to set is_storable
                        if test_type == 'consu' and 'is_storable' in field_info:
                            logger.info(f"[TYPE_DETECT] Adding is_storable=True for consu type")
                            return {'type': test_type, 'is_storable': True}

                        return {'type': test_type}

                # Fallback to first available
                if available_types:
                    fallback_type = available_types[0]
                    logger.warning(f"[TYPE_DETECT] Fallback to: type='{fallback_type}'")
                    return {'type': fallback_type}

            # Check 'detailed_type' field for newer versions
            elif 'detailed_type' in field_info:
                logger.info(f"[TYPE_DETECT] Found 'detailed_type' field - using 'product'")
                return {'detailed_type': 'product'}

            else:
                logger.error(f"[TYPE_DETECT] No 'type' or 'detailed_type' field found!")
                return {}  # Return empty dict, let Odoo use defaults

        except Exception as e:
            logger.error(f"[TYPE_DETECT] Error detecting product type field: {e}")
            return {}  # Return empty dict on error

    def _create_product_in_branch(self, barcode: str, principal_product: Dict) -> int:
        """
        Create product in branch with data from principal.
        ALWAYS creates products as storable (product type) to enable inventory tracking.
        Handles Odoo version compatibility (type vs detailed_type fields).
        """
        import logging
        logger = logging.getLogger(__name__)

        # Get principal product type for logging
        principal_type = principal_product.get('detailed_type') or principal_product.get('type', 'consu')

        logger.info(f"[CREATE_BRANCH] Creating product in branch: {principal_product['name']} (barcode: {barcode})")
        logger.info(f"[CREATE_BRANCH] Principal type: {principal_type}")

        # Build basic product data
        product_data = {
            'name': principal_product['name'],
            'barcode': barcode,
            'standard_price': format_decimal_for_odoo(principal_product['standard_price']),
            'list_price': format_decimal_for_odoo(principal_product['list_price']),
            'tracking': principal_product.get('tracking', 'none'),
            'available_in_pos': True,
            'sale_ok': True,
            'purchase_ok': True,
        }

        # Auto-detect and add correct type field for this Odoo version
        type_field = self._get_product_type_field_for_branch()
        product_data.update(type_field)

        logger.info(f"[CREATE_BRANCH] Creating product with data: {type_field}")

        # Create product (this creates both template and variant)
        product_id = self.branch_client.create(OdooModel.PRODUCT_PRODUCT, product_data)
        logger.info(f"[CREATE_BRANCH] ✅ Product created with ID: {product_id}")

        return product_id

    def _sync_product_data(self, branch_product_id: int, principal_product: Dict) -> None:
        """
        Sync product data from principal to branch.
        Updates name, cost (standard_price), sale price (list_price), and ensures product is storable.
        """
        import logging
        logger = logging.getLogger(__name__)

        update_data = {
            'name': principal_product['name'],
            'standard_price': format_decimal_for_odoo(principal_product['standard_price']),
            'list_price': format_decimal_for_odoo(principal_product['list_price'])
        }

        logger.info(f"[SYNC_PRODUCT] Updating branch product {branch_product_id} with: {update_data}")

        self.branch_client.write(
            OdooModel.PRODUCT_PRODUCT,
            [branch_product_id],
            update_data
        )

        logger.info(f"[SYNC_PRODUCT] Product {branch_product_id} updated successfully")

        # Note: We don't try to change product type here because:
        # 1. In Odoo saas~18.2, type field is read-only
        # 2. Changing type after creation can cause issues
        # 3. Existing products should already have correct type
        # If a consumable product needs to be storable, delete and recreate it

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

    def _capture_product_snapshot(
        self,
        client: 'OdooClient',
        barcode: str,
        product_id: Optional[int] = None
    ) -> Optional[Dict]:
        """
        Capture complete product snapshot (stock, prices).

        Args:
            client: Odoo client (principal or branch)
            barcode: Product barcode
            product_id: Optional product ID (faster if known)

        Returns:
            Dict with product data or None if not found
        """
        try:
            if product_id:
                products = client.read(
                    OdooModel.PRODUCT_PRODUCT,
                    [product_id],
                    fields=['id', 'name', 'barcode', 'qty_available',
                            'standard_price', 'list_price']
                )
            else:
                products = client.search_read(
                    OdooModel.PRODUCT_PRODUCT,
                    domain=[['barcode', '=', barcode]],
                    fields=['id', 'name', 'barcode', 'qty_available',
                            'standard_price', 'list_price'],
                    limit=1
                )

            if not products:
                return None

            product = products[0]
            return {
                'id': product.get('id'),
                'name': product.get('name'),
                'barcode': product.get('barcode'),
                'qty_available': product.get('qty_available', 0),
                'standard_price': product.get('standard_price', 0),
                'list_price': product.get('list_price', 0)
            }

        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error capturing product snapshot for {barcode}: {e}")
            return None

    def _generate_transfer_report_pdf(
        self,
        transfer_data: Dict[str, Any],
        origin_before: List[Dict],
        origin_after: List[Dict],
        destination_before: List[Dict],
        destination_after: List[Dict],
        new_products: List[Dict]
    ) -> tuple[str, str]:
        """
        Generate PDF report for transfer.

        Returns:
            Tuple of (base64_pdf_content, pdf_filename)
        """
        import base64
        from datetime import datetime
        from app.utils.pdf_templates import TransferReport

        # Generate PDF
        report = TransferReport()
        pdf_buffer = report.generate(
            transfer_data=transfer_data,
            origin_before=origin_before,
            origin_after=origin_after,
            destination_before=destination_before,
            destination_after=destination_after,
            new_products=new_products
        )

        # Convert to base64
        pdf_content = base64.b64encode(pdf_buffer.getvalue()).decode('utf-8')

        # Generate filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        transfer_id = transfer_data.get('id', 'new')
        pdf_filename = f"transfer_report_{transfer_id}_{timestamp}.pdf"

        return pdf_content, pdf_filename
