import xmlrpc.client
import ssl
import locale
import base64
from io import BytesIO
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from models import OdooConfig, ProductMapped, SyncResult, OdooConnectionTest, CierreCajaResponse, SaleByEmployee, PaymentMethodSummary, TransferResponse, POSSession


class OdooClient:
    def __init__(self, config: OdooConfig):
        self.config = config
        self.url = config.url
        self.db = config.database
        self.username = config.username
        self.password = config.password
        self.uid = None
        self.odoo_version = None
        
        # Setup XML-RPC connections with SSL context
        self.verify_ssl = config.verify_ssl  # Store for debugging
        
        if self.url.startswith('https://'):
            # Create SSL context based on configuration
            ssl_context = ssl.create_default_context()
            
            if not config.verify_ssl:
                # Allow self-signed certificates and disable hostname verification
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
                print(f"SSL verification disabled for {self.url}")
            else:
                print(f"SSL verification enabled for {self.url}")
            
            self.common = xmlrpc.client.ServerProxy(f'{self.url}/xmlrpc/2/common', context=ssl_context)
            self.models = xmlrpc.client.ServerProxy(f'{self.url}/xmlrpc/2/object', context=ssl_context)
        else:
            # For HTTP connections, no SSL context needed
            self.common = xmlrpc.client.ServerProxy(f'{self.url}/xmlrpc/2/common')
            self.models = xmlrpc.client.ServerProxy(f'{self.url}/xmlrpc/2/object')
    
    def _format_decimal_for_odoo(self, value: float) -> float:
        """Return decimal number as float for Odoo (Odoo XML-RPC expects float, not string)"""
        # Return as float with full precision (8 decimals) to ensure IVA calculation accuracy
        # This prevents rounding errors when Odoo calculates final price with IVA
        return round(float(value), 8)


    def _is_odoo_18_plus(self) -> bool:
        """Check if Odoo version is 18 or higher"""
        if not self.odoo_version:
            return False
        try:
            # Handle different version formats: "18.0", "saas~18.2+e", etc.
            version_str = self.odoo_version
            
            # Extract version number from saas format
            if 'saas~' in version_str:
                # Extract "18.2" from "saas~18.2+e"
                version_str = version_str.split('saas~')[1].split('+')[0]
            
            # Get major version number
            major_version = float(version_str.split('.')[0])
            return major_version >= 18.0
        except (ValueError, AttributeError, IndexError):
            print(f"Could not parse version '{self.odoo_version}', assuming Odoo 18+")
            return True  # Default to Odoo 18+ since you only use Odoo 18

    def _get_product_type_field(self) -> dict:
        """Get the correct product type field based on Odoo version with auto-detection"""
        try:
            # Debugging product type field for compatibility

            # Get field info for product.template
            field_info = self.models.execute_kw(
                self.db, self.uid, self.password,
                'product.template', 'fields_get',
                [],  # Get all fields
                {'attributes': ['type', 'selection', 'string']}
            )

            # Available fields retrieved (detailed list suppressed for cleaner logs)

            # Check 'type' field first
            if 'type' in field_info and 'selection' in field_info['type']:
                selection_values = field_info['type']['selection']
                print(f"✅ Found 'type' field with values: {selection_values}")

                available_types = [v for v, l in selection_values]

                # Try different type values in order of preference
                test_types = ['product', 'consu', 'service']

                for test_type in test_types:
                    if test_type in available_types:
                        print(f"🎯 Will try: type='{test_type}'")

                        # For 'consu' type, also check if we need to set is_storable
                        if test_type == 'consu' and 'is_storable' in field_info:
                            print(f"🔧 Adding is_storable=True for consu type")
                            return {'type': test_type, 'is_storable': True}

                        return {'type': test_type}

                # Fallback to first available
                if available_types:
                    fallback_type = available_types[0]
                    print(f"⚠️ Fallback to: type='{fallback_type}'")
                    return {'type': fallback_type}

            # Check 'detailed_type' field for older versions
            elif 'detailed_type' in field_info:
                print(f"✅ Found 'detailed_type' field - using for older Odoo")
                return {'detailed_type': 'storable'}

            else:
                print(f"❌ No 'type' or 'detailed_type' field found!")
                return {'type': 'consu'}  # Basic fallback

        except Exception as e:
            print(f"❌ Error detecting product type field: {e}")
            return {'type': 'consu'}  # Safe fallback

    def authenticate(self) -> OdooConnectionTest:
        """Test connection and authenticate with Odoo"""
        try:
            # Test connection and get version
            version_info = self.common.version()
            if not version_info:
                return OdooConnectionTest(
                    success=False,
                    message="Could not connect to Odoo server"
                )
            
            # Store version info for compatibility decisions
            self.odoo_version = version_info.get('server_version', '17.0')
            print(f"Detected Odoo version: {self.odoo_version}")
            
            # Authenticate
            self.uid = self.common.authenticate(
                self.db, self.username, self.password, {}
            )
            
            if self.uid:
                return OdooConnectionTest(
                    success=True,
                    message=f"Successfully connected to Odoo {self.odoo_version}",
                    user_id=self.uid
                )
            else:
                return OdooConnectionTest(
                    success=False,
                    message="Authentication failed. Check credentials."
                )
                
        except ssl.SSLError as e:
            return OdooConnectionTest(
                success=False,
                message=f"SSL certificate error: {str(e)}. Try using HTTP instead of HTTPS for testing, or ensure your Odoo server has valid SSL certificates."
            )
        except Exception as e:
            error_msg = str(e)
            # Provide more helpful error messages for common issues
            if "certificate verify failed" in error_msg.lower():
                error_msg = "SSL certificate verification failed. The server's SSL certificate could not be verified. Try using HTTP instead of HTTPS for testing."
            elif "connection refused" in error_msg.lower():
                error_msg = "Connection refused. Check if the Odoo server is running and the URL/port are correct."
            elif "name or service not known" in error_msg.lower():
                error_msg = "Cannot resolve hostname. Check if the server URL is correct and accessible."
            elif "302 found" in error_msg.lower():
                error_msg = "HTTP 302 redirect detected. Your server might be redirecting HTTP to HTTPS. Try using HTTPS in the URL instead of HTTP."
            elif "protocolerror" in error_msg.lower():
                error_msg = "Protocol error detected. This often means wrong URL format or HTTP/HTTPS mismatch. Check your server URL and try both HTTP and HTTPS."
            
            return OdooConnectionTest(
                success=False,
                message=f"Connection error: {error_msg}"
            )

    def search_product_by_barcode(self, barcode: str) -> Optional[int]:
        """Search for a product by barcode and return product.template ID"""
        if not self.uid:
            raise Exception("Not authenticated")

        try:
            # Search in product.product first to find the variant
            # Only search in active products available in POS to avoid conflicts
            product_variant_ids = self.models.execute_kw(
                self.db, self.uid, self.password,
                'product.product', 'search_read',
                [[
                    ['barcode', '=', barcode],
                    ['active', '=', True],
                    ['available_in_pos', '=', True]
                ]],
                {'fields': ['product_tmpl_id', 'name']}
            )

            if product_variant_ids:
                # Return the product.template ID from the variant
                return product_variant_ids[0]['product_tmpl_id'][0]

            # If not found in product.product, try product.template directly
            # Also filter by active and available_in_pos
            template_ids = self.models.execute_kw(
                self.db, self.uid, self.password,
                'product.template', 'search',
                [[
                    ['barcode', '=', barcode],
                    ['active', '=', True],
                    ['available_in_pos', '=', True]
                ]]
            )
            return template_ids[0] if template_ids else None

        except Exception as e:
            print(f"Error in search_product_by_barcode: {e}")
            return None
    
    def get_product_details(self, product_id: int) -> Optional[Dict]:
        """Get detailed product information"""
        if not self.uid:
            raise Exception("Not authenticated")

        try:
            product_data = self.models.execute_kw(
                self.db, self.uid, self.password,
                'product.template', 'search_read',
                [[['id', '=', product_id]]],
                {'fields': ['name', 'barcode', 'standard_price', 'list_price', 'qty_available', 'tracking', 'available_in_pos']}
            )
            return product_data[0] if product_data else None
        except Exception as e:
            print(f"Error in get_product_details: {e}")
            return None

    def search_product_by_name(self, name: str) -> Optional[int]:
        """Search for a product by name (exact match)"""
        if not self.uid:
            raise Exception("Not authenticated")
            
        try:
            product_ids = self.models.execute_kw(
                self.db, self.uid, self.password,
                'product.product', 'search',
                [[['name', '=', name]]]
            )
            return product_ids[0] if product_ids else None
        except Exception:
            return None

    def create_product(self, product: ProductMapped) -> SyncResult:
        """Create a new product in Odoo"""
        if not self.uid:
            raise Exception("Not authenticated")
            
        try:
            # Start with minimal required fields
            product_data = {
                'name': product.name,
                'standard_price': self._format_decimal_for_odoo(product.standard_price),
                'list_price': self._format_decimal_for_odoo(product.list_price),
            }
            
            # Add version-specific product type field
            product_data.update(self._get_product_type_field())
            
            # Add optional fields only if they have valid values
            if hasattr(product, 'tracking') and product.tracking in ['none', 'lot', 'serial']:
                product_data['tracking'] = product.tracking
            
            if hasattr(product, 'available_in_pos'):
                product_data['available_in_pos'] = bool(product.available_in_pos)
            
            # Debug: print essential data being sent to Odoo
            print(f"Creating product: {product.name} (type: {product_data.get('type')})")
            print(f"Odoo version: {self.odoo_version} - Type field: {self._get_product_type_field()}")
            
            # Add barcode if provided and not empty
            if hasattr(product, 'barcode') and product.barcode and product.barcode.strip():
                product_data['barcode'] = product.barcode.strip()
                
            # Note: qty_available is NOT added to product creation data
            # It will be handled separately via stock.quant after product creation

            product_id = self.models.execute_kw(
                self.db, self.uid, self.password,
                'product.product', 'create',
                [product_data]
            )
            
            # Update stock quantity if specified
            if hasattr(product, 'qty_available') and product.qty_available > 0:
                mode = getattr(product, 'quantity_mode', 'replace')
                self.update_stock_quantity(product_id, product.qty_available, mode, product.name)
            
            return SyncResult(
                success=True,
                message=f"Product '{product.name}' created successfully",
                product_id=product_id,
                action="created",
                product_name=product.name,
                barcode=getattr(product, 'barcode', None)
            )
            
        except Exception as e:
            import traceback
            import logging

            logger = logging.getLogger(__name__)
            error_msg = str(e)

            # Log full error for debugging with product details
            logger.error(f"❌ ERROR creating product '{product.name}': {error_msg}")
            logger.error(f"📊 Product data: {product_data}")
            logger.error(f"🔍 Full traceback: {traceback.format_exc()}")

            print(f"❌ ERROR creating product '{product.name}': {error_msg}")
            print(f"📊 Product data: {product_data}")
            print(f"🔍 Full error creating product: {traceback.format_exc()}")

            # Clean up XML-RPC fault messages for better readability
            if 'ValueError: Wrong value for' in error_msg:
                if 'product.template.type' in error_msg or 'product.template.detailed_type' in error_msg:
                    if self._is_odoo_18_plus():
                        error_msg = "Invalid product type for Odoo 18+. Valid values: 'goods' (physical products), 'service', or 'combo'."
                    else:
                        error_msg = "Invalid product detailed_type for Odoo 17-. Valid values: 'storable', 'consumable', or 'service'."
                elif 'tracking' in error_msg:
                    error_msg = "Invalid tracking value. Use 'none', 'lot', or 'serial'."
                else:
                    error_msg = "Invalid field value detected in product data."
            elif 'barcode' in error_msg.lower():
                error_msg = "Barcode validation failed. Check if barcode is unique or valid."
            elif 'fault 1:' in error_msg.lower():
                error_msg = "Internal Odoo error. Check server logs and ensure all field values are valid."
            elif len(error_msg) > 300:
                # Show more context for debugging
                error_msg = error_msg[:300] + "... (error truncated - check server logs)"
                
            return SyncResult(
                success=False,
                message=f"Failed to create product '{product.name}': {error_msg}",
                action="error",
                product_name=product.name,
                barcode=getattr(product, 'barcode', None),
                error_details=str(e) if len(str(e)) < 500 else str(e)[:500] + "..."
            )

    def update_product(self, product_id: int, product: ProductMapped) -> SyncResult:
        """Update an existing product in Odoo"""
        if not self.uid:
            raise Exception("Not authenticated")

        try:
            # Get current product details to check existing prices
            current_details = self.get_product_details(product_id)
            current_list_price = float(current_details.get('list_price', 0)) if current_details else 0
            new_list_price = self._format_decimal_for_odoo(product.list_price)

            update_data = {
                'standard_price': self._format_decimal_for_odoo(product.standard_price),  # Cost price
                'available_in_pos': product.available_in_pos,
            }

            # Price protection: only update sale price if new price is higher
            if new_list_price > current_list_price:
                update_data['list_price'] = new_list_price
                print(f"💰 Updating sale price: ${current_list_price} → ${new_list_price}")
            else:
                print(f"🛡️ Protecting higher sale price: keeping ${current_list_price} (XML suggests ${new_list_price})")

            # Always update cost price
            print(f"💸 Updating cost price: ${self._format_decimal_for_odoo(product.standard_price)}")

            # Add version-specific product type field (including is_storable)
            update_data.update(self._get_product_type_field())

            # Update barcode to ensure we're updating the correct product
            if product.barcode:
                update_data['barcode'] = product.barcode
                
            self.models.execute_kw(
                self.db, self.uid, self.password,
                'product.product', 'write',
                [[product_id], update_data]
            )
            
            # Update stock quantity if specified
            if hasattr(product, 'qty_available') and product.qty_available > 0:
                mode = getattr(product, 'quantity_mode', 'replace')
                self.update_stock_quantity(product_id, product.qty_available, mode, product.name)
            
            return SyncResult(
                success=True,
                message=f"Product '{product.name}' updated successfully",
                product_id=product_id,
                action="updated",
                product_name=product.name,
                barcode=getattr(product, 'barcode', None)
            )
            
        except Exception as e:
            import traceback
            import logging

            logger = logging.getLogger(__name__)
            error_msg = str(e)

            # Log full error for debugging with product details
            logger.error(f"❌ ERROR updating product '{product.name}' (ID: {product_id}): {error_msg}")
            logger.error(f"📊 Update data: {update_data}")
            logger.error(f"🔍 Full traceback: {traceback.format_exc()}")

            print(f"❌ ERROR updating product '{product.name}' (ID: {product_id}): {error_msg}")
            print(f"📊 Update data: {update_data}")
            print(f"🔍 Full error updating product: {traceback.format_exc()}")

            # Check if this is a tracking/inventory error for a product already used
            if ('no puede cambiar el seguimiento' in error_msg.lower() or
                'cannot change the tracking' in error_msg.lower() or
                'ya se utilizó' in error_msg.lower() or
                'already used' in error_msg.lower()):

                print(f"⚠️ Product '{product.name}' cannot update tracking - attempting archive and recreate")
                logger.warning(f"⚠️ Product '{product.name}' cannot update tracking - attempting archive and recreate")
                try:
                    # Archive and recreate the product
                    return self._archive_and_recreate_product(product_id, product)
                except Exception as recreate_error:
                    error_msg = f"Failed to recreate product after tracking error: {str(recreate_error)}"
                    logger.error(f"❌ Failed to recreate product '{product.name}': {str(recreate_error)}")

            # Clean up XML-RPC fault messages for better readability
            if 'ValueError: Wrong value for' in error_msg:
                if 'product.template.type' in error_msg or 'product.template.detailed_type' in error_msg:
                    if self._is_odoo_18_plus():
                        error_msg = "Invalid product type for Odoo 18+. Valid values: 'goods' (physical products), 'service', or 'combo'."
                    else:
                        error_msg = "Invalid product detailed_type for Odoo 17-. Valid values: 'storable', 'consumable', or 'service'."
                elif 'tracking' in error_msg:
                    error_msg = "Invalid tracking value. Use 'none', 'lot', or 'serial'."
                else:
                    error_msg = "Invalid field value detected in product data."
            elif 'barcode' in error_msg.lower():
                error_msg = "Barcode validation failed. Check if barcode is unique or valid."
            elif len(error_msg) > 200:
                # Truncate very long error messages
                error_msg = error_msg[:200] + "... (error truncated)"
                
            return SyncResult(
                success=False,
                message=f"Failed to update product '{product.name}': {error_msg}",
                product_id=product_id,
                action="error",
                product_name=product.name,
                barcode=getattr(product, 'barcode', None),
                error_details=str(e) if len(str(e)) < 500 else str(e)[:500] + "..."
            )

    def update_product_by_barcode(self, product: ProductMapped) -> SyncResult:
        """Update product using ONLY barcode - no IDs to avoid confusion"""
        if not self.uid:
            raise Exception("Not authenticated")

        try:
            # Update directly using barcode in the domain
            # Get current product details first
            current_products = self.models.execute_kw(
                self.db, self.uid, self.password,
                'product.product', 'search_read',
                [[["barcode", "=", product.barcode]]],
                {'fields': ['id', 'list_price', 'name']}
            )

            if not current_products:
                return SyncResult(
                    success=False,
                    message=f"Product with barcode '{product.barcode}' not found for update",
                    action="error",
                    product_name=product.name,
                    barcode=product.barcode
                )

            current_product = current_products[0]
            product_id = current_product['id']
            current_list_price = float(current_product.get('list_price', 0))
            new_list_price = self._format_decimal_for_odoo(product.list_price)

            print(f"Updating product: {current_product['name']} (ID: {product_id})")

            # Prepare update data
            update_data = {
                'standard_price': self._format_decimal_for_odoo(product.standard_price),
                'available_in_pos': product.available_in_pos,
                'barcode': product.barcode  # Keep the barcode
            }

            # Price protection: only update sale price if new price is higher
            if new_list_price > current_list_price:
                update_data['list_price'] = new_list_price
                print(f"💰 Updating sale price: ${current_list_price} → ${new_list_price}")
            else:
                print(f"🛡️ Protecting higher sale price: keeping ${current_list_price} (XML suggests ${new_list_price})")

            print(f"💸 Updating cost price: ${self._format_decimal_for_odoo(product.standard_price)}")

            # Add version-specific product type field
            update_data.update(self._get_product_type_field())

            # Update using the ID but with verification
            self.models.execute_kw(
                self.db, self.uid, self.password,
                'product.product', 'write',
                [[product_id], update_data]
            )

            print(f"Updated product ID {product_id} with barcode {product.barcode}")

            # Double-check that we updated the right product
            verify_products = self.models.execute_kw(
                self.db, self.uid, self.password,
                'product.product', 'search_read',
                [[["id", "=", product_id], ["barcode", "=", product.barcode]]],
                {'fields': ['name', 'barcode']}
            )

            if not verify_products:
                print(f"⚠️ WARNING: Product verification failed after update!")
            else:
                print(f"✅ Verified: Updated '{verify_products[0]['name']}' with barcode '{verify_products[0]['barcode']}'")

            # Update stock quantity if specified
            if hasattr(product, 'qty_available') and product.qty_available > 0:
                mode = getattr(product, 'quantity_mode', 'replace')
                self.update_stock_quantity(product_id, product.qty_available, mode, product.name)

            return SyncResult(
                success=True,
                message=f"Product '{current_product['name']}' updated successfully by barcode",
                product_id=product_id,
                action="updated",
                product_name=current_product['name'],
                barcode=product.barcode
            )

        except Exception as e:
            import traceback
            import logging

            logger = logging.getLogger(__name__)
            error_msg = str(e)

            logger.error(f"❌ ERROR updating product by barcode '{product.barcode}': {error_msg}")
            print(f"❌ ERROR updating product by barcode '{product.barcode}': {error_msg}")
            print(f"🔍 Full traceback: {traceback.format_exc()}")

            return SyncResult(
                success=False,
                message=f"Failed to update product by barcode '{product.barcode}': {error_msg}",
                action="error",
                product_name=product.name,
                barcode=product.barcode,
                error_details=str(e) if len(str(e)) < 500 else str(e)[:500] + "..."
            )

    def update_stock_quantity(self, product_id: int, quantity: float, mode: str = 'replace', product_name: str = None):
        """Update product stock quantity and create inventory movement

        Args:
            product_id: Product ID
            quantity: Quantity to set or add
            mode: 'replace' to set quantity, 'add' to add to existing quantity
            product_name: Product name for movement reference
        """
        try:
            # Get default location (stock location)
            location_ids = self.models.execute_kw(
                self.db, self.uid, self.password,
                'stock.location', 'search',
                [[['usage', '=', 'internal']], 0, 1]
            )
            
            if not location_ids:
                return
                
            location_id = location_ids[0]
            
            # Check if quant already exists
            quant_ids = self.models.execute_kw(
                self.db, self.uid, self.password,
                'stock.quant', 'search',
                [[['product_id', '=', product_id], ['location_id', '=', location_id]]]
            )
            
            final_quantity = quantity
            
            if quant_ids:
                if mode == 'add':
                    # Get current quantity and add to it
                    current_quant = self.models.execute_kw(
                        self.db, self.uid, self.password,
                        'stock.quant', 'read',
                        [quant_ids[0]],
                        {'fields': ['quantity']}
                    )
                    if current_quant:
                        current_qty = current_quant[0].get('quantity', 0)
                        final_quantity = current_qty + quantity
                        print(f"Adding {quantity} to existing {current_qty} = {final_quantity}")
                
                # Update existing quant
                self.models.execute_kw(
                    self.db, self.uid, self.password,
                    'stock.quant', 'write',
                    [[quant_ids[0]], {'quantity': self._format_decimal_for_odoo(final_quantity)}]
                )
            else:
                # Create new quant (mode doesn't matter for new products)
                self.models.execute_kw(
                    self.db, self.uid, self.password,
                    'stock.quant', 'create',
                    [{
                        'product_id': product_id,
                        'location_id': location_id,
                        'quantity': self._format_decimal_for_odoo(final_quantity)
                    }]
                )

            # Create inventory move to show in movement history
            # Only create move if we're adding/replacing with positive quantity
            if quantity > 0 and product_name:
                move_quantity = quantity if mode == 'replace' else quantity  # For add mode, quantity is already the delta
                # Commented out inventory moves for now - focusing on PDF reports
                # self.create_inventory_move(product_id, move_quantity, product_name)
                print(f"📦 Stock updated: {product_name} (+{move_quantity})")

        except Exception as e:
            # Log error but don't fail the main operation
            print(f"Warning: Could not update stock quantity: {e}")

    def create_inventory_move(self, product_id: int, quantity: float, product_name: str):
        """Create a proper inventory move for incoming merchandise
        This will show up in the product's movement history
        """
        try:
            # Get or create supplier location for "Odoo Sync"
            supplier_location_id = self._get_or_create_supplier_location()

            # Get internal stock location
            stock_location_ids = self.models.execute_kw(
                self.db, self.uid, self.password,
                'stock.location', 'search',
                [[['usage', '=', 'internal'], ['name', 'ilike', 'stock']], 0, 1]
            )

            if not stock_location_ids:
                print("Warning: Could not find stock location")
                return

            stock_location_id = stock_location_ids[0]

            # Create stock move directly as done
            move_data = {
                'name': f'Ingreso XML Odoo Sync - {product_name}',
                'product_id': product_id,
                'product_uom_qty': self._format_decimal_for_odoo(quantity),
                # 'quantity_done': self._format_decimal_for_odoo(quantity),  # Not needed for simple tracking
                'product_uom': 1,  # Units
                'location_id': supplier_location_id,
                'location_dest_id': stock_location_id,
                'reference': 'Ingreso XML Odoo Sync',
                'origin': 'Odoo Sync - XML Import'
                # 'state': 'done'  # Let Odoo handle state automatically
            }

            move_id = self.models.execute_kw(
                self.db, self.uid, self.password,
                'stock.move', 'create',
                [move_data]
            )

            print(f"✅ Registro de ingreso creado ID {move_id} para {product_name} (+{quantity})")
            print(f"    📋 Busca en Odoo → Producto → Historial de movimientos")
            print(f"    📝 Referencia: 'Ingreso XML Odoo Sync'")

            # Simple tracking - let Odoo handle the details automatically

        except Exception as e:
            # Don't fail the main operation if move creation fails
            print(f"Warning: Could not create inventory move: {e}")

    def _get_or_create_supplier_location(self) -> int:
        """Get or create the 'Odoo Sync' supplier location"""
        try:
            # Search for existing "Odoo Sync" location
            location_ids = self.models.execute_kw(
                self.db, self.uid, self.password,
                'stock.location', 'search',
                [[['name', '=', 'Odoo Sync'], ['usage', '=', 'supplier']]]
            )

            if location_ids:
                return location_ids[0]

            # Create new supplier location
            # First get the main supplier location as parent
            supplier_parent_ids = self.models.execute_kw(
                self.db, self.uid, self.password,
                'stock.location', 'search',
                [[['usage', '=', 'supplier'], ['name', '=', 'Partners/Suppliers']], 0, 1]
            )

            parent_id = supplier_parent_ids[0] if supplier_parent_ids else None

            location_data = {
                'name': 'Odoo Sync',
                'usage': 'supplier'
            }

            # Only add parent if found
            if parent_id:
                location_data['location_id'] = parent_id

            location_id = self.models.execute_kw(
                self.db, self.uid, self.password,
                'stock.location', 'create',
                [location_data]
            )

            print(f"✅ Created supplier location 'Odoo Sync' with ID {location_id}")
            return location_id

        except Exception as e:
            print(f"Error creating supplier location: {e}")
            # Fallback: try to find any supplier location
            try:
                fallback_ids = self.models.execute_kw(
                    self.db, self.uid, self.password,
                    'stock.location', 'search',
                    [[['usage', '=', 'supplier']], 0, 1]
                )
                return fallback_ids[0] if fallback_ids else 1
            except:
                return 1  # Default fallback

    def sync_product(self, product: ProductMapped) -> SyncResult:
        """Synchronize a single product (create or update)"""
        try:
            # Ensure we have version info before proceeding
            if not self.odoo_version:
                # Try to get version info if not available
                try:
                    version_info = self.common.version()
                    self.odoo_version = version_info.get('server_version', '17.0')
                    print(f"Detected Odoo version during sync: {self.odoo_version}")
                except Exception as e:
                    print(f"Could not detect version, assuming Odoo 17: {e}")
                    self.odoo_version = '17.0'
            
            # Search directly by barcode - NO IDs, only barcode
            if product.barcode:
                # Check if product exists by searching directly with barcode
                existing_products = self.models.execute_kw(
                    self.db, self.uid, self.password,
                    'product.product', 'search_read',
                    [[["barcode", "=", product.barcode]]],
                    {'fields': ['id', 'name', 'barcode']}
                )

                if existing_products:
                    found_product = existing_products[0]
                    print(f"✅ Product found: '{found_product['name']}' with barcode '{found_product['barcode']}'")
                    print(f"   ID: {found_product['id']} - Will update THIS product only")
                    print(f"Updating with quantity mode: {product.quantity_mode}")
                    return self.update_product_by_barcode(product)
                else:
                    print(f"Product '{product.name}' is new, creating with quantity: {product.qty_available}")
                    return self.create_product(product)
            else:
                # No barcode, create new product
                print(f"Product '{product.name}' has no barcode, creating new")
                return self.create_product(product)
                
        except Exception as e:
            import traceback
            import logging

            logger = logging.getLogger(__name__)
            error_msg = str(e)

            # Enhanced error logging
            logger.error(f"❌ SYNC ERROR for product '{product.name}': {error_msg}")
            logger.error(f"📊 Product details: name='{product.name}', barcode='{getattr(product, 'barcode', 'N/A')}', qty={getattr(product, 'qty_available', 'N/A')}")
            logger.error(f"🔍 Full sync traceback: {traceback.format_exc()}")

            print(f"❌ SYNC ERROR for product '{product.name}': {error_msg}")
            print(f"📊 Product details: name='{product.name}', barcode='{getattr(product, 'barcode', 'N/A')}', qty={getattr(product, 'qty_available', 'N/A')}")
            print(f"🔍 Full sync error: {traceback.format_exc()}")

            return SyncResult(
                success=False,
                message=f"Error syncing product '{product.name}': {error_msg}",
                action="error",
                product_name=product.name,
                barcode=getattr(product, 'barcode', None),
                error_details=str(e) if len(str(e)) < 500 else str(e)[:500] + "..."
            )

    def sync_products(self, products: List[ProductMapped]) -> List[SyncResult]:
        """Synchronize multiple products with before/after stock report"""
        from datetime import datetime

        # Get stock BEFORE sync
        stock_before = {}
        for product in products:
            if product.barcode:
                current_stock = self._get_product_stock_by_barcode(product.barcode)
                stock_before[product.barcode] = {
                    'name': product.name,
                    'barcode': product.barcode,
                    'stock_before': current_stock,
                    'quantity_to_add': product.qty_available if hasattr(product, 'qty_available') else 0
                }

        print(f"📊 Stock capturado ANTES de sincronizar {len(stock_before)} productos")

        # Sync products
        results = []
        for product in products:
            result = self.sync_product(product)
            results.append(result)

        # Get stock AFTER sync
        stock_after = {}
        for product in products:
            if product.barcode:
                final_stock = self._get_product_stock_by_barcode(product.barcode)
                if product.barcode in stock_before:
                    stock_before[product.barcode]['stock_after'] = final_stock

        print(f"📊 Stock capturado DESPUÉS de sincronizar")

        # Generate PDF report
        pdf_path = self._generate_stock_report_pdf(stock_before, results)
        print(f"📋 Reporte PDF generado: {pdf_path}")

        return results

    def sync_products_with_pdf(self, products: List[ProductMapped]) -> tuple:
        """Synchronize multiple products and return results + PDF path"""
        from datetime import datetime

        # Get stock BEFORE sync
        stock_before = {}
        for product in products:
            if product.barcode:
                current_stock = self._get_product_stock_by_barcode(product.barcode)
                stock_before[product.barcode] = {
                    'name': product.name,
                    'barcode': product.barcode,
                    'stock_before': current_stock,
                    'quantity_to_add': product.qty_available if hasattr(product, 'qty_available') else 0
                }

        print(f"📊 Stock capturado ANTES de sincronizar {len(stock_before)} productos")

        # Sync products
        results = []
        for product in products:
            result = self.sync_product(product)
            results.append(result)

        # Get stock AFTER sync
        stock_after = {}
        for product in products:
            if product.barcode:
                final_stock = self._get_product_stock_by_barcode(product.barcode)
                if product.barcode in stock_before:
                    stock_before[product.barcode]['stock_after'] = final_stock

        print(f"📊 Stock capturado DESPUÉS de sincronizar")

        # Generate PDF report
        pdf_path = self._generate_stock_report_pdf(stock_before, results)
        print(f"📋 Reporte PDF generado: {pdf_path}")

        return results, pdf_path

    def get_sales_data_by_date(self, date: str) -> CierreCajaResponse:
        """Get sales data for a specific date grouped by employee and payment method"""
        if not self.uid:
            raise Exception("Not authenticated")
        
        try:
            # Convert date string to datetime objects
            # Odoo stores dates in UTC, so we need to adjust for Ecuador timezone (UTC-5)
            from datetime import datetime, timedelta
            
            # Parse the input date
            input_date = datetime.strptime(date, '%Y-%m-%d')
            
            # For Ecuador timezone (UTC-5), we need to query the correct UTC range
            # When it's 13/09/2025 in Ecuador, we want sales from:
            # 13/09/2025 00:00:00 Ecuador = 13/09/2025 05:00:00 UTC
            # 13/09/2025 23:59:59 Ecuador = 14/09/2025 04:59:59 UTC
            start_date_utc = input_date + timedelta(hours=5)  # 00:00 Ecuador = 05:00 UTC same day
            end_date_utc = input_date + timedelta(days=1, hours=4, minutes=59, seconds=59)  # 23:59 Ecuador = 04:59 UTC next day
            
            start_date = start_date_utc.strftime('%Y-%m-%d %H:%M:%S')
            end_date = end_date_utc.strftime('%Y-%m-%d %H:%M:%S')
            
            print(f"Searching sales from {start_date} to {end_date} (UTC) for Ecuador date {date}")
            
            # Search for POS orders in the date range with more restrictive conditions
            search_domain = [
                ['date_order', '>=', start_date], 
                ['date_order', '<=', end_date], 
                ['state', 'in', ['paid', 'done', 'invoiced']]
            ]
            
            pos_order_ids = self.models.execute_kw(
                self.db, self.uid, self.password,
                'pos.order', 'search',
                [search_domain]
            )
            
            print(f"Found {len(pos_order_ids)} POS orders for the date range")
            print(f"Search domain: {search_domain}")
            
            if not pos_order_ids:
                # Still get POS sessions even if no orders
                pos_sessions = self._get_pos_sessions_for_date(date)
                return CierreCajaResponse(
                    date=date,
                    total_sales=0.0,
                    sales_by_employee=[],
                    payment_methods=[],
                    pos_sessions=pos_sessions
                )
            
            # Get POS order details
            pos_orders = self.models.execute_kw(
                self.db, self.uid, self.password,
                'pos.order', 'read',
                [pos_order_ids],
                {'fields': ['name', 'amount_total', 'user_id', 'date_order', 'payment_ids']}
            )
            
            # Debug: Print the dates of found orders
            for order in pos_orders[:3]:  # Show first 3 orders
                print(f"Order {order['name']}: date_order = {order['date_order']}, amount = {order['amount_total']}")
            
            # Get payment details for all orders
            all_payment_ids = []
            for order in pos_orders:
                if order.get('payment_ids'):
                    all_payment_ids.extend(order['payment_ids'])
            
            payments = []
            if all_payment_ids:
                payments = self.models.execute_kw(
                    self.db, self.uid, self.password,
                    'pos.payment', 'read',
                    [all_payment_ids],
                    {'fields': ['amount', 'payment_method_id', 'pos_order_id']}
                )
            
            # Get payment method details
            payment_method_ids = list(set([p['payment_method_id'][0] for p in payments if p.get('payment_method_id')]))
            payment_methods = {}
            if payment_method_ids:
                payment_method_data = self.models.execute_kw(
                    self.db, self.uid, self.password,
                    'pos.payment.method', 'read',
                    [payment_method_ids],
                    {'fields': ['name']}
                )
                payment_methods = {pm['id']: pm['name'] for pm in payment_method_data}
            
            # Get user details
            user_ids = list(set([order['user_id'][0] for order in pos_orders if order.get('user_id')]))
            users = {}
            if user_ids:
                user_data = self.models.execute_kw(
                    self.db, self.uid, self.password,
                    'res.users', 'read',
                    [user_ids],
                    {'fields': ['name']}
                )
                users = {user['id']: user['name'] for user in user_data}
            
            # Organize data by employee and payment method
            sales_by_employee_method = {}
            payment_method_totals = {}
            total_sales = 0.0
            
            # Create a mapping of payments by order
            payments_by_order = {}
            for payment in payments:
                order_id = payment['pos_order_id'][0]
                if order_id not in payments_by_order:
                    payments_by_order[order_id] = []
                payments_by_order[order_id].append(payment)
            
            for order in pos_orders:
                order_id = order['id']
                user_name = users.get(order['user_id'][0], 'Usuario Desconocido') if order.get('user_id') else 'Usuario Desconocido'
                
                # Get payments for this order
                order_payments = payments_by_order.get(order_id, [])
                
                if not order_payments:
                    # If no payments found, assume cash payment
                    method_name = 'Efectivo'
                    amount = order['amount_total']
                    
                    key = (user_name, method_name)
                    if key not in sales_by_employee_method:
                        sales_by_employee_method[key] = {'total': 0.0, 'count': 0}
                    
                    sales_by_employee_method[key]['total'] += amount
                    sales_by_employee_method[key]['count'] += 1
                    
                    if method_name not in payment_method_totals:
                        payment_method_totals[method_name] = {'total': 0.0, 'count': 0}
                    payment_method_totals[method_name]['total'] += amount
                    payment_method_totals[method_name]['count'] += 1
                    
                    total_sales += amount
                else:
                    # Process each payment for this order
                    for payment in order_payments:
                        method_id = payment['payment_method_id'][0] if payment.get('payment_method_id') else None
                        method_name = payment_methods.get(method_id, 'Otro') if method_id else 'Efectivo'
                        amount = payment['amount']
                        
                        # Map common payment method names
                        if 'efectivo' in method_name.lower() or 'cash' in method_name.lower():
                            method_name = 'Efectivo'
                        elif 'transfer' in method_name.lower() or 'banco' in method_name.lower():
                            method_name = 'Transferencia'
                        elif 'datafast' in method_name.lower() or 'tarjeta' in method_name.lower():
                            method_name = 'Datafast'
                        
                        key = (user_name, method_name)
                        if key not in sales_by_employee_method:
                            sales_by_employee_method[key] = {'total': 0.0, 'count': 0}
                        
                        sales_by_employee_method[key]['total'] += amount
                        sales_by_employee_method[key]['count'] += 1
                        
                        if method_name not in payment_method_totals:
                            payment_method_totals[method_name] = {'total': 0.0, 'count': 0}
                        payment_method_totals[method_name]['total'] += amount
                        payment_method_totals[method_name]['count'] += 1
                        
                        total_sales += amount
            
            # Convert to response format
            sales_by_employee = []
            for (employee, method), data in sales_by_employee_method.items():
                sales_by_employee.append(SaleByEmployee(
                    employee_name=employee,
                    payment_method=method,
                    total_amount=round(data['total'], 2),
                    transaction_count=data['count']
                ))
            
            payment_methods_summary = []
            for method, data in payment_method_totals.items():
                payment_methods_summary.append(PaymentMethodSummary(
                    method=method,
                    total=round(data['total'], 2),
                    count=data['count']
                ))
            
            # Get POS sessions for the date
            pos_sessions = self._get_pos_sessions_for_date(date)

            return CierreCajaResponse(
                date=date,
                total_sales=round(total_sales, 2),
                sales_by_employee=sales_by_employee,
                payment_methods=payment_methods_summary,
                pos_sessions=pos_sessions
            )
            
        except Exception as e:
            print(f"Error getting sales data: {e}")
            raise Exception(f"Error retrieving sales data: {str(e)}")

    def _get_pos_sessions_for_date(self, date: str) -> List[POSSession]:
        """Get POS sessions for a specific date"""
        try:
            from datetime import datetime, timedelta

            # Parse the input date
            input_date = datetime.strptime(date, '%Y-%m-%d')

            # For Ecuador timezone (UTC-5), we need to query the correct UTC range
            start_date_utc = input_date + timedelta(hours=5)  # 00:00 Ecuador = 05:00 UTC same day
            end_date_utc = input_date + timedelta(days=1, hours=4, minutes=59, seconds=59)  # 23:59 Ecuador = 04:59 UTC next day

            start_date = start_date_utc.strftime('%Y-%m-%d %H:%M:%S')
            end_date = end_date_utc.strftime('%Y-%m-%d %H:%M:%S')

            # Search for POS sessions that started during the target date
            session_domain = [
                ['start_at', '>=', start_date],
                ['start_at', '<=', end_date]
            ]

            session_ids = self.models.execute_kw(
                self.db, self.uid, self.password,
                'pos.session', 'search',
                [session_domain]
            )

            if not session_ids:
                return []

            # Get session details
            sessions_data = self.models.execute_kw(
                self.db, self.uid, self.password,
                'pos.session', 'read',
                [session_ids],
                {'fields': ['name', 'state', 'user_id', 'start_at', 'stop_at', 'config_id', 'cash_register_balance_start', 'cash_register_balance_end_real']}
            )

            # Get user names
            user_ids = list(set([session['user_id'][0] for session in sessions_data if session.get('user_id')]))
            users = {}
            if user_ids:
                user_data = self.models.execute_kw(
                    self.db, self.uid, self.password,
                    'res.users', 'read',
                    [user_ids],
                    {'fields': ['name']}
                )
                users = {user['id']: user['name'] for user in user_data}

            # Get POS config names
            config_ids = list(set([session['config_id'][0] for session in sessions_data if session.get('config_id')]))
            configs = {}
            if config_ids:
                config_data = self.models.execute_kw(
                    self.db, self.uid, self.password,
                    'pos.config', 'read',
                    [config_ids],
                    {'fields': ['name']}
                )
                configs = {config['id']: config['name'] for config in config_data}

            # Helper function to convert UTC datetime to Ecuador time
            def convert_utc_to_ecuador(utc_datetime_str):
                if not utc_datetime_str or utc_datetime_str is False:
                    return None
                try:
                    # Parse UTC datetime
                    utc_dt = datetime.strptime(utc_datetime_str, '%Y-%m-%d %H:%M:%S')
                    # Convert to Ecuador time (UTC-5)
                    ecuador_dt = utc_dt - timedelta(hours=5)
                    return ecuador_dt.strftime('%Y-%m-%d %H:%M:%S')
                except:
                    return utc_datetime_str

            # Convert to POSSession objects
            pos_sessions = []
            for session in sessions_data:
                pos_sessions.append(POSSession(
                    id=session['id'],
                    name=session['name'],
                    state=session['state'],
                    user_id=session['user_id'][0] if session.get('user_id') else 0,
                    user_name=users.get(session['user_id'][0], 'Usuario Desconocido') if session.get('user_id') else 'Usuario Desconocido',
                    start_at=convert_utc_to_ecuador(session.get('start_at')),
                    stop_at=convert_utc_to_ecuador(session.get('stop_at')),
                    config_id=session['config_id'][0] if session.get('config_id') else 0,
                    config_name=configs.get(session['config_id'][0], 'Configuración Desconocida') if session.get('config_id') else 'Configuración Desconocida',
                    cash_register_balance_start=session.get('cash_register_balance_start', 0.0),
                    cash_register_balance_end_real=session.get('cash_register_balance_end_real')
                ))

            return pos_sessions

        except Exception as e:
            print(f"Error getting POS sessions: {e}")
            return []

    def _generate_transfer_pdf(self, products: List[Dict]) -> str:
        """Generate a PDF report for transfer verification and save it to reports folder"""
        import os

        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.5*inch)

        # Safe text truncation function for UTF-8
        def safe_truncate(text, max_length):
            """Safely truncate text without breaking UTF-8 characters"""
            if not text:
                return ""
            text = str(text)
            if len(text) <= max_length:
                return text

            # Ensure we don't break in the middle of a UTF-8 character
            truncated = text[:max_length]
            try:
                truncated.encode('utf-8')
                return truncated + "..."
            except UnicodeEncodeError:
                # If encoding fails, back off one character at a time
                for i in range(max_length - 1, 0, -1):
                    try:
                        truncated = text[:i]
                        truncated.encode('utf-8')
                        return truncated + "..."
                    except UnicodeEncodeError:
                        continue
                return "..."

        # Styles
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=18,
            textColor=colors.darkblue,
            spaceAfter=30,
            alignment=1  # Center
        )
        
        # Story elements
        story = []
        
        # Title
        title = Paragraph("LISTA DE TRANSFERENCIA A SUCURSAL", title_style)
        story.append(title)
        
        # Date and info
        now = datetime.now()
        info_style = ParagraphStyle(
            'InfoStyle',
            parent=styles['Normal'],
            fontSize=10,
            spaceBefore=10,
            spaceAfter=20
        )
        
        info_text = f"""
        <b>Fecha y Hora:</b> {now.strftime('%d/%m/%Y %H:%M:%S')}<br/>
        <b>Generado por:</b> Sistema Pladsh Odoo Sync<br/>
        <b>Total de productos:</b> {len(products)}<br/>
        <b>IMPORTANTE:</b> Esta lista debe ser verificada físicamente antes de confirmar la transferencia.
        """
        
        info_para = Paragraph(info_text, info_style)
        story.append(info_para)
        story.append(Spacer(1, 20))
        
        # Table data
        data = [['#', 'Producto', 'Código de Barras', 'Cantidad', 'Precio Costo', 'Total']]
        
        total_value = 0
        for i, product in enumerate(products, 1):
            quantity = product['quantity']
            price = product['standard_price']
            total = quantity * price
            total_value += total
            
            data.append([
                str(i),
                safe_truncate(product['name'], 40),
                str(product['barcode']),
                str(quantity),
                f"${price:.2f}".replace('.', ','),
                f"${total:.2f}".replace('.', ',')
            ])
        
        # Add total row
        data.append(['', '', '', '', 'TOTAL:', f"${total_value:.2f}".replace('.', ',')])
        
        # Create table
        table = Table(data, colWidths=[0.5*inch, 3*inch, 1.2*inch, 0.8*inch, 1*inch, 1*inch])
        
        # Table style
        table.setStyle(TableStyle([
            # Header
            ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            
            # Body
            ('FONTNAME', (0, 1), (-1, -2), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -2), 9),
            ('GRID', (0, 0), (-1, -2), 1, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            
            # Alternate row colors
            ('BACKGROUND', (0, 1), (-1, -2), colors.beige),
            ('BACKGROUND', (0, 2), (-1, -1), colors.lightgrey),
            
            # Total row
            ('BACKGROUND', (0, -1), (-1, -1), colors.lightblue),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, -1), (-1, -1), 10),
        ]))
        
        story.append(table)
        story.append(Spacer(1, 30))
        
        # Verification section
        verification_style = ParagraphStyle(
            'VerificationStyle',
            parent=styles['Normal'],
            fontSize=12,
            spaceBefore=20
        )
        
        verification_text = """
        <b>VERIFICACIÓN FÍSICA</b><br/><br/>
        Confirmo que los productos listados arriba coinciden con los productos físicos que se están transfiriendo:<br/><br/>
        
        <b>Responsable de Transferencia:</b> ___________________________________________<br/><br/>
        <b>Firma:</b> ___________________________________________<br/><br/><br/>
        
        <b>Supervisor que Verifica:</b> ___________________________________________<br/><br/>
        <b>Firma:</b> ___________________________________________<br/><br/><br/>
        
        <b>Fecha de Verificación:</b> ____/____/_______ <b>Hora:</b> ______:______<br/><br/>
        
        <b>Observaciones:</b><br/>
        ________________________________________________________________________<br/>
        ________________________________________________________________________<br/>
        ________________________________________________________________________<br/>
        """
        
        verification_para = Paragraph(verification_text, verification_style)
        story.append(verification_para)
        
        # Build PDF
        doc.build(story)

        # Get PDF content as base64
        buffer.seek(0)
        pdf_content = buffer.getvalue()
        buffer.close()

        # Save PDF to reports folder
        reports_dir = os.path.join(os.path.dirname(__file__), 'reports')
        os.makedirs(reports_dir, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        pdf_filename = f'transfer_list_{timestamp}.pdf'
        pdf_path = os.path.join(reports_dir, pdf_filename)

        with open(pdf_path, 'wb') as f:
            f.write(pdf_content)

        print(f"✅ PDF guardado en: {pdf_path}")

        return base64.b64encode(pdf_content).decode('utf-8')

    def process_branch_transfer(self, transfer_items: List[Dict]) -> TransferResponse:
        """Process transfer to branch - reduce inventory and generate transfer data"""
        if not self.uid:
            raise Exception("Not authenticated")
        
        try:
            processed_products = []
            
            for item in transfer_items:
                barcode = item['barcode']
                requested_quantity = item['quantity']
                
                # Search product by barcode
                product_id = self.search_product_by_barcode(barcode)
                if not product_id:
                    print(f"Product not found: {barcode}")
                    continue
                
                # Get product details
                product_details = self.get_product_details(product_id)
                if not product_details:
                    print(f"Could not get details for product: {barcode}")
                    continue
                
                # Validate stock availability
                available_stock = product_details.get('qty_available', 0)
                max_allowed = int(available_stock * 0.5)  # 50% maximum
                
                if requested_quantity > available_stock:
                    print(f"Insufficient stock for {barcode}: requested {requested_quantity}, available {available_stock}")
                    continue
                
                if requested_quantity > max_allowed:
                    print(f"Exceeds 50% limit for {barcode}: requested {requested_quantity}, max allowed {max_allowed}")
                    continue
                
                # NOTE: Inventory is NOT reduced here - this is just preparation
                # Stock will be reduced later when the transfer is confirmed
                print(f"Prepared for transfer: {product_details['name']} - {requested_quantity} units")
                
                # Add to processed list with updated information from main location
                processed_products.append({
                    'name': product_details['name'],
                    'barcode': barcode,
                    'quantity': requested_quantity,
                    'standard_price': product_details['standard_price'],
                    'list_price': product_details['list_price'],
                    'tracking': product_details.get('tracking', 'none'),
                    'available_in_pos': product_details.get('available_in_pos', True)
                })
            
            if not processed_products:
                return TransferResponse(
                    success=False,
                    message="No se pudieron procesar productos para la transferencia",
                    processed_count=0
                )
            
            # Generate XML content for branch upload
            xml_content = self._generate_transfer_xml(processed_products)
            
            # Generate PDF for verification
            pdf_content = self._generate_transfer_pdf(processed_products)
            
            return TransferResponse(
                success=True,
                message=f"Lista de transferencia preparada: {len(processed_products)} productos. INVENTARIO NO REDUCIDO - requiere confirmación.",
                xml_content=xml_content,
                pdf_content=pdf_content,  # Add PDF content
                processed_count=len(processed_products),
                inventory_reduced=False  # Changed to False - no reduction yet
            )
            
        except Exception as e:
            print(f"Error processing branch transfer: {e}")
            raise Exception(f"Error processing transfer: {str(e)}")

    def confirm_branch_transfer(self, transfer_items: List[Dict]) -> TransferResponse:
        """Confirm transfer to branch - ACTUALLY reduce inventory and generate final transfer data"""
        if not self.uid:
            raise Exception("Not authenticated")
        
        try:
            processed_products = []
            
            for item in transfer_items:
                barcode = item['barcode']
                requested_quantity = item['quantity']
                
                # Search product by barcode
                product_id = self.search_product_by_barcode(barcode)
                if not product_id:
                    print(f"Product not found: {barcode}")
                    continue
                
                # Get product details
                product_details = self.get_product_details(product_id)
                if not product_details:
                    print(f"Could not get details for product: {barcode}")
                    continue
                
                # Validate stock availability (re-check at confirmation time)
                available_stock = product_details.get('qty_available', 0)
                max_allowed = int(available_stock * 0.5)  # 50% maximum
                
                if requested_quantity > available_stock:
                    print(f"Insufficient stock for {barcode}: requested {requested_quantity}, available {available_stock}")
                    continue
                
                if requested_quantity > max_allowed:
                    print(f"Exceeds 50% limit for {barcode}: requested {requested_quantity}, max allowed {max_allowed}")
                    continue
                
                # NOW we actually reduce inventory in main location
                try:
                    self.reduce_stock_quantity(product_id, requested_quantity)
                    print(f"CONFIRMED: Reduced stock for {product_details['name']}: -{requested_quantity} units")
                except Exception as e:
                    print(f"Failed to reduce stock for {barcode}: {e}")
                    continue
                
                # Add to processed list with updated information from main location
                processed_products.append({
                    'name': product_details['name'],
                    'barcode': barcode,
                    'quantity': requested_quantity,
                    'standard_price': product_details['standard_price'],
                    'list_price': product_details['list_price'],
                    'tracking': product_details.get('tracking', 'none'),
                    'available_in_pos': product_details.get('available_in_pos', True)
                })
            
            if not processed_products:
                return TransferResponse(
                    success=False,
                    message="No se pudieron confirmar productos para la transferencia",
                    processed_count=0
                )
            
            # Generate XML content for branch upload
            xml_content = self._generate_transfer_xml(processed_products)
            
            return TransferResponse(
                success=True,
                message=f"¡Transferencia CONFIRMADA! {len(processed_products)} productos. Inventario reducido del principal.",
                xml_content=xml_content,
                processed_count=len(processed_products),
                inventory_reduced=True  # NOW we actually reduced inventory
            )
            
        except Exception as e:
            print(f"Error confirming branch transfer: {e}")
            raise Exception(f"Error confirming transfer: {str(e)}")

    def reduce_stock_quantity(self, product_id: int, quantity: float):
        """Reduce product stock quantity from main location"""
        try:
            # Convert product.template ID to product.product ID for stock operations
            # Stock quants are associated with product variants (product.product), not templates
            product_variant_ids = self.models.execute_kw(
                self.db, self.uid, self.password,
                'product.product', 'search',
                [[['product_tmpl_id', '=', product_id]]]
            )

            if not product_variant_ids:
                raise Exception(f"No product variant found for template ID {product_id}")

            # Use the first variant (most products have only one variant)
            variant_id = product_variant_ids[0]
            print(f"🔄 Using product variant ID {variant_id} for template ID {product_id}")

            # Get default location (stock location)
            location_ids = self.models.execute_kw(
                self.db, self.uid, self.password,
                'stock.location', 'search',
                [[['usage', '=', 'internal']], 0, 1]
            )

            if not location_ids:
                raise Exception("No internal location found")

            location_id = location_ids[0]

            # Check if quant exists using the variant ID
            quant_ids = self.models.execute_kw(
                self.db, self.uid, self.password,
                'stock.quant', 'search',
                [[['product_id', '=', variant_id], ['location_id', '=', location_id]]]
            )
            
            if quant_ids:
                # Get current quantity
                current_quant = self.models.execute_kw(
                    self.db, self.uid, self.password,
                    'stock.quant', 'read',
                    [quant_ids[0]],
                    {'fields': ['quantity']}
                )
                
                if current_quant:
                    current_qty = current_quant[0].get('quantity', 0)
                    new_quantity = max(0, current_qty - quantity)  # Don't go below 0
                    
                    # Update quant with reduced quantity
                    self.models.execute_kw(
                        self.db, self.uid, self.password,
                        'stock.quant', 'write',
                        [[quant_ids[0]], {'quantity': self._format_decimal_for_odoo(new_quantity)}]
                    )
                    
                    print(f"Stock reduced from {current_qty} to {new_quantity} (reduced by {quantity})")
                else:
                    raise Exception("Could not read current stock quantity")
            else:
                raise Exception("No stock quant found for product")
                
        except Exception as e:
            raise Exception(f"Could not reduce stock: {e}")

    def _generate_transfer_xml(self, products: List[Dict]) -> str:
        """Generate XML content for branch transfer (compatible with existing upload system) and save it to reports folder"""
        from datetime import datetime
        from xml.sax.saxutils import escape
        import os

        # Generate a simple XML structure compatible with D'Mujeres format
        current_date = datetime.now().strftime('%Y-%m-%d')
        current_datetime = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
        
        xml_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<autorizacion>
    <comprobante><![CDATA[<?xml version="1.0" encoding="UTF-8"?>
<factura id="comprobante" version="1.1.0">
    <infoTributaria>
        <ambiente>1</ambiente>
        <tipoEmision>1</tipoEmision>
        <razonSocial>Transferencia Sucursal</razonSocial>
        <ruc>0000000000001</ruc>
        <claveAcceso>0000000000000000000000000000000000000000000001</claveAcceso>
        <codDoc>01</codDoc>
        <estab>001</estab>
        <ptoEmi>001</ptoEmi>
        <secuencial>000000001</secuencial>
        <dirMatriz>Local Principal</dirMatriz>
    </infoTributaria>
    <infoFactura>
        <fechaEmision>{current_date}</fechaEmision>
        <dirEstablecimiento>Local Principal</dirEstablecimiento>
        <razonSocialComprador>Sucursal</razonSocialComprador>
        <identificacionComprador>0000000000</identificacionComprador>
        <totalSinImpuestos>0.00</totalSinImpuestos>
        <totalDescuento>0.00</totalDescuento>
        <propina>0.00</propina>
        <importeTotal>0.00</importeTotal>
        <moneda>DOLAR</moneda>
    </infoFactura>
    <detalles>'''
        
        for product in products:
            xml_content += f'''
        <detalle>
            <codigoPrincipal>{escape(str(product['barcode']))}</codigoPrincipal>
            <codigoAuxiliar>{escape(str(product['barcode']))}</codigoAuxiliar>
            <descripcion>{escape(str(product['name']))}</descripcion>
            <cantidad>{product['quantity']}</cantidad>
            <precioUnitario>{product['standard_price']}</precioUnitario>
            <descuento>0.00</descuento>
            <precioTotalSinImpuesto>{product['quantity'] * product['standard_price']}</precioTotalSinImpuesto>
        </detalle>'''
        
        xml_content += '''
    </detalles>
</factura>]]></comprobante>
</autorizacion>'''

        # Save XML to reports folder
        reports_dir = os.path.join(os.path.dirname(__file__), 'reports')
        os.makedirs(reports_dir, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        xml_filename = f'transfer_list_{timestamp}.xml'
        xml_path = os.path.join(reports_dir, xml_filename)

        with open(xml_path, 'w', encoding='utf-8') as f:
            f.write(xml_content)

        print(f"✅ XML guardado en: {xml_path}")

        return xml_content
    
    def confirm_branch_transfer_with_dual_auth(self, transfer_items: List[Dict], branch_client: 'OdooClient') -> TransferResponse:
        """Confirm transfer to branch with dual authentication - reduce inventory from principal and add to branch"""
        if not self.uid:
            raise Exception("Principal Odoo client not authenticated")
        
        if not branch_client.uid:
            raise Exception("Branch Odoo client not authenticated")
        
        try:
            processed_products = []
            
            for item in transfer_items:
                barcode = item['barcode']
                requested_quantity = item['quantity']
                
                # Search product by barcode in PRINCIPAL location
                principal_product_id = self.search_product_by_barcode(barcode)
                if not principal_product_id:
                    print(f"Product not found in principal location: {barcode}")
                    continue
                
                # Get product details from principal
                principal_product_details = self.get_product_details(principal_product_id)
                if not principal_product_details:
                    print(f"Could not get details for product in principal: {barcode}")
                    continue
                
                # Search product by barcode in BRANCH location
                branch_product_id = branch_client.search_product_by_barcode(barcode)
                
                if not branch_product_id:
                    # ✅ PRODUCTO NO EXISTE EN SUCURSAL → CREAR AUTOMÁTICAMENTE
                    print(f"Product not found in branch location: {barcode} - CREATING automatically")
                    
                    # Crear ProductMapped con datos del principal para homogenizar
                    from models import ProductMapped
                    mapped_product = ProductMapped(
                        name=principal_product_details['name'],
                        barcode=barcode,
                        standard_price=principal_product_details['standard_price'],
                        list_price=principal_product_details['list_price'],
                        qty_available=0,  # Iniciar con 0, se sumará después
                        tracking='none',  # Usar configuración por defecto, no copiar del principal
                        available_in_pos=True,  # Usar configuración por defecto, no copiar del principal
                        type='storable'
                    )
                    
                    # Crear producto en sucursal usando sync_product (que maneja crear/actualizar)
                    sync_result = branch_client.sync_product(mapped_product)
                    
                    if not sync_result.success:
                        print(f"❌ Failed to create product {barcode} in branch: {sync_result.message}")
                        continue
                    
                    branch_product_id = sync_result.product_id
                    print(f"✅ Created product {barcode} in branch with ID: {branch_product_id}")
                    
                    # Get product details from newly created product
                    branch_product_details = branch_client.get_product_details(branch_product_id)
                else:
                    # ✅ PRODUCTO EXISTE → HOMOGENIZAR DATOS CON EL PRINCIPAL
                    print(f"Product exists in branch: {barcode} - SYNCHRONIZING data with principal")
                    
                    # Get current product details from branch
                    branch_product_details = branch_client.get_product_details(branch_product_id)
                    
                    # Homogenizar datos: actualizar precios y nombre desde el principal
                    from models import ProductMapped
                    update_data = ProductMapped(
                        name=principal_product_details['name'],  # Sincronizar nombre
                        barcode=barcode,
                        standard_price=principal_product_details['standard_price'],  # Sincronizar costo
                        list_price=principal_product_details['list_price'],  # Sincronizar precio
                        qty_available=0,  # No cambiar cantidad aquí
                        tracking=branch_product_details.get('tracking', 'none'),  # MANTENER configuración de la sucursal
                        available_in_pos=branch_product_details.get('available_in_pos', True)  # MANTENER configuración de la sucursal
                    )
                    update_data.quantity_mode = 'add'  # Importante: no reemplazar stock
                    
                    # Actualizar producto en sucursal para homogenizar
                    update_result = branch_client.update_product(branch_product_id, update_data)
                    if update_result.success:
                        print(f"✅ Synchronized product data {barcode} in branch")
                    else:
                        print(f"⚠️ Warning: Could not sync product data {barcode}: {update_result.message}")
                
                if not branch_product_details:
                    print(f"Could not get details for product in branch: {barcode}")
                    continue
                
                # Validate stock availability in principal (re-check at confirmation time)
                principal_stock_before = principal_product_details.get('qty_available', 0)
                branch_stock_before = branch_product_details.get('qty_available', 0)

                if requested_quantity > principal_stock_before:
                    print(f"Insufficient stock in principal for {barcode}: requested {requested_quantity}, available {principal_stock_before}")
                    continue

                # STEP 1: Reduce inventory in PRINCIPAL location
                try:
                    self.reduce_stock_quantity(principal_product_id, requested_quantity)
                    print(f"✅ Reduced {requested_quantity} units of {barcode} from principal location")

                except Exception as e:
                    print(f"❌ Error reducing inventory in principal for {barcode}: {e}")
                    continue

                # STEP 2: Add inventory in BRANCH location
                try:
                    print(f"📋 Branch stock before: {branch_stock_before} units")

                    # Add stock using inventory adjustment in branch
                    branch_client.add_stock_quantity(branch_product_id, requested_quantity)

                    # Get final stock amounts after transfer
                    principal_stock_after = self.get_product_details(principal_product_id).get('qty_available', 0)
                    branch_stock_after = branch_client.get_product_details(branch_product_id).get('qty_available', 0)

                    print(f"✅ TRANSFER COMPLETE: {requested_quantity} units of '{principal_product_details['name']}' ({barcode})")
                    print(f"   Principal: {principal_stock_before} → {principal_stock_after} units")
                    print(f"   Branch: {branch_stock_before} → {branch_stock_after} units")

                except Exception as e:
                    print(f"❌ Error adding inventory in branch for {barcode}: {e}")
                    print(f"⚠️  WARNING: Principal inventory was reduced but branch addition failed!")
                    print(f"⚠️  Manual correction may be needed for product {barcode}")
                    continue
                
                # Add to processed list with stock information
                processed_products.append({
                    'barcode': barcode,
                    'name': principal_product_details.get('name', 'Unknown'),
                    'quantity': requested_quantity,
                    'standard_price': principal_product_details.get('standard_price', 0),
                    'list_price': principal_product_details.get('list_price', 0),
                    'principal_stock_before': principal_stock_before,
                    'principal_stock_after': principal_stock_after,
                    'branch_stock_before': branch_stock_before,
                    'branch_stock_after': branch_stock_after
                })
            
            processed_count = len(processed_products)
            
            # Generate PDF report for the transfer
            pdf_path = self._generate_transfer_report_pdf(processed_products)
            pdf_filename = None
            if pdf_path:
                import os
                pdf_filename = os.path.basename(pdf_path)
                print(f"📋 Transfer PDF report generated: {pdf_filename}")

            return TransferResponse(
                success=True,
                message=f"¡Transferencia DUAL CONFIRMADA! {processed_count} productos transferidos. Inventario reducido del principal y agregado a la sucursal.",
                xml_content=None,  # No need to generate XML in admin step
                processed_count=processed_count,
                inventory_reduced=True,
                pdf_filename=pdf_filename
            )
            
        except Exception as e:
            print(f"Error in dual authentication transfer: {e}")
            raise Exception(f"Transfer failed: {str(e)}")

    def _generate_transfer_report_pdf(self, transfer_data: list) -> str:
        """Generate PDF report for admin transfers"""
        try:
            from reportlab.lib.pagesizes import letter, A4
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib import colors
            from reportlab.lib.units import inch
            from datetime import datetime
            import os

            # Create reports directory if it doesn't exist
            reports_dir = os.path.join(os.path.dirname(__file__), 'reports')
            os.makedirs(reports_dir, exist_ok=True)

            # Generate filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"transfer_admin_report_{timestamp}.pdf"
            filepath = os.path.join(reports_dir, filename)

            # Create PDF document
            doc = SimpleDocTemplate(
                filepath,
                pagesize=A4
            )
            elements = []
            styles = getSampleStyleSheet()

            # Safe text truncation function for UTF-8
            def safe_truncate(text, max_length):
                """Safely truncate text without breaking UTF-8 characters"""
                if not text:
                    return ""
                text = str(text)
                if len(text) <= max_length:
                    return text

                # Ensure we don't break in the middle of a UTF-8 character
                truncated = text[:max_length]
                try:
                    truncated.encode('utf-8')
                    return truncated + "..."
                except UnicodeEncodeError:
                    # If encoding fails, back off one character at a time
                    for i in range(max_length - 1, 0, -1):
                        try:
                            truncated = text[:i]
                            truncated.encode('utf-8')
                            return truncated + "..."
                        except UnicodeEncodeError:
                            continue
                    return "..."

            # Title with proper UTF-8 handling
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Heading1'],
                fontSize=16,
                spaceAfter=30,
                alignment=1  # Center alignment
            )
            title_text = "Reporte de Transferencia Admin"
            title = Paragraph(title_text, title_style)
            elements.append(title)

            # Subtitle with date
            subtitle = Paragraph(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal'])
            elements.append(subtitle)
            elements.append(Spacer(1, 20))

            # Summary
            total_products = len(transfer_data)
            total_value = sum(item.get('standard_price', 0) * item.get('quantity', 0) for item in transfer_data)

            summary_data = [
                ["Resumen de Transferencia", ""],
                ["Total de productos transferidos:", str(total_products)],
                ["Valor total transferido:", f"${total_value:.2f}"],
                ["Tipo de transferencia:", "Admin (Principal → Sucursal)"]
            ]

            summary_table = Table(summary_data, colWidths=[3*inch, 2*inch])
            summary_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 12),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))

            elements.append(summary_table)
            elements.append(Spacer(1, 30))

            # Transfer details table
            if transfer_data:
                details_title = Paragraph("Detalles de Productos Transferidos", styles['Heading2'])
                elements.append(details_title)
                elements.append(Spacer(1, 10))

                # Table headers
                table_data = [
                    ["Código", "Producto", "Cantidad", "Stock Principal", "Stock Sucursal", "Precio Costo"]
                ]

                # Add sub-headers for stock columns
                subheader_data = [
                    ["", "", "Transferida", "Antes | Después", "Antes | Después", "Unitario"]
                ]

                # Add product data
                for item in transfer_data:
                    barcode = item.get('barcode', 'N/A')
                    name = safe_truncate(item.get('name', 'N/A'), 25)
                    quantity = item.get('quantity', 0)
                    standard_price = item.get('standard_price', 0)

                    # Stock information
                    principal_before = item.get('principal_stock_before', 0)
                    principal_after = item.get('principal_stock_after', 0)
                    branch_before = item.get('branch_stock_before', 0)
                    branch_after = item.get('branch_stock_after', 0)

                    table_data.append([
                        str(barcode),
                        name,
                        f"{quantity:.0f}",
                        f"{principal_before:.0f} | {principal_after:.0f}",
                        f"{branch_before:.0f} | {branch_after:.0f}",
                        f"${standard_price:.2f}"
                    ])

                # Combine headers and data
                final_table_data = table_data[:1] + subheader_data + table_data[1:]

                # Create table
                details_table = Table(final_table_data, colWidths=[1.0*inch, 2.2*inch, 0.8*inch, 1.0*inch, 1.0*inch, 0.8*inch])
                details_table.setStyle(TableStyle([
                    # Main header style
                    ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 10),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 8),

                    # Sub-header style
                    ('BACKGROUND', (0, 1), (-1, 1), colors.lightblue),
                    ('TEXTCOLOR', (0, 1), (-1, 1), colors.black),
                    ('FONTNAME', (0, 1), (-1, 1), 'Helvetica'),
                    ('FONTSIZE', (0, 1), (-1, 1), 8),
                    ('BOTTOMPADDING', (0, 1), (-1, 1), 6),

                    # Data rows
                    ('BACKGROUND', (0, 2), (-1, -1), colors.white),
                    ('FONTNAME', (0, 2), (-1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 2), (-1, -1), 8),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black),

                    # Alternate row colors for data
                    ('ROWBACKGROUNDS', (0, 2), (-1, -1), [colors.white, colors.lightgrey])
                ]))

                elements.append(details_table)

            # Footer with transfer info
            elements.append(Spacer(1, 20))
            footer_text = "Este reporte muestra los productos transferidos desde la ubicación principal hacia la sucursal. Las columnas 'Stock Principal' y 'Stock Sucursal' muestran las cantidades antes y después de la transferencia en cada ubicación."
            footer = Paragraph(footer_text, styles['Normal'])
            elements.append(footer)

            # Build PDF
            doc.build(elements)

            return filepath

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"⚠️ Warning: Could not generate transfer PDF report: {e}")
            print(f"🔍 Full error: {error_details}")
            return None
    
    def add_stock_quantity(self, product_id: int, quantity: float):
        """Add product stock quantity to location (for branch transfers)"""
        try:
            # Convert product.template ID to product.product ID for stock operations
            # Stock quants are associated with product variants (product.product), not templates
            product_variant_ids = self.models.execute_kw(
                self.db, self.uid, self.password,
                'product.product', 'search',
                [[['product_tmpl_id', '=', product_id]]]
            )

            if not product_variant_ids:
                raise Exception(f"No product variant found for template ID {product_id}")

            # Use the first variant (most products have only one variant)
            variant_id = product_variant_ids[0]
            print(f"🔄 Using product variant ID {variant_id} for template ID {product_id}")

            # Get default location (stock location)
            location_ids = self.models.execute_kw(
                self.db, self.uid, self.password,
                'stock.location', 'search',
                [[['usage', '=', 'internal']], 0, 1]
            )

            if not location_ids:
                raise Exception("No internal location found")

            location_id = location_ids[0]

            # Check if quant exists using the variant ID
            quant_ids = self.models.execute_kw(
                self.db, self.uid, self.password,
                'stock.quant', 'search',
                [[['product_id', '=', variant_id], ['location_id', '=', location_id]]]
            )
            
            if quant_ids:
                # Get current quantity and add to it
                quant_data = self.models.execute_kw(
                    self.db, self.uid, self.password,
                    'stock.quant', 'read',
                    [quant_ids[0]], {'fields': ['quantity']}
                )
                current_quantity = quant_data[0]['quantity']
                new_quantity = current_quantity + quantity
                
                # Update with new quantity
                self.models.execute_kw(
                    self.db, self.uid, self.password,
                    'stock.quant', 'write',
                    [[quant_ids[0]], {'quantity': self._format_decimal_for_odoo(new_quantity)}]
                )
                
                print(f"📦 Updated stock: {current_quantity} + {quantity} = {new_quantity} units for product {variant_id}")
                
            else:
                # Create new quant with initial quantity
                self.models.execute_kw(
                    self.db, self.uid, self.password,
                    'stock.quant', 'create',
                    [{
                        'product_id': variant_id,
                        'location_id': location_id,
                        'quantity': self._format_decimal_for_odoo(quantity)
                    }]
                )

                print(f"📦 Created new stock entry: {quantity} units for product {variant_id}")
            
        except Exception as e:
            print(f"❌ Error adding stock quantity: {e}")
            raise Exception(f"Failed to add stock: {str(e)}")

    def fix_tracking_products(self, products_with_tracking_issues: List[ProductMapped]) -> List[SyncResult]:
        """
        Maneja productos que necesitan rastreo pero ya tienen movimientos de inventario.
        Proceso:
        1. Archiva el producto original (que no puede activar rastreo)
        2. Crea un producto nuevo con los mismos datos pero con rastreo activado
        3. Asigna el stock correcto al nuevo producto

        Args:
            products_with_tracking_issues: Lista de productos que necesitan ser recreados con rastreo

        Returns:
            Lista de SyncResult con el resultado de cada operación
        """
        if not self.uid:
            raise Exception("Not authenticated")

        results = []

        for product in products_with_tracking_issues:
            try:
                print(f"\n🔧 Procesando producto con problema de rastreo: {product.name}")

                # PASO 1: Buscar el producto original
                original_product_id = None
                if product.barcode:
                    original_product_id = self.search_product_by_barcode(product.barcode)
                if not original_product_id:
                    original_product_id = self.search_product_by_name(product.name)

                if not original_product_id:
                    results.append(SyncResult(
                        success=False,
                        message=f"No se encontró el producto original: {product.name}",
                        action="tracking_fix_failed"
                    ))
                    continue

                # Obtener detalles del producto original
                original_details = self.get_product_details(original_product_id)
                if not original_details:
                    results.append(SyncResult(
                        success=False,
                        message=f"No se pudieron obtener detalles del producto: {product.name}",
                        action="tracking_fix_failed"
                    ))
                    continue

                print(f"📦 Producto original encontrado: ID {original_product_id}")
                print(f"📊 Stock actual: {original_details.get('qty_available', 0)}")

                # PASO 2: Crear código de barras único temporal para evitar conflictos
                temp_barcode = None
                if product.barcode:
                    temp_barcode = f"TEMP_{product.barcode}_{original_product_id}"

                # PASO 3: Archivar el producto original (cambiar código de barras temporalmente)
                try:
                    archive_data = {'active': False}
                    if temp_barcode:
                        archive_data['barcode'] = temp_barcode

                    self.models.execute_kw(
                        self.db, self.uid, self.password,
                        'product.product', 'write',
                        [[original_product_id], archive_data]
                    )
                    print(f"📁 Producto original archivado con código temporal: {temp_barcode}")

                except Exception as e:
                    print(f"❌ Error archivando producto original: {e}")
                    results.append(SyncResult(
                        success=False,
                        message=f"Error archivando producto original {product.name}: {str(e)}",
                        action="tracking_fix_failed"
                    ))
                    continue

                # PASO 4: Crear el producto nuevo con rastreo activado
                try:
                    # Preparar datos del nuevo producto con rastreo
                    new_product_data = {
                        'name': product.name,
                        'standard_price': self._format_decimal_for_odoo(product.standard_price),
                        'list_price': self._format_decimal_for_odoo(product.list_price),
                        'tracking': 'none',  # Activar rastreo básico
                        'available_in_pos': True
                    }

                    # Agregar el campo de tipo según la versión de Odoo
                    new_product_data.update(self._get_product_type_field())

                    # Agregar código de barras original
                    if product.barcode:
                        new_product_data['barcode'] = product.barcode

                    print(f"🆕 Creando nuevo producto con datos: {new_product_data}")

                    # Crear el nuevo producto
                    new_product_id = self.models.execute_kw(
                        self.db, self.uid, self.password,
                        'product.product', 'create',
                        [new_product_data]
                    )

                    print(f"✅ Nuevo producto creado con ID: {new_product_id}")

                except Exception as e:
                    # Si falla la creación, restaurar el producto original
                    print(f"❌ Error creando nuevo producto: {e}")
                    try:
                        restore_data = {'active': True}
                        if product.barcode:
                            restore_data['barcode'] = product.barcode
                        self.models.execute_kw(
                            self.db, self.uid, self.password,
                            'product.product', 'write',
                            [[original_product_id], restore_data]
                        )
                        print(f"🔄 Producto original restaurado")
                    except:
                        print(f"⚠️ No se pudo restaurar el producto original")

                    results.append(SyncResult(
                        success=False,
                        message=f"Error creando nuevo producto para {product.name}: {str(e)}",
                        action="tracking_fix_failed"
                    ))
                    continue

                # PASO 5: Asignar stock al nuevo producto
                try:
                    if hasattr(product, 'qty_available') and product.qty_available > 0:
                        self.update_stock_quantity(new_product_id, product.qty_available, 'replace', product.name)
                        print(f"📦 Stock asignado al nuevo producto: {product.qty_available} unidades")

                except Exception as e:
                    print(f"⚠️ Advertencia: No se pudo asignar stock al nuevo producto: {e}")
                    # No marcamos como error porque el producto se creó exitosamente

                # PASO 6: Resultado exitoso
                results.append(SyncResult(
                    success=True,
                    message=f"Producto recreado exitosamente: {product.name}. Original archivado (ID: {original_product_id}), nuevo creado (ID: {new_product_id})",
                    product_id=new_product_id,
                    action="tracking_fix_success"
                ))

                print(f"🎉 Proceso completado para: {product.name}")
                print(f"   - Original archivado: ID {original_product_id}")
                print(f"   - Nuevo con rastreo: ID {new_product_id}")

            except Exception as e:
                print(f"❌ Error general procesando {product.name}: {e}")
                results.append(SyncResult(
                    success=False,
                    message=f"Error general procesando {product.name}: {str(e)}",
                    action="tracking_fix_failed"
                ))

        print(f"\n📊 Resumen del proceso de corrección de rastreo:")
        successful = [r for r in results if r.success]
        failed = [r for r in results if not r.success]
        print(f"   ✅ Productos corregidos exitosamente: {len(successful)}")
        print(f"   ❌ Productos que fallaron: {len(failed)}")

        return results

    def _archive_and_recreate_product(self, product_id: int, product: ProductMapped) -> SyncResult:
        """Archive existing product and create new one with inventory tracking enabled"""
        try:
            print(f"🔄 Starting archive and recreate process for product ID: {product_id}")

            # Get original product details
            original_details = self.get_product_details(product_id)
            if not original_details:
                raise Exception(f"Could not get details for product ID: {product_id}")

            # Check current prices for protection
            current_list_price = float(original_details.get('list_price', 0))
            new_list_price = self._format_decimal_for_odoo(product.list_price)

            # Determine which price to use (protection logic)
            protected_list_price = max(current_list_price, new_list_price)
            if protected_list_price > new_list_price:
                print(f"🛡️ Protecting higher sale price in recreated product: ${protected_list_price} (XML suggests ${new_list_price})")
            else:
                print(f"💰 Using new sale price in recreated product: ${new_list_price}")

            # No need for temporary barcodes - we'll handle transfer manually

            # STEP 1: Archive the original product (set active=False but keep original barcode)
            try:
                # First, archive without changing barcode
                self.models.execute_kw(
                    self.db, self.uid, self.password,
                    'product.template', 'write',
                    [[product_id], {'active': False}]
                )
                print(f"📁 Original product archived (active=False) - keeping original barcode temporarily")
            except Exception as e:
                raise Exception(f"Failed to archive original product: {str(e)}")

            # STEP 2: Create new product with tracking enabled (WITHOUT barcode first)
            try:
                new_product_data = {
                    'name': product.name,
                    'standard_price': self._format_decimal_for_odoo(product.standard_price),
                    'list_price': protected_list_price,  # Use protected price
                    'tracking': 'none',
                    'available_in_pos': True
                }

                # Add version-specific product type field (including is_storable)
                new_product_data.update(self._get_product_type_field())

                # DON'T add barcode yet - create without it first
                print(f"🆕 Creating new product WITHOUT barcode first: {new_product_data}")

                # Create the new product
                new_product_id = self.models.execute_kw(
                    self.db, self.uid, self.password,
                    'product.product', 'create',
                    [new_product_data]
                )
                print(f"✅ New product created with ID: {new_product_id} (without barcode)")

                # STEP 3: Now remove barcode from archived product and assign to new product
                if product.barcode:
                    try:
                        # Remove barcode from archived product
                        self.models.execute_kw(
                            self.db, self.uid, self.password,
                            'product.template', 'write',
                            [[product_id], {'barcode': False}]
                        )
                        print(f"📄 Barcode removed from archived product")

                        # Assign barcode to new product
                        self.models.execute_kw(
                            self.db, self.uid, self.password,
                            'product.template', 'write',
                            [[new_product_id], {'barcode': product.barcode}]
                        )
                        print(f"✅ Barcode {product.barcode} assigned to new product")

                    except Exception as barcode_error:
                        print(f"⚠️ Error transferring barcode: {barcode_error}")
                        raise Exception(f"Failed to transfer barcode: {str(barcode_error)}")

            except Exception as e:
                # If creation fails, restore the original product
                print(f"❌ Error creating new product: {e}")
                try:
                    # Restore the original product
                    self.models.execute_kw(
                        self.db, self.uid, self.password,
                        'product.template', 'write',
                        [[product_id], {'active': True}]
                    )
                    print(f"🔄 Original product restored")
                except:
                    print(f"⚠️ Could not restore original product")
                raise Exception(f"Failed to create new product: {str(e)}")

                # STEP 4: Assign stock to new product
                try:
                    if hasattr(product, 'qty_available') and product.qty_available > 0:
                        mode = getattr(product, 'quantity_mode', 'replace')
                        self.update_stock_quantity(new_product_id, product.qty_available, mode, product.name)
                        print(f"📦 Stock assigned to new product: {product.qty_available} units")
                except Exception as e:
                    print(f"⚠️ Warning: Could not assign stock to new product: {e}")
                    # Don't mark as error because product was created successfully

            return SyncResult(
                success=True,
                message=f"Product '{product.name}' recreated successfully with tracking enabled. Original archived (ID: {product_id}), new created (ID: {new_product_id})",
                product_id=new_product_id,
                action="recreated"
            )

        except Exception as e:
            print(f"❌ Error in archive and recreate process: {e}")
            return SyncResult(
                success=False,
                message=f"Failed to recreate product '{product.name}': {str(e)}",
                product_id=product_id,
                action="recreate_failed"
            )

    def _get_product_stock_by_barcode(self, barcode: str) -> float:
        """Get current stock quantity for a product by barcode"""
        try:
            products = self.models.execute_kw(
                self.db, self.uid, self.password,
                'product.product', 'search_read',
                [[["barcode", "=", barcode]]],
                {'fields': ['id', 'qty_available', 'name']}
            )

            if products:
                return float(products[0]['qty_available'])
            else:
                return 0.0

        except Exception as e:
            print(f"⚠️ Warning: Could not get stock for barcode {barcode}: {e}")
            return 0.0

    def _generate_stock_report_pdf(self, stock_data: dict, sync_results: list) -> str:
        """Generate PDF report with before/after stock comparison"""
        try:
            from reportlab.lib.pagesizes import letter, A4
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib import colors
            from reportlab.lib.units import inch
            from datetime import datetime
            import os

            # Create reports directory if it doesn't exist
            reports_dir = os.path.join(os.path.dirname(__file__), 'reports')
            os.makedirs(reports_dir, exist_ok=True)

            # Generate filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"stock_report_{timestamp}.pdf"
            filepath = os.path.join(reports_dir, filename)

            # Create PDF document
            doc = SimpleDocTemplate(
                filepath,
                pagesize=A4
            )
            elements = []
            styles = getSampleStyleSheet()

            # Safe text truncation function for UTF-8
            def safe_truncate(text, max_length):
                """Safely truncate text without breaking UTF-8 characters"""
                if not text:
                    return ""
                text = str(text)
                if len(text) <= max_length:
                    return text

                # Ensure we don't break in the middle of a UTF-8 character
                truncated = text[:max_length]
                try:
                    truncated.encode('utf-8')
                    return truncated + "..."
                except UnicodeEncodeError:
                    # If encoding fails, back off one character at a time
                    for i in range(max_length - 1, 0, -1):
                        try:
                            truncated = text[:i]
                            truncated.encode('utf-8')
                            return truncated + "..."
                        except UnicodeEncodeError:
                            continue
                    return "..."

            # Title with proper UTF-8 handling
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Heading1'],
                fontSize=16,
                spaceAfter=30,
                alignment=1  # Center alignment
            )
            # Use direct UTF-8 characters
            title_text = "Reporte de Sincronización de Stock"
            title = Paragraph(title_text, title_style)
            elements.append(title)

            # Subtitle with date
            subtitle = Paragraph(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal'])
            elements.append(subtitle)
            elements.append(Spacer(1, 20))

            # Summary
            total_products = len(stock_data)
            successful_syncs = len([r for r in sync_results if r.success])
            failed_syncs = total_products - successful_syncs

            summary_data = [
                ["Resumen de Sincronización", ""],
                ["Total de productos:", str(total_products)],
                ["Sincronizados exitosamente:", str(successful_syncs)],
                ["Errores:", str(failed_syncs)]
            ]

            summary_table = Table(summary_data, colWidths=[3*inch, 2*inch])
            summary_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 12),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))

            elements.append(summary_table)
            elements.append(Spacer(1, 30))

            # Stock details table
            if stock_data:
                details_title = Paragraph("Detalles de Stock por Producto", styles['Heading2'])
                elements.append(details_title)
                elements.append(Spacer(1, 10))

                # Table headers with direct UTF-8 characters
                table_data = [
                    ["Código", "Producto", "Stock Antes", "Cantidad Agregada", "Stock Después", "Diferencia"]
                ]

                # Add product data
                for barcode, data in stock_data.items():
                    stock_before = data.get('stock_before', 0)
                    stock_after = data.get('stock_after', 0)
                    quantity_added = data.get('quantity_to_add', 0)
                    difference = stock_after - stock_before

                    table_data.append([
                        str(barcode),
                        safe_truncate(data['name'], 30),
                        f"{stock_before:.1f}",
                        f"{quantity_added:.1f}",
                        f"{stock_after:.1f}",
                        f"{difference:+.1f}"
                    ])

                # Create table
                details_table = Table(table_data, colWidths=[1.2*inch, 2.5*inch, 0.8*inch, 1*inch, 0.8*inch, 0.8*inch])
                details_table.setStyle(TableStyle([
                    # Header style
                    ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 10),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),

                    # Data rows
                    ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                    ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 1), (-1, -1), 8),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black),

                    # Alternate row colors
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey])
                ]))

                elements.append(details_table)

            # Error details if any
            error_results = [r for r in sync_results if not r.success]
            if error_results:
                elements.append(Spacer(1, 30))
                error_title = Paragraph("Productos con Errores", styles['Heading2'])
                elements.append(error_title)
                elements.append(Spacer(1, 10))

                error_data = [["Código", "Producto", "Error"]]
                for result in error_results:
                    error_data.append([
                        str(result.barcode or "N/A"),
                        safe_truncate(result.product_name or "N/A", 40),
                        safe_truncate(result.message, 60)
                    ])

                error_table = Table(error_data, colWidths=[1.2*inch, 2.5*inch, 3*inch])
                error_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.red),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 10),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.mistyrose),
                    ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 1), (-1, -1), 8),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black)
                ]))

                elements.append(error_table)

            # Build PDF
            doc.build(elements)

            return filepath

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"⚠️ Warning: Could not generate PDF report: {e}")
            print(f"🔍 Full error: {error_details}")

            # Try to create a simple fallback PDF
            try:
                from reportlab.platypus import SimpleDocTemplate, Paragraph
                from reportlab.lib.styles import getSampleStyleSheet
                from datetime import datetime
                import os

                reports_dir = os.path.join(os.path.dirname(__file__), 'reports')
                os.makedirs(reports_dir, exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                fallback_path = os.path.join(reports_dir, f"error_report_{timestamp}.pdf")

                doc = SimpleDocTemplate(fallback_path, pagesize=A4)
                styles = getSampleStyleSheet()
                elements = [
                    Paragraph("Error en Reporte de Stock", styles['Title']),
                    Paragraph(f"Error: {str(e)}", styles['Normal']),
                    Paragraph(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal'])
                ]
                doc.build(elements)
                print(f"📋 Fallback PDF created: {fallback_path}")
                return fallback_path
            except:
                print("❌ Could not create fallback PDF either")
                return f"Error generating PDF: {str(e)}"