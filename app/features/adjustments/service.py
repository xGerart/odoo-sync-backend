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

        # If there are ANY errors, reject the entire adjustment
        if errors:
            error_details = "; ".join(errors[:3])
            if len(errors) > 3:
                error_details += f"... and {len(errors) - 3} more"

            message = (
                f"❌ Adjustment REJECTED - {len(errors)} product(s) failed validation. "
                f"Fix these errors and try again:\n\n{error_details}\n\n"
                f"✅ {len(validated_items)} product(s) passed validation but were NOT saved."
            )

            return AdjustmentResponse(
                success=False,
                message=message,
                processed_count=0,
                inventory_updated=False
            )

        # All products validated successfully - save to database
        try:
            pending_adjustment = self.save_pending_adjustment(validated_items, user)

            message = f"✅ Adjustment validated successfully: {len(validated_items)} items ready. Awaiting admin confirmation."

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

        # Data for history capture
        snapshots_before = []
        snapshots_after = []
        successful_products = []

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

                # CAPTURE: Snapshot BEFORE adjustment
                snapshot_before = self._capture_product_snapshot(
                    self.principal_client,
                    item.barcode,
                    product['id']
                )
                if snapshot_before:
                    snapshots_before.append(snapshot_before)
                    logger.info(f"  ✓ Snapshot BEFORE captured")

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

                # CAPTURE: Snapshot AFTER adjustment
                snapshot_after = self._capture_product_snapshot(
                    self.principal_client,
                    item.barcode,
                    product['id']
                )
                if snapshot_after:
                    snapshots_after.append(snapshot_after)
                    logger.info(f"  ✓ Snapshot AFTER captured")

                # Track successful product with all data
                successful_products.append({
                    'barcode': item.barcode,
                    'product_id': item.product_id,
                    'product_name': item.product_name,
                    'quantity': item.quantity,
                    'adjustment_type': item.adjustment_type.value,
                    'reason': item.reason.value,
                    'unit_price': item.unit_price,
                    'stock_before': snapshot_before.get('qty_available') if snapshot_before else None,
                    'stock_after': snapshot_after.get('qty_available') if snapshot_after else None
                })

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

        # Generate PDF and XML, and create historical record
        if processed_count > 0 and successful_products:
            try:
                from datetime import datetime

                # Generate XML content
                xml_content = self._generate_adjustment_xml(successful_products)
                logger.info("✓ XML content generated")

                # Prepare adjustment data for PDF
                adjustment_data = {
                    'id': adjustment_id or 'new',
                    'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'username': user.username,
                    'confirmed_by': user.username,
                    'location_name': 'Principal',
                    'adjustment_type': items[0].adjustment_type.value if items else '',
                    'reason': items[0].reason.value if items else '',
                    'total_items': len(successful_products),
                    'total_quantity': sum(abs(p['quantity']) for p in successful_products)
                }

                # Generate PDF report
                pdf_content = None
                pdf_filename = None
                try:
                    pdf_content, pdf_filename = self._generate_adjustment_report_pdf(
                        adjustment_data=adjustment_data,
                        snapshots_before=snapshots_before,
                        snapshots_after=snapshots_after
                    )
                    logger.info(f"✓ PDF report generated: {pdf_filename}")
                except Exception as pdf_error:
                    logger.error(f"Error generating PDF report: {str(pdf_error)}")
                    # Continue even if PDF generation fails

                # Create historical record
                try:
                    self._create_adjustment_history(
                        pending_adjustment_id=adjustment_id,
                        location='principal',
                        location_name='Principal',
                        executed_by=user.username,
                        successful_products=successful_products,
                        failed_products=[],  # We could track failed products here if needed
                        snapshots_before=snapshots_before,
                        snapshots_after=snapshots_after,
                        pdf_content=pdf_content,
                        pdf_filename=pdf_filename,
                        xml_content=xml_content,
                        errors=errors
                    )
                    logger.info("✓ Adjustment history record created")
                except Exception as history_error:
                    logger.error(f"Failed to create adjustment history: {str(history_error)}")
                    import traceback
                    logger.error(traceback.format_exc())
                    # Don't fail the adjustment if history creation fails

            except Exception as e:
                logger.error(f"Error in history/PDF generation: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
                # Don't fail the adjustment if history creation fails

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

    # Helper methods for adjustment history

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
            logger.error(f"Error capturing product snapshot for {barcode}: {e}")
            return None

    def _generate_adjustment_xml(self, products: List[Dict]) -> str:
        """
        Generate XML content for adjustment.

        Args:
            products: List of products with adjustment data

        Returns:
            XML string
        """
        xml_lines = ['<?xml version="1.0" encoding="UTF-8"?>']
        xml_lines.append('<adjustment>')

        for product in products:
            xml_lines.append('  <product>')
            xml_lines.append(f'    <name>{product.get("product_name", "")}</name>')
            xml_lines.append(f'    <barcode>{product.get("barcode", "")}</barcode>')
            xml_lines.append(f'    <quantity>{product.get("quantity", 0)}</quantity>')
            xml_lines.append(f'    <adjustment_type>{product.get("adjustment_type", "")}</adjustment_type>')
            xml_lines.append(f'    <reason>{product.get("reason", "")}</reason>')
            xml_lines.append(f'    <unit_price>{product.get("unit_price", 0)}</unit_price>')
            xml_lines.append('  </product>')

        xml_lines.append('</adjustment>')
        return '\n'.join(xml_lines)

    def _generate_adjustment_report_pdf(
        self,
        adjustment_data: Dict[str, Any],
        snapshots_before: List[Dict],
        snapshots_after: List[Dict]
    ) -> tuple[str, str]:
        """
        Generate PDF report for adjustment.

        Args:
            adjustment_data: Adjustment metadata (id, date, user, type, reason, etc.)
            snapshots_before: Stock before adjustment
            snapshots_after: Stock after adjustment

        Returns:
            Tuple of (base64_pdf_content, pdf_filename)
        """
        import base64
        from datetime import datetime
        from app.utils.pdf_templates import AdjustmentReport

        try:
            # Generate PDF
            report = AdjustmentReport()
            pdf_buffer = report.generate(
                adjustment_data=adjustment_data,
                snapshots_before=snapshots_before,
                snapshots_after=snapshots_after
            )

            # Convert to base64
            pdf_content = base64.b64encode(pdf_buffer.getvalue()).decode('utf-8')

            # Generate filename
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            adjustment_id = adjustment_data.get('id', 'new')
            pdf_filename = f"adjustment_report_{adjustment_id}_{timestamp}.pdf"

            logger.info(f"Generated PDF report: {pdf_filename}")
            return pdf_content, pdf_filename

        except Exception as e:
            logger.error(f"Error generating PDF report: {str(e)}")
            raise

    def _create_adjustment_history(
        self,
        pending_adjustment_id: Optional[int],
        location: str,
        location_name: str,
        executed_by: str,
        successful_products: List[Dict],
        failed_products: List[Dict],
        snapshots_before: List[Dict],
        snapshots_after: List[Dict],
        pdf_content: Optional[str],
        pdf_filename: Optional[str],
        xml_content: Optional[str],
        errors: List[str]
    ) -> 'AdjustmentHistory':
        """
        Create comprehensive historical record of adjustment execution.

        Args:
            pending_adjustment_id: Optional ID of the pending adjustment
            location: Location ID where adjustment was made
            location_name: Location name
            executed_by: Username who executed the adjustment
            successful_products: List of successfully adjusted products
            failed_products: List of products that failed to adjust
            snapshots_before: Stock snapshots before adjustment
            snapshots_after: Stock snapshots after adjustment
            pdf_content: Base64 encoded PDF content
            pdf_filename: PDF filename
            xml_content: XML content
            errors: List of error messages

        Returns:
            Created AdjustmentHistory record

        Raises:
            Exception: If database operations fail
        """
        import json
        from app.models.adjustment_history import AdjustmentHistory, AdjustmentHistoryItem
        from app.utils.timezone import get_ecuador_now

        logger.info(f"Creating adjustment history record for location: {location_name}")

        # Combine all products for counting
        all_products = successful_products + failed_products

        # Calculate totals
        total_items = len(all_products)
        successful_items = len(successful_products)
        failed_items = len(failed_products)
        total_quantity_requested = sum(abs(p.get('quantity', 0)) for p in all_products)
        total_quantity_adjusted = sum(abs(p.get('quantity', 0)) for p in successful_products)

        # Build error summary
        error_summary = None
        if errors:
            error_summary = "; ".join(errors)

        # Create main history record
        history = AdjustmentHistory(
            pending_adjustment_id=pending_adjustment_id,
            location=location,
            location_name=location_name,
            executed_by=executed_by,
            executed_at=get_ecuador_now().replace(tzinfo=None),  # SQLite needs naive datetime
            total_items=total_items,
            successful_items=successful_items,
            failed_items=failed_items,
            total_quantity_requested=total_quantity_requested,
            total_quantity_adjusted=total_quantity_adjusted,
            pdf_content=pdf_content,
            pdf_filename=pdf_filename,
            xml_content=xml_content,
            snapshots_before=json.dumps(snapshots_before),
            snapshots_after=json.dumps(snapshots_after),
            has_errors=len(errors) > 0,
            error_summary=error_summary
        )

        self.db.add(history)
        self.db.flush()  # Get ID for items

        logger.info(f"Adjustment history record created with ID: {history.id}")

        # Create individual item records
        for product in all_products:
            is_successful = product in successful_products

            item = AdjustmentHistoryItem(
                history_id=history.id,
                barcode=product.get('barcode', ''),
                product_id=product.get('product_id', 0),
                product_name=product.get('product_name', ''),
                quantity_requested=abs(product.get('quantity', 0)),
                quantity_adjusted=abs(product.get('quantity', 0)) if is_successful else 0,
                adjustment_type=product.get('adjustment_type', ''),
                reason=product.get('reason', ''),
                success=is_successful,
                error_message=product.get('error') if not is_successful else None,
                stock_before=product.get('stock_before'),
                stock_after=product.get('stock_after'),
                unit_price=product.get('unit_price'),
                total_value=abs(product.get('quantity', 0)) * product.get('unit_price', 0) if is_successful else 0
            )
            self.db.add(item)

        # Commit all changes
        self.db.commit()

        logger.info(f"✓ Adjustment history saved: {successful_items} successful, {failed_items} failed")

        return history
