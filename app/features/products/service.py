"""
Product service for syncing products with Odoo.
Handles product CRUD, stock management, and XML sync operations.
"""
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from app.infrastructure.odoo import OdooClient
from app.schemas.product import (
    ProductData,
    ProductMapped,
    ProductInput,
    ProductResponse,
    SyncResult,
    SyncResponse,
    XMLParseResponse
)
from app.core.constants import OdooModel, QuantityMode
from app.core.exceptions import (
    ProductNotFoundError,
    OdooOperationError,
    ValidationError
)
from app.utils.formatters import (
    format_decimal_for_odoo,
    calculate_sale_price,
    calculate_price_with_iva,
    round_price_ecuador
)
from app.utils.validators import validate_barcode, validate_quantity, validate_price


class ProductService:
    """Service for product operations."""

    def __init__(self, odoo_client: OdooClient, db: Session = None):
        """
        Initialize product service.

        Args:
            odoo_client: Authenticated Odoo client
            db: Database session (optional, for future features)
        """
        self.client = odoo_client
        self.db = db
        self._product_type_field = None  # Cache for product type field info

    def _get_product_type_value(self) -> str:
        """
        Get the correct product type value for storable products in this Odoo version.

        In Odoo 18, the 'type' field values changed. This method detects the correct value.

        Returns:
            The correct type value for storable products
        """
        import logging
        logger = logging.getLogger(__name__)

        if self._product_type_field is not None:
            return self._product_type_field

        try:
            # Get field definition to see valid values
            fields_info = self.client.fields_get(
                OdooModel.PRODUCT_TEMPLATE,
                fields=['type'],
                attributes=['selection', 'type']
            )

            if 'type' in fields_info and 'selection' in fields_info['type']:
                selection = fields_info['type']['selection']
                logger.info(f"Product type field valid values: {selection}")

                # In Odoo 18+, 'consu' is used for storable products with inventory
                # The field 'detailed_type' controls the actual behavior
                # For now, use 'consu' which works for storable products
                self._product_type_field = 'consu'

                logger.info(f"Using product type: {self._product_type_field}")
                return self._product_type_field

        except Exception as e:
            logger.warning(f"Could not get product type field info: {e}")

        # Default fallback
        self._product_type_field = 'consu'
        return self._product_type_field

    def search_product_by_barcode(self, barcode: str) -> Optional[ProductResponse]:
        """
        Search for a product by barcode.

        Args:
            barcode: Product barcode

        Returns:
            Product information or None if not found

        Raises:
            ValidationError: If barcode is invalid
        """
        import logging
        logger = logging.getLogger(__name__)

        logger.info(f"[SERVICE] Validating barcode: {barcode}")
        if not validate_barcode(barcode):
            raise ValidationError("Invalid barcode format", field="barcode")

        try:
            # Search in product.product first
            logger.info(f"[SERVICE] Searching in Odoo for barcode: {barcode}")
            products = self.client.search_read(
                OdooModel.PRODUCT_PRODUCT,
                domain=[
                    ['barcode', '=', barcode],
                    ['active', '=', True],
                    ['available_in_pos', '=', True]
                ],
                fields=['id', 'name', 'barcode', 'qty_available', 'standard_price',
                        'list_price', 'tracking', 'available_in_pos', 'image_1920']
            )

            logger.info(f"[SERVICE] Found {len(products)} products")

            if products:
                product = products[0]
                logger.info(f"[SERVICE] Product data: {product}")

                # Calculate display price with IVA
                logger.info(f"[SERVICE] Calculating display price from list_price: {product['list_price']}")
                display_price = calculate_price_with_iva(product['list_price'])
                logger.info(f"[SERVICE] Display price calculated: {display_price}")

                logger.info("[SERVICE] Creating ProductResponse...")
                return ProductResponse(
                    id=product['id'],
                    name=product['name'],
                    barcode=product.get('barcode'),
                    qty_available=product.get('qty_available', 0),
                    standard_price=product.get('standard_price', 0),
                    list_price=product.get('list_price', 0),
                    display_price=display_price,
                    tracking=product.get('tracking'),
                    available_in_pos=product.get('available_in_pos', False),
                    image_1920=product.get('image_1920') or None  # Odoo returns False when no image
                )

            logger.info("[SERVICE] No products found, returning None")
            return None

        except Exception as e:
            logger.error(f"[SERVICE] Error in search_product_by_barcode: {str(e)}")
            import traceback
            logger.error(f"[SERVICE] Traceback: {traceback.format_exc()}")
            raise OdooOperationError(
                operation="search_product",
                message=str(e)
            )

    def create_product(self, product: ProductInput) -> SyncResult:
        """
        Create a new product in Odoo.

        Args:
            product: Product input data

        Returns:
            Sync result with product ID

        Raises:
            ValidationError: If product data is invalid
            OdooOperationError: If creation fails
        """
        # Validate inputs
        is_valid, error_msg = validate_quantity(product.qty_available)
        if not is_valid:
            raise ValidationError(error_msg, field="qty_available")

        is_valid, error_msg = validate_price(product.standard_price)
        if not is_valid:
            raise ValidationError(error_msg, field="standard_price")

        is_valid, error_msg = validate_price(product.list_price)
        if not is_valid:
            raise ValidationError(error_msg, field="list_price")

        try:
            # Prepare product data
            # In Odoo, product.product doesn't have type field directly
            # Omit type field and let Odoo use defaults
            product_data = {
                'name': product.name,
                'standard_price': format_decimal_for_odoo(product.standard_price),
                'list_price': format_decimal_for_odoo(product.list_price),
                'tracking': 'none',  # Track by quantity only (no lots/serials)
                'available_in_pos': True,
                'sale_ok': True,  # Can be sold
                'purchase_ok': True,  # Can be purchased
            }

            # Add barcode if provided
            if product.barcode:
                product_data['barcode'] = product.barcode.strip()

            # Add image if provided (base64 encoded)
            if product.image_1920:
                # Remove data URL prefix if present
                image_data = product.image_1920
                if ',' in image_data:
                    image_data = image_data.split(',', 1)[1]
                product_data['image_1920'] = image_data

            # Create product
            product_id = self.client.create(OdooModel.PRODUCT_PRODUCT, product_data)

            # After creating, change the product type to 'product' (storable)
            # Get the product.template id
            product_info = self.client.read(
                OdooModel.PRODUCT_PRODUCT,
                [product_id],
                fields=['product_tmpl_id']
            )

            if product_info and product_info[0].get('product_tmpl_id'):
                template_id = product_info[0]['product_tmpl_id'][0]

                # Update the template to be storable
                try:
                    self.client.write(
                        OdooModel.PRODUCT_TEMPLATE,
                        [template_id],
                        {'detailed_type': 'product'}  # Storable product
                    )
                except Exception:
                    # Try old field name
                    try:
                        self.client.write(
                            OdooModel.PRODUCT_TEMPLATE,
                            [template_id],
                            {'type': 'product'}  # Storable product
                        )
                    except Exception:
                        pass  # Continue anyway

            # Update stock if quantity specified
            if product.qty_available > 0:
                self._update_stock_quantity(
                    product_id,
                    product.qty_available,
                    product.quantity_mode,
                    product.name
                )

            return SyncResult(
                success=True,
                message=f"Product '{product.name}' created successfully",
                product_id=product_id,
                action="created",
                product_name=product.name,
                barcode=product.barcode
            )

        except Exception as e:
            return SyncResult(
                success=False,
                message=f"Failed to create product '{product.name}': {str(e)}",
                product_id=None,
                action="error",
                product_name=product.name,
                barcode=product.barcode,
                error_details=str(e)[:500]
            )

    def update_product(self, product_id: int, product: ProductInput) -> SyncResult:
        """
        Update an existing product.

        Args:
            product_id: Product ID to update
            product: Updated product data

        Returns:
            Sync result
        """
        try:
            # Get current product details
            current = self.client.read(
                OdooModel.PRODUCT_PRODUCT,
                [product_id],
                fields=['list_price', 'name']
            )

            if not current:
                raise ProductNotFoundError(product_id)

            current_list_price = float(current[0].get('list_price', 0))
            new_list_price = format_decimal_for_odoo(product.list_price)

            # Prepare update data
            update_data = {
                'standard_price': format_decimal_for_odoo(product.standard_price),
                'available_in_pos': True,
            }

            # Price protection: only update if new price is higher
            if new_list_price > current_list_price:
                update_data['list_price'] = new_list_price

            if product.barcode:
                update_data['barcode'] = product.barcode

            # Update image if provided
            if product.image_1920:
                # Remove data URL prefix if present
                image_data = product.image_1920
                if ',' in image_data:
                    image_data = image_data.split(',', 1)[1]
                update_data['image_1920'] = image_data

            # Update product
            self.client.write(OdooModel.PRODUCT_PRODUCT, [product_id], update_data)

            # Update stock
            if product.qty_available > 0:
                self._update_stock_quantity(
                    product_id,
                    product.qty_available,
                    product.quantity_mode,
                    product.name
                )

            return SyncResult(
                success=True,
                message=f"Product '{product.name}' updated successfully",
                product_id=product_id,
                action="updated",
                product_name=product.name,
                barcode=product.barcode
            )

        except Exception as e:
            return SyncResult(
                success=False,
                message=f"Failed to update product: {str(e)}",
                product_id=product_id,
                action="error",
                product_name=product.name,
                barcode=product.barcode,
                error_details=str(e)[:500]
            )

    def sync_product(self, product_mapped: Dict[str, Any]) -> SyncResult:
        """
        Sync a single product (create or update by barcode).

        Args:
            product_mapped: Mapped product data

        Returns:
            Sync result
        """
        import logging
        logger = logging.getLogger(__name__)

        barcode = product_mapped.get('barcode')
        product_name = product_mapped.get('name', 'Unknown')

        logger.info(f"=== SYNCING PRODUCT: {product_name} ({barcode}) ===")

        if not barcode:
            logger.error(f"Product missing barcode: {product_name}")
            return SyncResult(
                success=False,
                message="Product missing barcode",
                action="error",
                product_name=product_name
            )

        try:
            # Search for existing product
            logger.info(f"Searching for existing product with barcode: {barcode}")
            existing = self.client.search_read(
                OdooModel.PRODUCT_PRODUCT,
                domain=[['barcode', '=', barcode]],
                fields=['id', 'list_price', 'name'],
                limit=1
            )
            logger.info(f"Search result: {existing if existing else 'Not found'}")

            if existing:
                # Update existing
                product_id = existing[0]['id']
                current_list_price = float(existing[0].get('list_price', 0))
                new_list_price = format_decimal_for_odoo(product_mapped['list_price'])

                update_data = {
                    'standard_price': format_decimal_for_odoo(product_mapped['standard_price']),
                    'available_in_pos': True,
                    'barcode': barcode
                }

                # Price protection
                if new_list_price > current_list_price:
                    update_data['list_price'] = new_list_price

                self.client.write(OdooModel.PRODUCT_PRODUCT, [product_id], update_data)

                # Update stock
                if product_mapped.get('qty_available', 0) > 0:
                    self._update_stock_quantity(
                        product_id,
                        product_mapped['qty_available'],
                        product_mapped.get('quantity_mode', 'replace'),
                        product_mapped['name']
                    )

                return SyncResult(
                    success=True,
                    message=f"Product '{product_mapped['name']}' updated",
                    product_id=product_id,
                    action="updated",
                    product_name=product_mapped['name'],
                    barcode=barcode
                )

            else:
                # Create new storable product (tracks inventory)
                # Key fields:
                # - type: 'consu' = Goods (tangible products)
                # - is_storable: True = Enable inventory tracking
                # - tracking: 'none' = Track by quantity (not by lots/serials)
                product_data = {
                    'name': product_mapped['name'],
                    'standard_price': format_decimal_for_odoo(product_mapped['standard_price']),
                    'list_price': format_decimal_for_odoo(product_mapped['list_price']),
                    'barcode': barcode,
                    'type': 'consu',  # Goods (tangible products)
                    'is_storable': True,  # Enable inventory tracking
                    'tracking': 'none',  # Track by quantity only (no lots/serials)
                    'available_in_pos': True,
                    'sale_ok': True,  # Can be sold
                    'purchase_ok': True,  # Can be purchased
                }

                logger.info(f"Product data to create: {product_data}")

                try:
                    product_id = self.client.create(OdooModel.PRODUCT_PRODUCT, product_data)
                    logger.info(f"Product created successfully with ID: {product_id} with inventory tracking enabled")

                except Exception as create_error:
                    logger.error(f"Error creating product: {str(create_error)}")
                    import traceback
                    logger.error(traceback.format_exc())
                    raise

                # Update stock
                qty = product_mapped.get('qty_available', 0)
                logger.info(f"Product quantity to set: {qty}")

                if qty > 0:
                    logger.info(f"Updating stock quantity for product {product_id}")
                    self._update_stock_quantity(
                        product_id,
                        qty,
                        product_mapped.get('quantity_mode', 'replace'),
                        product_mapped['name']
                    )
                else:
                    logger.warning(f"Quantity is {qty}, skipping stock update")

                logger.info(f"Product sync completed successfully: {product_name}")
                return SyncResult(
                    success=True,
                    message=f"Product '{product_mapped['name']}' created",
                    product_id=product_id,
                    action="created",
                    product_name=product_mapped['name'],
                    barcode=barcode
                )

        except Exception as e:
            logger.error(f"Error syncing product {product_name}: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return SyncResult(
                success=False,
                message=f"Failed to sync product: {str(e)}",
                action="error",
                product_name=product_mapped.get('name', 'Unknown'),
                barcode=barcode,
                error_details=str(e)[:500]
            )

    def sync_products_bulk(self, products: List[Dict[str, Any]]) -> SyncResponse:
        """
        Sync multiple products.

        Args:
            products: List of mapped product data

        Returns:
            Sync response with results
        """
        import logging
        logger = logging.getLogger(__name__)

        logger.info(f"Starting bulk sync of {len(products)} products")

        results = []
        created_count = 0
        updated_count = 0
        errors_count = 0

        for idx, product in enumerate(products, 1):
            logger.info(f"Processing product {idx}/{len(products)}")
            result = self.sync_product(product)
            results.append(result)

            if result.success:
                if result.action == "created":
                    created_count += 1
                    logger.info(f"✓ Created: {result.product_name}")
                elif result.action == "updated":
                    updated_count += 1
                    logger.info(f"✓ Updated: {result.product_name}")
            else:
                errors_count += 1
                logger.error(f"✗ Error: {result.product_name} - {result.message}")

        logger.info(f"Bulk sync completed: {created_count} created, {updated_count} updated, {errors_count} errors")

        return SyncResponse(
            results=results,
            total_processed=len(products),
            created_count=created_count,
            updated_count=updated_count,
            errors_count=errors_count
        )

    def _update_stock_quantity(
        self,
        product_id: int,
        quantity: float,
        mode: str = 'replace',
        product_name: str = None
    ) -> None:
        """
        Update product stock quantity.

        Args:
            product_id: Product ID
            quantity: Quantity to set or add
            mode: 'replace' or 'add'
            product_name: Product name for logging
        """
        import logging
        logger = logging.getLogger(__name__)

        try:
            logger.info(f"Updating stock for product {product_id} ({product_name}): quantity={quantity}, mode={mode}")

            # Get internal stock location
            location_ids = self.client.search(
                OdooModel.STOCK_LOCATION,
                domain=[['usage', '=', 'internal']],
                limit=1
            )

            if not location_ids:
                logger.warning(f"No internal stock location found for product {product_id}")
                return

            location_id = location_ids[0]
            logger.info(f"Using stock location ID: {location_id}")

            # Check if quant exists
            quant_ids = self.client.search(
                OdooModel.STOCK_QUANT,
                domain=[
                    ['product_id', '=', product_id],
                    ['location_id', '=', location_id]
                ]
            )

            final_quantity = quantity

            if quant_ids:
                logger.info(f"Found existing quant(s): {quant_ids}")
                if mode == 'add':
                    # Get current quantity
                    current = self.client.read(
                        OdooModel.STOCK_QUANT,
                        quant_ids[:1],
                        fields=['quantity']
                    )
                    if current:
                        current_qty = current[0].get('quantity', 0)
                        final_quantity = current_qty + quantity
                        logger.info(f"Adding {quantity} to existing {current_qty} = {final_quantity}")

                # Update existing quant
                self.client.write(
                    OdooModel.STOCK_QUANT,
                    quant_ids[:1],
                    {'quantity': format_decimal_for_odoo(final_quantity)}
                )
                logger.info(f"Updated quant with quantity: {final_quantity}")
            else:
                logger.info(f"No existing quant, creating new one with quantity: {final_quantity}")
                # Create new quant
                quant_id = self.client.create(
                    OdooModel.STOCK_QUANT,
                    {
                        'product_id': product_id,
                        'location_id': location_id,
                        'quantity': format_decimal_for_odoo(final_quantity)
                    }
                )
                logger.info(f"Created new quant ID: {quant_id}")

        except Exception as e:
            # Don't fail the main operation but log the error
            logger.error(f"Error updating stock quantity for product {product_id}: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())

    def get_all_products(self, limit: int = 1000) -> List[ProductResponse]:
        """
        Get all products from Odoo.

        Args:
            limit: Maximum number of products to return

        Returns:
            List of products
        """
        try:
            products = self.client.search_read(
                OdooModel.PRODUCT_PRODUCT,
                domain=[['available_in_pos', '=', True]],
                fields=['id', 'name', 'barcode', 'qty_available', 'standard_price',
                        'list_price', 'tracking', 'available_in_pos', 'image_1920'],
                limit=limit
            )

            return [
                ProductResponse(
                    id=p['id'],
                    name=p['name'],
                    barcode=p.get('barcode'),
                    qty_available=p.get('qty_available', 0),
                    standard_price=p.get('standard_price', 0),
                    list_price=p.get('list_price', 0),
                    display_price=calculate_price_with_iva(p.get('list_price', 0)),
                    tracking=p.get('tracking'),
                    available_in_pos=p.get('available_in_pos', False),
                    image_1920=p.get('image_1920')
                )
                for p in products
            ]

        except Exception as e:
            raise OdooOperationError(
                operation="get_all_products",
                message=str(e)
            )
