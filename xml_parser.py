import xmltodict
from typing import List, Dict, Any, Optional
from models import ProductData, ProductMapped, XMLParseResponse
import re
import time
import hashlib
import html


class XMLInvoiceParser:
    """Parser for extracting product data from XML invoices with provider-specific templates"""
    
    def __init__(self):
        self.supported_providers = [
            "D'Mujeres",  # D'Mujeres provider with Ecuadorian format
            "LANSEY",  # LANSEY provider with same format as D'Mujeres but uses codigoPrincipal as barcode
            'Proveedor Genérico'  # Generic provider fallback
        ]
        self.generated_barcodes = set()  # Keep track of generated barcodes to avoid duplicates
    
    def _generate_unique_barcode(self, base_text: str = "") -> str:
        """Generate a unique barcode using timestamp and hash"""
        timestamp = str(int(time.time() * 1000))  # Milliseconds for more uniqueness
        
        # Create a base string for hashing
        hash_input = f"{base_text}_{timestamp}"
        hash_object = hashlib.md5(hash_input.encode())
        hash_hex = hash_object.hexdigest()[:8]  # Take first 8 characters
        
        # Create barcode: timestamp + hash
        generated_barcode = f"{timestamp[-6:]}{hash_hex}"  # Last 6 digits of timestamp + 8 chars hash = 14 chars
        
        # Ensure uniqueness within this session
        while generated_barcode in self.generated_barcodes:
            # If collision, add a small increment
            timestamp = str(int(time.time() * 1000) + len(self.generated_barcodes))
            hash_input = f"{base_text}_{timestamp}"
            hash_object = hashlib.md5(hash_input.encode())
            hash_hex = hash_object.hexdigest()[:8]
            generated_barcode = f"{timestamp[-6:]}{hash_hex}"
        
        self.generated_barcodes.add(generated_barcode)
        return generated_barcode

    def _clean_html_entities(self, text: str) -> str:
        """
        Limpia entidades HTML múltiples y caracteres especiales latinoamericanos
        Convierte: CIG&amp;AMP;AMP;AMP;AMP;AMP;UUML;E&amp;AMP;AMP;AMP;AMP;AMP;NTILDE;A -> CIGÜEÑA
        """
        if not text:
            return text

        # Decodificar múltiples veces para manejar codificación anidada
        cleaned_text = text
        max_iterations = 10  # Evitar bucles infinitos

        for _ in range(max_iterations):
            # Decodificar entidades HTML
            previous_text = cleaned_text
            try:
                cleaned_text = html.unescape(cleaned_text)
            except:
                break

            # Si no hay cambios, ya terminamos
            if cleaned_text == previous_text:
                break

            # También manejar codificación manual común
            cleaned_text = cleaned_text.replace('&amp;', '&')

        # Limpiar caracteres extraños que podrían quedar
        cleaned_text = re.sub(r'&[a-zA-Z0-9#]+;', '', cleaned_text)

        # Normalizar espacios
        cleaned_text = ' '.join(cleaned_text.split())

        return cleaned_text.strip()

    def _round_sale_price(self, price: float) -> float:
        """
        Redondea el precio de venta de manera inteligente:
        - 4.57 -> 4.60 (redondea a decimo superior)
        - 4.92 -> 4.95 (redondea a 5 centavos)
        - 4.43 -> 4.45 (redondea a 5 centavos)
        - Precios enteros: 43 -> 45, 47 -> 50
        """
        if price <= 0:
            return price

        # Si es un precio entero o muy cercano (menos de 0.01 de diferencia)
        if abs(price - round(price)) < 0.01:
            whole_price = round(price)
            last_digit = whole_price % 10

            # Redondear enteros a terminaciones en 0 o 5
            if last_digit in [1, 2, 3, 4]:
                return float(whole_price + (5 - last_digit))  # -> termina en 5
            elif last_digit in [6, 7, 8, 9]:
                return float(whole_price + (10 - last_digit))  # -> termina en 0
            else:
                return float(whole_price)  # Ya termina en 0 o 5

        # Para precios con decimales
        whole_part = int(price)
        decimal_part = price - whole_part

        # Obtener los centavos (segunda cifra decimal)
        cents = int((decimal_part * 100) % 10)
        decimos = int((decimal_part * 10) % 10)

        # Lógica de redondeo para decimales:
        if cents <= 2:
            # .x1, .x2 -> .x5
            new_decimal = decimos / 10 + 0.05
        elif cents == 3 or cents == 4:
            # .x3, .x4 -> .x5
            new_decimal = decimos / 10 + 0.05
        elif cents == 5:
            # .x5 -> mantener .x5
            new_decimal = decimos / 10 + 0.05
        elif cents == 6 or cents == 7:
            # .x6, .x7 -> .(x+1)0
            new_decimal = (decimos + 1) / 10
        else:
            # .x8, .x9 -> .(x+1)0
            new_decimal = (decimos + 1) / 10

        # Manejar overflow de decimales
        if new_decimal >= 1.0:
            whole_part += 1
            new_decimal = 0.0

        result = whole_part + new_decimal
        return round(result, 2)

    def parse_xml_file(self, xml_content: str, provider: str = "D'Mujeres") -> XMLParseResponse:
        """Parse XML content and extract product information based on provider"""
        try:
            # Convert XML to dictionary
            xml_dict = xmltodict.parse(xml_content)
            
            # Route to appropriate parser based on provider
            products = []
            
            if provider == "D'Mujeres":
                products = self._parse_dmujeres_format(xml_dict)
            elif provider == "LANSEY":
                products = self._parse_lansey_format(xml_dict)
            elif provider == "Proveedor Genérico":
                products = self._parse_generic_format(xml_dict)
            else:
                # Fallback to D'Mujeres format for unknown providers
                products = self._parse_dmujeres_format(xml_dict)
            
            return XMLParseResponse(
                products=products,
                total_found=len(products)
            )
            
        except Exception as e:
            raise Exception(f"Error parsing XML with {provider} provider: {str(e)}")
    
    def _parse_dmujeres_format(self, xml_dict: Dict[str, Any]) -> List[ProductData]:
        """Parse D'Mujeres Ecuadorian electronic invoice format"""
        products = []
        
        try:
            # Handle CDATA content in autorizacion->comprobante
            comprobante_content = None
            
            if 'autorizacion' in xml_dict:
                comprobante_cdata = xml_dict['autorizacion'].get('comprobante', '')
                if comprobante_cdata:
                    # Parse the inner XML from CDATA
                    inner_xml_dict = xmltodict.parse(comprobante_cdata)
                    comprobante_content = inner_xml_dict.get('factura')
            else:
                # Try direct factura access
                comprobante_content = xml_dict.get('factura')
            
            if not comprobante_content:
                return products
            
            # Navigate to detalles section
            detalles = comprobante_content.get('detalles', {})
            if not detalles:
                return products
            
            detalle_list = detalles.get('detalle', [])
            if not detalle_list:
                return products
            
            # Handle both single item and list of items
            if not isinstance(detalle_list, list):
                detalle_list = [detalle_list]
            
            for detalle in detalle_list:
                product = self._extract_dmujeres_product(detalle)
                if product:
                    products.append(product)
        
        except Exception as e:
            print(f"Error parsing D'Mujeres format: {e}")
        
        return products
    
    def _extract_dmujeres_product(self, detalle: Dict[str, Any]) -> Optional[ProductData]:
        """Extract product data from D'Mujeres detalle"""
        try:
            # Extract required fields
            descripcion_raw = detalle.get('descripcion', '').strip()
            
            # Clean HTML entities and description: remove extra whitespace, newlines, and limit length
            descripcion = self._clean_html_entities(descripcion_raw)
            descripcion = ' '.join(descripcion.split())  # Remove extra whitespace and newlines
            descripcion = descripcion[:100]  # Limit to 100 characters
            
            cantidad = float(detalle.get('cantidad', 0))
            precio_unitario = float(detalle.get('precioUnitario', 0))
            precio_total = float(detalle.get('precioTotalSinImpuesto', 0))  # Precio total sin impuestos
            
            # Extract optional fields
            codigo_principal = detalle.get('codigoPrincipal', '').strip()
            codigo_auxiliar = detalle.get('codigoAuxiliar', '').strip()
            
            # Use codigoAuxiliar as barcode (preferred for barcode scanning)
            codigo_final = codigo_auxiliar if codigo_auxiliar else (codigo_principal if codigo_principal else None)
            
            # If no barcode available, generate one using product description
            if not codigo_final:
                codigo_final = self._generate_unique_barcode(descripcion)
            
            if descripcion and cantidad > 0 and precio_unitario > 0:
                # Calcular precio costo real basado en precio total / cantidad
                # Esto refleja mejor el costo real cuando hay descuentos
                precio_costo_real = precio_total / cantidad if cantidad > 0 else precio_unitario

                return ProductData(
                    descripcion=descripcion,
                    cantidad=cantidad,
                    codigo_auxiliar=codigo_final,
                    precio_unitario=precio_costo_real  # Usar el precio costo calculado
                )
        except Exception as e:
            print(f"Error extracting D'Mujeres product: {e}")
        
        return None

    def _parse_lansey_format(self, xml_dict: Dict[str, Any]) -> List[ProductData]:
        """Parse LANSEY format (same as D'Mujeres Ecuadorian electronic invoice format)"""
        products = []

        try:
            # Handle CDATA content in autorizacion->comprobante
            comprobante_content = None

            if 'autorizacion' in xml_dict:
                comprobante_cdata = xml_dict['autorizacion'].get('comprobante', '')
                if comprobante_cdata:
                    # Parse the inner XML from CDATA
                    inner_xml_dict = xmltodict.parse(comprobante_cdata)
                    comprobante_content = inner_xml_dict.get('factura')
            else:
                # Try direct factura access
                comprobante_content = xml_dict.get('factura')

            if not comprobante_content:
                return products

            # Navigate to detalles section
            detalles = comprobante_content.get('detalles', {})
            if not detalles:
                return products

            detalle_list = detalles.get('detalle', [])
            if not detalle_list:
                return products

            # Handle both single item and list of items
            if not isinstance(detalle_list, list):
                detalle_list = [detalle_list]

            for detalle in detalle_list:
                product = self._extract_lansey_product(detalle)
                if product:
                    products.append(product)

        except Exception as e:
            print(f"Error parsing LANSEY format: {e}")

        return products

    def _extract_lansey_product(self, detalle: Dict[str, Any]) -> Optional[ProductData]:
        """Extract product data from LANSEY detalle - uses codigoPrincipal as barcode"""
        try:
            # Extract required fields
            descripcion_raw = detalle.get('descripcion', '').strip()

            # Clean HTML entities and description: remove extra whitespace, newlines, and limit length
            descripcion = self._clean_html_entities(descripcion_raw)
            descripcion = ' '.join(descripcion.split())  # Remove extra whitespace and newlines
            descripcion = descripcion[:100]  # Limit to 100 characters

            cantidad = float(detalle.get('cantidad', 0))
            precio_unitario = float(detalle.get('precioUnitario', 0))
            precio_total = float(detalle.get('precioTotalSinImpuesto', 0))  # Precio total sin impuestos

            # Extract optional fields
            codigo_principal = detalle.get('codigoPrincipal', '').strip()
            codigo_auxiliar = detalle.get('codigoAuxiliar', '').strip()

            # LANSEY uses codigoPrincipal as barcode (MANDATORY)
            # Only fall back to codigoAuxiliar if codigoPrincipal is not available
            codigo_final = codigo_principal if codigo_principal else (codigo_auxiliar if codigo_auxiliar else None)

            # If no barcode available, generate one using product description
            if not codigo_final:
                codigo_final = self._generate_unique_barcode(descripcion)

            if descripcion and cantidad > 0 and precio_unitario > 0:
                # Calcular precio costo real basado en precio total / cantidad
                # Esto refleja mejor el costo real cuando hay descuentos
                precio_costo_real = precio_total / cantidad if cantidad > 0 else precio_unitario

                return ProductData(
                    descripcion=descripcion,
                    cantidad=cantidad,
                    codigo_auxiliar=codigo_final,
                    precio_unitario=precio_costo_real  # Usar el precio costo calculado
                )
        except Exception as e:
            print(f"Error extracting LANSEY product: {e}")

        return None


    def _parse_generic_format(self, xml_dict: Dict[str, Any]) -> List[ProductData]:
        """Parse generic XML format by searching for common patterns"""
        products = []
        
        try:
            # Recursively search for product-like elements
            products_found = self._search_products_recursive(xml_dict)
            
            for product_data in products_found:
                product = self._extract_generic_product(product_data)
                if product:
                    products.append(product)
        
        except Exception as e:
            print(f"Error parsing generic format: {e}")
        
        return products
    
    def _search_products_recursive(self, data: Any, products: List = None) -> List[Dict]:
        """Recursively search for product elements in XML structure"""
        if products is None:
            products = []
        
        if isinstance(data, dict):
            # Check if current dict looks like a product
            if self._looks_like_product(data):
                products.append(data)
            
            # Recurse into child elements
            for key, value in data.items():
                if key.lower() in ['products', 'items', 'lines', 'conceptos', 'productos']:
                    self._search_products_recursive(value, products)
                elif isinstance(value, (dict, list)):
                    self._search_products_recursive(value, products)
        
        elif isinstance(data, list):
            for item in data:
                self._search_products_recursive(item, products)
        
        return products
    
    def _looks_like_product(self, data: Dict) -> bool:
        """Check if a dictionary looks like product data"""
        product_indicators = [
            'descripcion', 'description', 'name', 'nombre',
            'cantidad', 'quantity', 'qty',
            'precio', 'price', 'valor', 'amount'
        ]
        
        keys_lower = [k.lower() for k in data.keys()]
        matches = sum(1 for indicator in product_indicators if any(indicator in key for key in keys_lower))
        
        return matches >= 2
    
    def _extract_generic_product(self, data: Dict) -> Optional[ProductData]:
        """Extract product data from generic XML structure"""
        try:
            # Find description field
            descripcion_raw = ''
            for key, value in data.items():
                if any(term in key.lower() for term in ['descripcion', 'description', 'name', 'nombre']):
                    descripcion_raw = str(value).strip()
                    break
            
            # Clean HTML entities and description: remove extra whitespace, newlines, and limit length
            descripcion = self._clean_html_entities(descripcion_raw)
            descripcion = ' '.join(descripcion.split())  # Remove extra whitespace and newlines
            descripcion = descripcion[:100]  # Limit to 100 characters
            
            # Find quantity field
            cantidad = 0.0
            for key, value in data.items():
                if any(term in key.lower() for term in ['cantidad', 'quantity', 'qty']):
                    try:
                        cantidad = float(value)
                        break
                    except (ValueError, TypeError):
                        continue
            
            # Find price field (unitario)
            precio_unitario = 0.0
            for key, value in data.items():
                if any(term in key.lower() for term in ['preciounitario', 'precio_unitario', 'unit_price']):
                    try:
                        precio_unitario = float(value)
                        break
                    except (ValueError, TypeError):
                        continue

            # Find total price field
            precio_total = 0.0
            for key, value in data.items():
                if any(term in key.lower() for term in ['preciototal', 'precio_total', 'total_price', 'total']):
                    try:
                        precio_total = float(value)
                        break
                    except (ValueError, TypeError):
                        continue
            
            # Find auxiliary code field
            codigo_auxiliar = None
            for key, value in data.items():
                if any(term in key.lower() for term in ['codigo', 'code', 'id', 'sku', 'clave']):
                    codigo_auxiliar = str(value).strip()
                    break
            
            # If no barcode available, generate one using product description
            if not codigo_auxiliar:
                codigo_auxiliar = self._generate_unique_barcode(descripcion)
            
            if descripcion and cantidad > 0 and precio_unitario > 0:
                # Calcular precio costo real basado en precio total / cantidad
                # Si no hay precio total, usar el precio unitario
                precio_costo_real = (precio_total / cantidad) if precio_total > 0 and cantidad > 0 else precio_unitario

                return ProductData(
                    descripcion=descripcion,
                    cantidad=cantidad,
                    codigo_auxiliar=codigo_auxiliar,
                    precio_unitario=precio_costo_real  # Usar el precio costo calculado
                )
        except Exception as e:
            print(f"Error extracting generic product: {e}")
        
        return None
    
    def map_to_odoo_format(self, products: List[ProductData], profit_margin: float = 50.0, iva_rate: float = 15.0) -> List[ProductMapped]:
        """Map ProductData to ProductMapped for Odoo with profit margin calculation"""
        mapped_products = []

        for product in products:
            # Calculate sale price with profit margin
            sale_price_with_iva = product.precio_unitario * (1 + profit_margin / 100)

            # Apply smart rounding to sale price with IVA
            sale_price_with_iva_rounded = self._round_sale_price(sale_price_with_iva)

            # Calculate price without IVA for Odoo (Odoo adds IVA automatically)
            sale_price_without_iva = sale_price_with_iva_rounded / (1 + iva_rate / 100)

            mapped = ProductMapped(
                name=product.descripcion,
                qty_available=product.cantidad,
                barcode=product.codigo_auxiliar,
                standard_price=product.precio_unitario,  # Cost price
                list_price=round(sale_price_without_iva, 8),  # Sale price without IVA for Odoo
                type='product',
                tracking='none',  # Track by quantity only (no lots/serial numbers)
                available_in_pos=True,
                quantity_mode='add'  # XML invoices always ADD quantity (incoming merchandise)
            )

            # Add display price with IVA for frontend (already rounded)
            mapped.display_price = sale_price_with_iva_rounded
            
            mapped_products.append(mapped)
        
        return mapped_products
    
    def parse_transfer_xml(self, xml_content: str) -> List[Dict]:
        """Parse transfer XML generated in step 1 and extract product information"""
        try:
            # Convert XML to dictionary
            xml_dict = xmltodict.parse(xml_content)
            
            products = []
            
            # Navigate through the XML structure for transfer format
            # The structure is: autorizacion -> comprobante -> factura -> detalles -> detalle
            comprobante_cdata = xml_dict.get('autorizacion', {}).get('comprobante', '')
            
            if comprobante_cdata:
                # Parse the CDATA content which contains the actual invoice XML
                inner_xml_dict = xmltodict.parse(comprobante_cdata)
                
                # Extract details from the inner XML
                factura = inner_xml_dict.get('factura', {})
                detalles = factura.get('detalles', {})
                
                # Handle both single detail and multiple details
                detalle_items = detalles.get('detalle', [])
                if not isinstance(detalle_items, list):
                    detalle_items = [detalle_items]
                
                for detalle in detalle_items:
                    if detalle:  # Make sure detalle is not empty
                        product = {
                            'descripcion': detalle.get('descripcion', ''),
                            'codigo_auxiliar': detalle.get('codigoAuxiliar', ''),
                            'cantidad': float(detalle.get('cantidad', 0)),
                            'precio_unitario': float(detalle.get('precioUnitario', 0))
                        }

                        # Only add products with valid data
                        if product['descripcion'] and product['codigo_auxiliar']:
                            products.append(product)
            
            return products
            
        except Exception as e:
            print(f"Error parsing transfer XML: {e}")
            raise Exception(f"Error parsing transfer XML: {str(e)}")