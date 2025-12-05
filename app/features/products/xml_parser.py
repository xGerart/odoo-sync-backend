"""
XML invoice parser for extracting product data from supplier invoices.
Supports multiple providers: D'Mujeres, LANSEY, Generic.
"""
import xmltodict
import html
import re
import time
import hashlib
from typing import List, Dict, Any, Optional, Set
from app.schemas.product import ProductData, XMLParseResponse
from app.core.constants import XMLProvider
from app.core.exceptions import ValidationError
from app.utils.formatters import round_price_ecuador


class XMLInvoiceParser:
    """Parser for extracting product data from XML invoices with provider-specific templates."""

    def __init__(self):
        self.generated_barcodes: Set[str] = set()

    def parse_xml_file(self, xml_content: str, provider: XMLProvider) -> XMLParseResponse:
        """
        Parse XML content and extract product information based on provider.

        Args:
            xml_content: XML file content as string
            provider: XML provider type

        Returns:
            XMLParseResponse with extracted products

        Raises:
            ValidationError: If XML parsing fails
        """
        try:
            # Pre-process: Remove wrapper if present (from factura update system)
            xml_content = self._remove_factura_wrapper(xml_content)

            # Convert XML to dictionary
            xml_dict = xmltodict.parse(xml_content)

            # Route to appropriate parser based on provider
            if provider == XMLProvider.DMUJERES:
                products = self._parse_dmujeres_format(xml_dict)
            elif provider == XMLProvider.LANSEY:
                products = self._parse_lansey_format(xml_dict)
            else:  # GENERIC
                products = self._parse_generic_format(xml_dict)

            return XMLParseResponse(
                products=products,
                total_found=len(products),
                provider=provider
            )

        except Exception as e:
            raise ValidationError(
                f"Error parsing XML with {provider.value} provider: {str(e)}"
            )

    def _parse_dmujeres_format(self, xml_dict: Dict[str, Any]) -> List[ProductData]:
        """Parse D'Mujeres Ecuadorian electronic invoice format."""
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
            raise ValidationError(f"Error parsing D'Mujeres format: {str(e)}")

        return products

    def _extract_dmujeres_product(self, detalle: Dict[str, Any]) -> Optional[ProductData]:
        """Extract product from D'Mujeres detail item."""
        try:
            # Extract fields
            descripcion = detalle.get('descripcion', '')
            cantidad = float(detalle.get('cantidad', 0))
            precio_unitario = float(detalle.get('precioUnitario', 0))

            # Try codigoAuxiliar first (D'Mujeres), then codigoPrincipal (LANSEY/otros)
            codigo_auxiliar = detalle.get('codigoAuxiliar', '').strip()
            if not codigo_auxiliar:
                codigo_auxiliar = detalle.get('codigoPrincipal', '').strip()

            # Clean HTML entities from description
            descripcion = self._clean_html_entities(descripcion)

            # Generate barcode if missing
            if not codigo_auxiliar:
                codigo_auxiliar = self._generate_unique_barcode(descripcion)

            return ProductData(
                descripcion=descripcion,
                cantidad=cantidad,
                codigo_auxiliar=codigo_auxiliar,
                precio_unitario=precio_unitario
            )

        except Exception:
            return None

    def _parse_lansey_format(self, xml_dict: Dict[str, Any]) -> List[ProductData]:
        """Parse LANSEY format (similar to D'Mujeres but uses codigoPrincipal)."""
        import logging
        logger = logging.getLogger(__name__)

        logger.info("=== LANSEY PARSER DEBUG ===")
        products = []

        try:
            # Same structure as D'Mujeres
            comprobante_content = None

            logger.info(f"XML dict top-level keys: {list(xml_dict.keys())}")

            if 'autorizacion' in xml_dict:
                logger.info("Found 'autorizacion' key")
                comprobante_cdata = xml_dict['autorizacion'].get('comprobante', '')
                logger.info(f"Comprobante CDATA length: {len(comprobante_cdata) if comprobante_cdata else 0}")
                if comprobante_cdata:
                    logger.info(f"First 300 chars of CDATA: {comprobante_cdata[:300]}")
                    inner_xml_dict = xmltodict.parse(comprobante_cdata)
                    logger.info(f"Inner XML keys: {list(inner_xml_dict.keys())}")
                    comprobante_content = inner_xml_dict.get('factura')
            else:
                logger.info("No 'autorizacion' key, trying direct 'factura'")
                comprobante_content = xml_dict.get('factura')

            if not comprobante_content:
                logger.warning("No comprobante_content found")
                return products

            logger.info("Comprobante content found")
            detalles = comprobante_content.get('detalles', {})
            logger.info(f"Detalles type: {type(detalles)}, content: {detalles if detalles else 'empty'}")

            if not detalles:
                logger.warning("No detalles section found")
                return products

            detalle_list = detalles.get('detalle', [])
            logger.info(f"Detalle list type: {type(detalle_list)}, length: {len(detalle_list) if isinstance(detalle_list, list) else 1}")

            if not detalle_list:
                logger.warning("Empty detalle list")
                return products

            if not isinstance(detalle_list, list):
                detalle_list = [detalle_list]

            logger.info(f"Processing {len(detalle_list)} detalles")
            for idx, detalle in enumerate(detalle_list):
                logger.info(f"Detalle {idx} keys: {list(detalle.keys())}")
                logger.info(f"Detalle {idx} codigoPrincipal: {detalle.get('codigoPrincipal', 'NOT FOUND')}")
                product = self._extract_lansey_product(detalle)
                if product:
                    logger.info(f"Product {idx} extracted: barcode={product.codigo_auxiliar}, name={product.descripcion[:30]}")
                    products.append(product)
                else:
                    logger.warning(f"Product {idx} extraction failed")

        except Exception as e:
            logger.error(f"Error parsing LANSEY format: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            raise ValidationError(f"Error parsing LANSEY format: {str(e)}")

        logger.info(f"Total products extracted: {len(products)}")
        return products

    def _extract_lansey_product(self, detalle: Dict[str, Any]) -> Optional[ProductData]:
        """Extract product from LANSEY detail item."""
        import logging
        logger = logging.getLogger(__name__)

        try:
            descripcion = detalle.get('descripcion', '')
            cantidad = float(detalle.get('cantidad', 0))
            precio_unitario = float(detalle.get('precioUnitario', 0))

            logger.info(f"Extracting LANSEY product: desc={descripcion[:50]}, cant={cantidad}, precio={precio_unitario}")

            # Try codigoPrincipal first (LANSEY), then codigoAuxiliar (D'Mujeres/otros)
            codigo_principal = detalle.get('codigoPrincipal', '').strip()
            if not codigo_principal:
                codigo_principal = detalle.get('codigoAuxiliar', '').strip()

            logger.info(f"Codigo found: '{codigo_principal}' (length: {len(codigo_principal)})")

            descripcion = self._clean_html_entities(descripcion)

            if not codigo_principal:
                logger.warning("No codigo found, generating barcode")
                codigo_principal = self._generate_unique_barcode(descripcion)
                logger.info(f"Generated barcode: {codigo_principal}")

            return ProductData(
                descripcion=descripcion,
                cantidad=cantidad,
                codigo_auxiliar=codigo_principal,
                precio_unitario=precio_unitario
            )

        except Exception as e:
            logger.error(f"Error extracting LANSEY product: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    def _parse_generic_format(self, xml_dict: Dict[str, Any]) -> List[ProductData]:
        """Parse generic XML format."""
        products = []

        try:
            # Try to find products in common structures
            items = None

            # Try common paths
            if 'invoice' in xml_dict:
                items = xml_dict['invoice'].get('items', {}).get('item', [])
            elif 'factura' in xml_dict:
                items = xml_dict['factura'].get('detalles', {}).get('detalle', [])
            elif 'items' in xml_dict:
                items = xml_dict['items'].get('item', [])

            if not items:
                return products

            if not isinstance(items, list):
                items = [items]

            for item in items:
                product = self._extract_generic_product(item)
                if product:
                    products.append(product)

        except Exception as e:
            raise ValidationError(f"Error parsing generic format: {str(e)}")

        return products

    def _extract_generic_product(self, item: Dict[str, Any]) -> Optional[ProductData]:
        """Extract product from generic item."""
        try:
            # Try different field names
            descripcion = (
                item.get('descripcion') or
                item.get('description') or
                item.get('name') or
                ''
            )

            cantidad = float(
                item.get('cantidad') or
                item.get('quantity') or
                item.get('qty') or
                0
            )

            precio_unitario = float(
                item.get('precioUnitario') or
                item.get('precio') or
                item.get('price') or
                item.get('unitPrice') or
                0
            )

            codigo = (
                item.get('codigoAuxiliar') or
                item.get('codigoPrincipal') or
                item.get('barcode') or
                item.get('sku') or
                item.get('code') or
                ''
            ).strip()

            descripcion = self._clean_html_entities(descripcion)

            if not codigo:
                codigo = self._generate_unique_barcode(descripcion)

            return ProductData(
                descripcion=descripcion,
                cantidad=cantidad,
                codigo_auxiliar=codigo,
                precio_unitario=precio_unitario
            )

        except Exception:
            return None

    def _remove_factura_wrapper(self, xml_content: str) -> str:
        """
        Remove wrapper tag from updated XML files.

        The factura update system wraps XMLs in:
        <factura index="0" filename="...">
            <?xml version...?>
            <autorizacion>...</autorizacion>
        </factura>

        This wrapper breaks XML parsing. Remove it if present.

        Args:
            xml_content: XML content that may have wrapper

        Returns:
            Cleaned XML content without wrapper
        """
        # Check if content starts with <factura wrapper
        if xml_content.strip().startswith('<factura '):
            # Find the first <?xml or <autorizacion tag
            import re
            # Remove the opening <factura...> tag and everything before the actual XML
            match = re.search(r'<factura[^>]*>\s*(<\?xml|<autorizacion)', xml_content, re.DOTALL)
            if match:
                # Start from the matched position (skip the wrapper)
                start_pos = match.start(1)
                xml_content = xml_content[start_pos:]

                # Remove closing </factura> tag at the end if present
                xml_content = re.sub(r'</factura>\s*$', '', xml_content, flags=re.DOTALL)

        return xml_content.strip()

    def _clean_html_entities(self, text: str) -> str:
        """
        Clean HTML entities and special characters.

        Handles multiple levels of encoding like:
        CIG&amp;AMP;AMP;UUML;E -> CIGÜE

        Args:
            text: Text with HTML entities

        Returns:
            Cleaned text
        """
        if not text:
            return text

        cleaned_text = text
        max_iterations = 10  # Prevent infinite loops

        for _ in range(max_iterations):
            previous_text = cleaned_text

            try:
                cleaned_text = html.unescape(cleaned_text)
            except Exception:
                break

            if cleaned_text == previous_text:
                break

            # Also handle manual encoding
            cleaned_text = cleaned_text.replace('&amp;', '&')

        # Clean remaining odd characters
        cleaned_text = re.sub(r'&[a-zA-Z0-9#]+;', '', cleaned_text)

        # Normalize whitespace
        cleaned_text = ' '.join(cleaned_text.split())

        return cleaned_text.strip()

    def _generate_unique_barcode(self, base_text: str = "") -> str:
        """
        Generate a unique barcode using timestamp and hash.

        Args:
            base_text: Base text for hash generation

        Returns:
            Unique barcode string
        """
        timestamp = str(int(time.time() * 1000))  # Milliseconds

        # Create hash input
        hash_input = f"{base_text}_{timestamp}"
        hash_object = hashlib.md5(hash_input.encode())
        hash_hex = hash_object.hexdigest()[:8]

        # Create barcode: last 6 digits of timestamp + 8 char hash = 14 chars
        generated_barcode = f"{timestamp[-6:]}{hash_hex}"

        # Ensure uniqueness within session
        while generated_barcode in self.generated_barcodes:
            timestamp = str(int(time.time() * 1000) + len(self.generated_barcodes))
            hash_input = f"{base_text}_{timestamp}"
            hash_object = hashlib.md5(hash_input.encode())
            hash_hex = hash_object.hexdigest()[:8]
            generated_barcode = f"{timestamp[-6:]}{hash_hex}"

        self.generated_barcodes.add(generated_barcode)
        return generated_barcode

    def map_to_odoo_format(
        self,
        products: List[ProductData],
        profit_margin: float,
        quantity_mode: str = "replace",
        apply_iva: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Map parsed products to Odoo format with pricing calculations.

        Args:
            products: List of parsed products
            profit_margin: Profit margin to apply (0-1, e.g., 0.50 for 50%)
            quantity_mode: 'replace' or 'add' for quantity updates
            apply_iva: Whether to calculate display price with IVA

        Returns:
            List of products mapped to Odoo format
        """
        from app.utils.formatters import (
            apply_profit_margin,
            calculate_price_with_iva,
            calculate_price_without_iva,
            round_to_half_dollar
        )

        mapped_products = []

        for product in products:
            # Calculate price with margin
            price_with_margin = apply_profit_margin(product.precio_unitario, profit_margin)

            # Round to nearest 50 cents - this is the FINAL sale price (includes IVA conceptually)
            display_price = round_to_half_dollar(price_with_margin)

            # Calculate price WITHOUT IVA to store in Odoo
            # When Odoo sells the product, it will add IVA and get back to display_price
            if apply_iva:
                sale_price = calculate_price_without_iva(display_price)
            else:
                sale_price = display_price
                display_price = None

            mapped = {
                "name": product.descripcion,
                "qty_available": product.cantidad,
                "barcode": product.codigo_auxiliar,
                "standard_price": product.precio_unitario,
                "list_price": sale_price,
                "display_price": display_price,
                "type": "storable",
                "tracking": "none",
                "available_in_pos": True,
                "quantity_mode": quantity_mode
            }

            mapped_products.append(mapped)

        return mapped_products
