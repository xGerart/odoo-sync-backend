"""
Adjustment service for managing inventory adjustments.
Two-step process: prepare (validate) then confirm (execute in Odoo).
"""
from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.infrastructure.odoo import OdooClient
from app.schemas.adjustment import (
    AdjustmentItem,
    AdjustmentResponse,
    PendingAdjustmentResponse,
    PendingAdjustmentListResponse,
    PendingAdjustmentItemResponse,
    AdjustmentHistoryItemResponse,
    AdjustmentHistoryResponse
)
from app.schemas.auth import UserInfo
from app.core.constants import OdooModel
from app.models import (
    PendingAdjustment,
    PendingAdjustmentItem,
    AdjustmentStatus,
    AdjustmentType,
    AdjustmentReason
)
from app.utils.timezone import get_ecuador_now
import logging

logger = logging.getLogger(__name__)


class AdjustmentService:
    """Service for inventory adjustment operations."""

    def __init__(self, principal_client: OdooClient, db: Session = None):
        """
        Initialize adjustment service.

        Args:
            principal_client: Authenticated principal Odoo client
            db: Database session (for persistence)
        """
        self.principal_client = principal_client
        self.db = db

    def prepare_adjustment(self, items: List[AdjustmentItem], user: UserInfo) -> AdjustmentResponse:
        """
        Prepare adjustment - validate and save to database.
        Does NOT update inventory in Odoo yet.

        Args:
            items: List of adjustment items
            user: Current user info

        Returns:
            Adjustment response with validation results
        """
        logger.info(f"Preparing adjustment for user: {user.username}")
        logger.info(f"Items count: {len(items)}")

        if not items:
            return AdjustmentResponse(
                success=False,
                message="No items provided for adjustment",
                processed_count=0,
                inventory_updated=False
            )

        # Validate items and check if products exist
        validated_items = []
        errors = []

        for item in items:
            try:
                # Verify product exists in Odoo
                products = self.principal_client.search_read(
                    OdooModel.PRODUCT_PRODUCT,
                    domain=[['barcode', '=', item.barcode]],
                    fields=['id', 'name', 'qty_available', 'standard_price'],
                    limit=1
                )

                if not products:
                    errors.append(f"Product not found: {item.barcode}")
                    continue

                product = products[0]

                # Verify product_id matches
                if product['id'] != item.product_id:
                    logger.warning(f"Product ID mismatch for barcode {item.barcode}: expected {item.product_id}, got {product['id']}")

                validated_items.append(item)

            except Exception as e:
                logger.error(f"Error validating item {item.barcode}: {str(e)}")
                errors.append(f"Error validating {item.barcode}: {str(e)}")

        if not validated_items:
            return AdjustmentResponse(
                success=False,
                message=f"No valid items to process. Errors: {'; '.join(errors)}",
                processed_count=0,
                inventory_updated=False
            )

        # Save to database
        try:
            pending_adjustment = self.save_pending_adjustment(validated_items, user)

            message = f"Adjustment prepared successfully: {len(validated_items)} items. Awaiting admin confirmation."
            if errors:
                message += f" {len(errors)} items had errors."

            return AdjustmentResponse(
                success=True,
                message=message,
                processed_count=len(validated_items),
                inventory_updated=False
            )

        except Exception as e:
            logger.error(f"Error saving pending adjustment: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return AdjustmentResponse(
                success=False,
                message=f"Error saving adjustment: {str(e)}",
                processed_count=0,
                inventory_updated=False
            )

    def save_pending_adjustment(self, items: List[AdjustmentItem], user: UserInfo) -> PendingAdjustment:
        """
        Save pending adjustment to database.

        Args:
            items: List of adjustment items
            user: Current user info

        Returns:
            Created PendingAdjustment record
        """
        if not self.db:
            raise ValueError("Database session not provided")

        # Determine adjustment type from first item (all should be same type)
        adjustment_type = AdjustmentType(items[0].adjustment_type.value)

        # Create pending adjustment
        pending_adjustment = PendingAdjustment(
            user_id=user.user_id,
            username=user.username,
            adjustment_type=adjustment_type,
            status=AdjustmentStatus.PENDING
        )

        self.db.add(pending_adjustment)
        self.db.flush()  # Get the ID

        # Create adjustment items
        for item in items:
            adjustment_item = PendingAdjustmentItem(
                adjustment_id=pending_adjustment.id,
                barcode=item.barcode,
                product_id=item.product_id,
                product_name=item.product_name,
                quantity=item.quantity,
                available_stock=item.available_stock,
                adjustment_type=AdjustmentType(item.adjustment_type.value),
                reason=AdjustmentReason(item.reason.value),
                description=item.description,
                unit_price=item.unit_price,
                new_product_name=item.new_product_name,
                photo_url=item.photo_url
            )
            self.db.add(adjustment_item)

        self.db.commit()
        self.db.refresh(pending_adjustment)

        logger.info(f"Saved pending adjustment ID: {pending_adjustment.id}")
        return pending_adjustment

    def get_pending_adjustments(self) -> PendingAdjustmentListResponse:
        """
        Get all pending adjustments awaiting confirmation.

        Returns:
            List of pending adjustments
        """
        if not self.db:
            raise ValueError("Database session not provided")

        pending = self.db.query(PendingAdjustment).filter(
            PendingAdjustment.status == AdjustmentStatus.PENDING
        ).order_by(desc(PendingAdjustment.created_at)).all()

        adjustments = [PendingAdjustmentResponse.model_validate(adj) for adj in pending]

        return PendingAdjustmentListResponse(
            adjustments=adjustments,
            total=len(adjustments)
        )

    def confirm_adjustment(self, items: List[AdjustmentItem], user: UserInfo, adjustment_id: Optional[int] = None) -> AdjustmentResponse:
        """
        Confirm and execute adjustment in Odoo.
        Updates inventory quantities based on adjustment type.

        Args:
            items: List of adjustment items to confirm
            user: Current user (admin)
            adjustment_id: Optional ID of pending adjustment

        Returns:
            Adjustment response with execution results
        """
        logger.info(f"Confirming adjustment by user: {user.username}")
        logger.info(f"Adjustment ID: {adjustment_id}")
        logger.info(f"Items count: {len(items)}")

        if not items:
            return AdjustmentResponse(
                success=False,
                message="No items provided for confirmation",
                processed_count=0,
                inventory_updated=False
            )

        # Process each item and update in Odoo
        processed_count = 0
        errors = []

        for item in items:
            try:
                # Get current product info
                products = self.principal_client.search_read(
                    OdooModel.PRODUCT_PRODUCT,
                    domain=[['id', '=', item.product_id]],
                    fields=['id', 'name', 'qty_available'],
                    limit=1
                )

                if not products:
                    errors.append(f"Product not found: {item.barcode}")
                    continue

                product = products[0]
                current_stock = product.get('qty_available', 0)

                logger.info(f"Updating product {product['name']} (ID: {product['id']})")
                logger.info(f"Current stock: {current_stock}, Adjustment type: {item.adjustment_type.value}, Quantity: {item.quantity}")

                # Determine mode based on adjustment type
                # ADJUSTMENT (physical count) = replace the value
                # ENTRY/EXIT = add to existing (negative for exit)
                if item.adjustment_type.value == 'adjustment':
                    mode = 'replace'
                    quantity = item.quantity  # Use the exact counted quantity
                    logger.info(f"Physical count mode: replacing stock with {quantity}")
                else:
                    mode = 'add'
                    quantity = item.quantity  # Already signed (negative for exits)
                    logger.info(f"Entry/Exit mode: adding {quantity} to current stock")

                # Update stock quantity using stock.quant
                try:
                    self.principal_client.update_stock_quantity(
                        product_id=product['id'],
                        quantity=quantity,
                        mode=mode,
                        product_name=product['name']
                    )
                    logger.info(f"Successfully updated stock for product {product['id']}")
                except Exception as stock_error:
                    logger.error(f"Error updating stock: {str(stock_error)}")
                    errors.append(f"Failed to update stock for {item.barcode}")
                    continue

                # Update product name and photo if provided (only for ADJUSTMENT type)
                if item.adjustment_type.value == 'adjustment':
                    update_values = {}

                    logger.info(f"Checking for name/photo updates - new_product_name: '{item.new_product_name}', photo_url exists: {bool(item.photo_url)}")

                    if item.new_product_name and item.new_product_name.strip():
                        update_values['name'] = item.new_product_name.strip()
                        logger.info(f"Will update product name to: '{item.new_product_name.strip()}'")

                    # Note: Odoo product.product has an 'image_1920' field for product images
                    # The photo_url contains base64 data, we need to extract just the base64 part
                    if item.photo_url and item.photo_url.startswith('data:image'):
                        # Extract base64 data from data URL (remove "data:image/png;base64," prefix)
                        base64_data = item.photo_url.split(',')[1] if ',' in item.photo_url else item.photo_url
                        update_values['image_1920'] = base64_data
                        logger.info(f"Will update product image (size: {len(base64_data)} chars)")

                    if update_values:
                        try:
                            # Separate name from other fields - name goes to template only
                            name_update = {}
                            other_updates = {}

                            if 'name' in update_values:
                                name_update['name'] = update_values['name']
                            if 'image_1920' in update_values:
                                other_updates['image_1920'] = update_values['image_1920']

                            # Update product.product only with image (not name)
                            product_updated = False
                            if other_updates:
                                success = self.principal_client.write(
                                    OdooModel.PRODUCT_PRODUCT,
                                    [product['id']],
                                    other_updates
                                )
                                if success:
                                    logger.info(f"Successfully updated product.product fields: {list(other_updates.keys())}")
                                    product_updated = True

                            # Update product.template with name (this is the master record)
                            template_updated = False
                            if name_update:
                                # Get the template ID from the product
                                product_data = self.principal_client.read(
                                    OdooModel.PRODUCT_PRODUCT,
                                    [product['id']],
                                    fields=['product_tmpl_id', 'display_name']
                                )
                                logger.info(f"Product data before template update: {product_data}")

                                if product_data and product_data[0].get('product_tmpl_id'):
                                    template_id = product_data[0]['product_tmpl_id'][0]

                                    # Read current template name
                                    template_before = self.principal_client.read(
                                        OdooModel.PRODUCT_TEMPLATE,
                                        [template_id],
                                        fields=['name', 'display_name']
                                    )
                                    logger.info(f"Template BEFORE update: {template_before}")

                                    template_success = self.principal_client.write(
                                        OdooModel.PRODUCT_TEMPLATE,
                                        [template_id],
                                        name_update
                                    )

                                    if template_success:
                                        logger.info(f"Successfully updated product.template (ID: {template_id}) name to '{name_update['name']}'")
                                        template_updated = True

                                        # Verify template update using read()
                                        template_after = self.principal_client.read(
                                            OdooModel.PRODUCT_TEMPLATE,
                                            [template_id],
                                            fields=['name', 'display_name']
                                        )
                                        logger.info(f"Template AFTER update (read): {template_after}")

                                        # ALSO verify using search_read to ensure DB persistence
                                        template_search = self.principal_client.search_read(
                                            OdooModel.PRODUCT_TEMPLATE,
                                            domain=[['id', '=', template_id]],
                                            fields=['name', 'display_name'],
                                            limit=1
                                        )
                                        logger.info(f"Template AFTER update (search_read from DB): {template_search}")

                                        # Search by the new name to verify searchability
                                        search_by_name = self.principal_client.search_read(
                                            OdooModel.PRODUCT_TEMPLATE,
                                            domain=[['name', '=', name_update['name']]],
                                            fields=['id', 'name'],
                                            limit=5
                                        )
                                        logger.info(f"Search by new name '{name_update['name']}': found {len(search_by_name)} results: {search_by_name}")
                                    else:
                                        logger.error(f"Failed to update product.template name")

                            # Verify the updates
                            if product_updated and other_updates:
                                verify_fields = list(other_updates.keys())
                                verified = self.principal_client.read(
                                    OdooModel.PRODUCT_PRODUCT,
                                    [product['id']],
                                    fields=verify_fields
                                )
                                if verified:
                                    logger.info(f"Verified product.product updated values: {verified[0]}")

                            if template_updated:
                                logger.info(f"Product name successfully updated in Odoo")

                        except Exception as update_error:
                            logger.error(f"Error updating product fields: {str(update_error)}")
                            import traceback
                            logger.error(traceback.format_exc())

                processed_count += 1

            except Exception as e:
                logger.error(f"Error processing item {item.barcode}: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
                errors.append(f"Error processing {item.barcode}: {str(e)}")

        # Update pending adjustment status if provided
        if adjustment_id and self.db:
            try:
                pending_adj = self.db.query(PendingAdjustment).filter(
                    PendingAdjustment.id == adjustment_id
                ).first()

                if pending_adj:
                    pending_adj.status = AdjustmentStatus.CONFIRMED
                    pending_adj.confirmed_at = get_ecuador_now().replace(tzinfo=None)
                    pending_adj.confirmed_by = user.username
                    self.db.commit()
                    logger.info(f"Updated pending adjustment {adjustment_id} status to CONFIRMED")

            except Exception as e:
                logger.error(f"Error updating pending adjustment status: {str(e)}")
                # Don't fail the entire operation if just the status update fails

        # Build response
        if processed_count == 0:
            return AdjustmentResponse(
                success=False,
                message=f"Failed to process adjustments. Errors: {'; '.join(errors)}",
                processed_count=0,
                inventory_updated=False
            )

        message = f"Adjustment confirmed: {processed_count} items updated in Odoo."
        if errors:
            message += f" {len(errors)} items had errors."

        return AdjustmentResponse(
            success=True,
            message=message,
            processed_count=processed_count,
            inventory_updated=True
        )

    def cancel_pending_adjustment(self, adjustment_id: int) -> bool:
        """
        Cancel a pending adjustment.

        Args:
            adjustment_id: ID of adjustment to cancel

        Returns:
            True if cancelled successfully
        """
        if not self.db:
            raise ValueError("Database session not provided")

        pending_adj = self.db.query(PendingAdjustment).filter(
            PendingAdjustment.id == adjustment_id
        ).first()

        if not pending_adj:
            raise ValueError(f"Adjustment {adjustment_id} not found")

        if pending_adj.status != AdjustmentStatus.PENDING:
            raise ValueError(f"Adjustment {adjustment_id} is not pending")

        pending_adj.status = AdjustmentStatus.REJECTED
        self.db.commit()

        logger.info(f"Cancelled pending adjustment {adjustment_id}")
        return True

    def get_adjustment_history(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        adjustment_type: Optional[str] = None,
        user_id: Optional[int] = None
    ) -> AdjustmentHistoryResponse:
        """
        Get adjustment history with optional filters.

        Args:
            start_date: Filter by start date (ISO format)
            end_date: Filter by end date (ISO format)
            adjustment_type: Filter by adjustment type
            user_id: Filter by user ID

        Returns:
            Adjustment history response
        """
        if not self.db:
            raise ValueError("Database session not provided")

        query = self.db.query(PendingAdjustment).filter(
            PendingAdjustment.status == AdjustmentStatus.CONFIRMED
        )

        # Apply filters
        if start_date:
            query = query.filter(PendingAdjustment.confirmed_at >= start_date)
        if end_date:
            query = query.filter(PendingAdjustment.confirmed_at <= end_date)
        if adjustment_type:
            query = query.filter(PendingAdjustment.adjustment_type == adjustment_type)
        if user_id:
            query = query.filter(PendingAdjustment.user_id == user_id)

        confirmed = query.order_by(desc(PendingAdjustment.confirmed_at)).all()

        # Flatten items into history list
        history = []
        for adj in confirmed:
            for item in adj.items:
                history.append(AdjustmentHistoryItemResponse(
                    id=item.id,
                    adjustment_type=item.adjustment_type.value if isinstance(item.adjustment_type, AdjustmentType) else item.adjustment_type,
                    product_name=item.product_name,
                    barcode=item.barcode,
                    quantity=item.quantity,
                    reason=item.reason.value if isinstance(item.reason, AdjustmentReason) else item.reason,
                    description=item.description,
                    created_by=adj.username,
                    confirmed_by=adj.confirmed_by,
                    created_at=adj.created_at,
                    confirmed_at=adj.confirmed_at
                ))

        return AdjustmentHistoryResponse(
            history=history,
            total=len(history)
        )
