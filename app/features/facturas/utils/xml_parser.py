"""
XML parsing utilities for facturas.
"""
import re
import xml.etree.ElementTree as ET
from typing import List, Dict, Any
from html import unescape


def extract_productos_from_xml(xml_content: str, barcode_source: str = 'codigoAuxiliar') -> List[Dict[str, Any]]:
    """
    Extract products from XML factura content.

    Args:
        xml_content: XML string content
        barcode_source: Which field to use as barcode ('codigoPrincipal' or 'codigoAuxiliar')

    Returns:
        List of product dictionaries with 'codigo', 'descripcion', 'cantidad'
    """
    productos = []

    # Check if content has CDATA section
    inner_xml = xml_content
    cdata_start = xml_content.find('<![CDATA[')
    if cdata_start != -1:
        cdata_end = xml_content.find(']]>')
        if cdata_end != -1:
            inner_xml = xml_content[cdata_start + 9:cdata_end]

    # Find all <detalle> sections using regex
    detalle_pattern = re.compile(r'<detalle>(.*?)</detalle>', re.DOTALL)
    detalles = detalle_pattern.findall(inner_xml)

    for detalle_content in detalles:
        # Extract fields from detalle
        codigo_principal_match = re.search(r'<codigoPrincipal>(.*?)</codigoPrincipal>', detalle_content)
        codigo_auxiliar_match = re.search(r'<codigoAuxiliar>(.*?)</codigoAuxiliar>', detalle_content)
        descripcion_match = re.search(r'<descripcion>(.*?)</descripcion>', detalle_content)
        cantidad_match = re.search(r'<cantidad>(.*?)</cantidad>', detalle_content)
        precio_unitario_match = re.search(r'<precioUnitario>(.*?)</precioUnitario>', detalle_content)
        precio_total_match = re.search(r'<precioTotalSinImpuesto>(.*?)</precioTotalSinImpuesto>', detalle_content)

        if descripcion_match and cantidad_match:
            # Extract both codes
            codigo_principal = codigo_principal_match.group(1).strip() if codigo_principal_match else ''
            codigo_auxiliar = codigo_auxiliar_match.group(1).strip() if codigo_auxiliar_match else ''

            # Select code based on preference
            if barcode_source == 'codigoPrincipal':
                codigo = codigo_principal if codigo_principal else codigo_auxiliar
            else:  # Default to codigoAuxiliar
                codigo = codigo_auxiliar if codigo_auxiliar else codigo_principal

            # Skip if no code available
            if not codigo:
                continue

            descripcion = unescape(descripcion_match.group(1))

            # Replace common HTML entities
            descripcion = (descripcion
                          .replace('&ntilde;', 'ñ')
                          .replace('&Ntilde;', 'Ñ'))

            cantidad = float(cantidad_match.group(1))

            # Extract prices
            precio_unitario = None
            precio_total = None

            if precio_total_match:
                precio_total = float(precio_total_match.group(1))

            # Calculate unit price from total (source of truth) when possible
            # This fixes incorrect precioUnitario values in some XML files
            if precio_total is not None and cantidad > 0:
                precio_unitario = precio_total / cantidad
            elif precio_unitario_match:
                # Fallback to XML value only if total is not available
                precio_unitario = float(precio_unitario_match.group(1))

            productos.append({
                'codigo': codigo,
                'descripcion': descripcion,
                'cantidad': cantidad,
                'precio_unitario': precio_unitario,
                'precio_total': precio_total
            })

    return productos


def extract_productos_preview_from_xml(xml_content: str) -> List[Dict[str, Any]]:
    """
    Extract products from XML factura with BOTH barcode fields for preview.

    Unlike extract_productos_from_xml(), this returns both codigo_principal
    and codigo_auxiliar without filtering based on barcode_source preference.
    This allows users to see which field has data before making a selection.

    Args:
        xml_content: XML string content

    Returns:
        List of product dictionaries with both barcode fields:
        {
            'codigo_principal': str,
            'codigo_auxiliar': str,
            'descripcion': str,
            'cantidad': float,
            'precio_unitario': Optional[float],
            'precio_total': Optional[float]
        }
    """
    productos = []

    # Check if content has CDATA section
    inner_xml = xml_content
    cdata_start = xml_content.find('<![CDATA[')
    if cdata_start != -1:
        cdata_end = xml_content.find(']]>')
        if cdata_end != -1:
            inner_xml = xml_content[cdata_start + 9:cdata_end]

    # Find all <detalle> sections using regex
    detalle_pattern = re.compile(r'<detalle>(.*?)</detalle>', re.DOTALL)
    detalles = detalle_pattern.findall(inner_xml)

    for detalle_content in detalles:
        # Extract fields from detalle
        codigo_principal_match = re.search(r'<codigoPrincipal>(.*?)</codigoPrincipal>', detalle_content)
        codigo_auxiliar_match = re.search(r'<codigoAuxiliar>(.*?)</codigoAuxiliar>', detalle_content)
        descripcion_match = re.search(r'<descripcion>(.*?)</descripcion>', detalle_content)
        cantidad_match = re.search(r'<cantidad>(.*?)</cantidad>', detalle_content)
        precio_unitario_match = re.search(r'<precioUnitario>(.*?)</precioUnitario>', detalle_content)
        precio_total_match = re.search(r'<precioTotalSinImpuesto>(.*?)</precioTotalSinImpuesto>', detalle_content)

        if descripcion_match and cantidad_match:
            # Extract BOTH codes (may be empty strings)
            codigo_principal = codigo_principal_match.group(1).strip() if codigo_principal_match else ''
            codigo_auxiliar = codigo_auxiliar_match.group(1).strip() if codigo_auxiliar_match else ''

            descripcion = unescape(descripcion_match.group(1))

            # Replace common HTML entities
            descripcion = (descripcion
                          .replace('&ntilde;', 'ñ')
                          .replace('&Ntilde;', 'Ñ'))

            cantidad = float(cantidad_match.group(1))

            # Extract prices
            precio_unitario = None
            precio_total = None

            if precio_total_match:
                precio_total = float(precio_total_match.group(1))

            # Calculate unit price from total (source of truth) when possible
            # This fixes incorrect precioUnitario values in some XML files
            if precio_total is not None and cantidad > 0:
                precio_unitario = precio_total / cantidad
            elif precio_unitario_match:
                # Fallback to XML value only if total is not available
                precio_unitario = float(precio_unitario_match.group(1))

            productos.append({
                'codigo_principal': codigo_principal,
                'codigo_auxiliar': codigo_auxiliar,
                'descripcion': descripcion,
                'cantidad': cantidad,
                'precio_unitario': precio_unitario,
                'precio_total': precio_total
            })

    return productos


def create_unified_xml(xml_files: List[Dict[str, str]]) -> str:
    """
    Create unified XML from multiple factura XMLs.

    Args:
        xml_files: List of dicts with 'filename' and 'content'

    Returns:
        Unified XML string
    """
    unified = '<?xml version="1.0" encoding="UTF-8"?>\n'
    unified += '<facturasUnificadas>\n'

    for i, xml_data in enumerate(xml_files):
        filename = xml_data['filename']
        content = xml_data['content']

        # Escape XML content for embedding
        escaped_content = (content
                          .replace('&', '&amp;')
                          .replace('<', '&lt;')
                          .replace('>', '&gt;')
                          .replace('"', '&quot;')
                          .replace("'", '&apos;'))

        unified += f'  <factura index="{i}" filename="{filename}">\n'
        unified += f'    {escaped_content}\n'
        unified += '  </factura>\n'

    unified += '</facturasUnificadas>'
    return unified


def update_xml_with_barcodes(unified_xml: str, codigo_map: Dict[str, Dict[str, Any]]) -> List[Dict[str, str]]:
    """
    Update unified XML with barcode and quantity mappings and split into individual XMLs.

    Handles two formats:
    1. Backend-generated unified XML: <facturasUnificadas><factura>...</factura></facturasUnificadas>
    2. SRI authorization XML: <autorizacion><comprobante><![CDATA[...]]></comprobante></autorizacion>

    Args:
        unified_xml: Unified XML content
        codigo_map: Dictionary mapping codigo_original -> {'barcode': str, 'cantidad': float}

    Returns:
        List of dicts with 'filename' and 'content' for each updated XML
    """
    import logging
    logger = logging.getLogger(__name__)

    individual_xmls = []

    logger.info(f"Starting update_xml_with_barcodes")
    logger.info(f"Unified XML length: {len(unified_xml)}")
    logger.info(f"First 500 chars of XML: {unified_xml[:500]}")
    logger.info(f"Codigo map entries: {len(codigo_map)}")
    logger.info(f"Codigo map: {codigo_map}")

    # Check if this is an SRI authorization XML (single file format)
    if '<autorizacion>' in unified_xml and '<facturasUnificadas>' not in unified_xml:
        logger.info("Detected SRI authorization XML format (single file)")
        return _update_sri_authorization_xml(unified_xml, codigo_map)

    # Otherwise, treat as backend-generated unified XML
    logger.info("Detected backend unified XML format")
    # Find all factura elements
    factura_pattern = re.compile(r'<factura[^>]*>(.*?)</factura>', re.DOTALL)
    facturas = list(factura_pattern.finditer(unified_xml))
    logger.info(f"Facturas found by regex: {len(facturas)}")

    for idx, match in enumerate(facturas):
        logger.info(f"Processing factura {idx}")
        full_factura = match.group(0)
        factura_content = match.group(1)

        logger.info(f"Factura content length: {len(factura_content)}")
        logger.info(f"First 200 chars: {factura_content[:200]}")

        # Extract filename
        filename_match = re.search(r'filename="([^"]*)"', full_factura)
        filename = filename_match.group(1) if filename_match else f'factura_{len(individual_xmls)}.xml'
        logger.info(f"Filename: {filename}")

        # Unescape XML content
        decoded_content = unescape_xml(factura_content.strip())
        logger.info(f"Decoded content length: {len(decoded_content)}")
        logger.info(f"First 300 chars of decoded: {decoded_content[:300]}")

        # Find comprobante CDATA section
        comprobante_match = re.search(r'<comprobante><!\[CDATA\[(.*?)\]\]></comprobante>', decoded_content, re.DOTALL)
        if not comprobante_match:
            logger.warning(f"No comprobante CDATA found in factura {idx}")
            continue

        logger.info(f"Found comprobante CDATA section")
        inner_xml = comprobante_match.group(1)

        # Pass 1: Replace códigos with barcodes
        replacements_made = 0
        for codigo_original, data in codigo_map.items():
            codigo_barras = data['barcode']
            # Escape special regex characters in codigo
            escaped_codigo = re.escape(codigo_original)
            pattern = f'(<codigoPrincipal>){escaped_codigo}(</codigoPrincipal>)'
            # Use lambda to avoid backslash interpretation issues with numeric barcodes
            new_xml, count = re.subn(pattern, lambda m: f'{m.group(1)}{codigo_barras}{m.group(2)}', inner_xml)
            if count > 0:
                replacements_made += count
                inner_xml = new_xml

        logger.info(f"Barcode replacements made: {replacements_made}")

        # Pass 2: Replace cantidades for each barcode and remove duplicates
        # For products that appear multiple times, keep only the first occurrence
        # with the total quantity and remove the rest
        cantidad_replacements = 0
        detalles_removed = 0
        for codigo_original, data in codigo_map.items():
            codigo_barras = data['barcode']
            cantidad = data['cantidad']

            # Format cantidad as int if whole number, otherwise as float
            cantidad_formatted = int(cantidad) if cantidad == int(cantidad) else cantidad

            # Find all <detalle> blocks containing this barcode
            # After Pass 1, codigoPrincipal now contains barcode
            detalle_blocks = re.findall(r'<detalle>(.*?)</detalle>', inner_xml, re.DOTALL)

            first_occurrence = True
            for detalle in detalle_blocks:
                if f'<codigoPrincipal>{codigo_barras}</codigoPrincipal>' in detalle:
                    old_detalle = f'<detalle>{detalle}</detalle>'

                    if first_occurrence:
                        # Update first occurrence with total quantity
                        new_detalle = re.sub(
                            r'<cantidad>.*?</cantidad>',
                            f'<cantidad>{cantidad_formatted}</cantidad>',
                            old_detalle
                        )
                        inner_xml = inner_xml.replace(old_detalle, new_detalle, 1)
                        cantidad_replacements += 1
                        first_occurrence = False
                    else:
                        # Remove subsequent occurrences to avoid duplication
                        inner_xml = inner_xml.replace(old_detalle, '', 1)
                        detalles_removed += 1

        logger.info(f"Cantidad replacements made: {cantidad_replacements}")
        logger.info(f"Duplicate detalles removed: {detalles_removed}")

        # Reconstruct full XML with updated CDATA
        updated_xml = re.sub(
            r'<comprobante><!\[CDATA\[.*?\]\]></comprobante>',
            f'<comprobante><![CDATA[{inner_xml}]]></comprobante>',
            decoded_content,
            flags=re.DOTALL
        )

        logger.info(f"Updated XML first 200 chars: {updated_xml[:200]}")
        logger.info(f"Updated XML starts with '<factura': {updated_xml.strip().startswith('<factura')}")

        # Remove wrapper if present (caused by double-wrapping in upload)
        if updated_xml.strip().startswith('<factura '):
            # Extract content without the wrapper
            wrapper_match = re.search(r'<factura[^>]*>\s*(.*?)\s*</factura>\s*$', updated_xml, re.DOTALL)
            if wrapper_match:
                updated_xml = wrapper_match.group(1).strip()
                logger.info(f"Removed wrapper, XML now starts with: {updated_xml[:100]}")

        individual_xmls.append({
            'filename': filename.replace('.xml', '_actualizado.xml'),
            'content': updated_xml
        })
        logger.info(f"Added XML {idx} to results")

    logger.info(f"Total XMLs generated: {len(individual_xmls)}")
    return individual_xmls


def _update_sri_authorization_xml(xml_content: str, codigo_map: Dict[str, Dict[str, Any]]) -> List[Dict[str, str]]:
    """
    Update an SRI authorization XML with barcode and quantity mappings.

    Args:
        xml_content: SRI authorization XML content
        codigo_map: Dictionary mapping codigo_original -> {'barcode': str, 'cantidad': float}

    Returns:
        List with single updated XML dict
    """
    import logging
    logger = logging.getLogger(__name__)

    logger.info("Processing SRI authorization XML")

    # Find comprobante CDATA section
    comprobante_match = re.search(r'<comprobante><!\[CDATA\[(.*?)\]\]></comprobante>', xml_content, re.DOTALL)
    if not comprobante_match:
        logger.error("No CDATA section found in SRI XML")
        return []

    inner_xml = comprobante_match.group(1)
    logger.info(f"Found CDATA section, length: {len(inner_xml)}")

    # Pass 1: Replace códigos with barcodes
    replacements_made = 0
    for codigo_original, data in codigo_map.items():
        codigo_barras = data['barcode']
        escaped_codigo = re.escape(codigo_original)
        pattern = f'(<codigoPrincipal>){escaped_codigo}(</codigoPrincipal>)'
        # Use lambda to avoid backslash interpretation issues with numeric barcodes
        new_xml, count = re.subn(pattern, lambda m: f'{m.group(1)}{codigo_barras}{m.group(2)}', inner_xml)
        if count > 0:
            replacements_made += count
            inner_xml = new_xml

    logger.info(f"Barcode replacements made: {replacements_made}")

    # Pass 2: Replace cantidades for each barcode and remove duplicates
    # For products that appear multiple times, keep only the first occurrence
    # with the total quantity and remove the rest
    cantidad_replacements = 0
    detalles_removed = 0
    for codigo_original, data in codigo_map.items():
        codigo_barras = data['barcode']
        cantidad = data['cantidad']

        # Format cantidad as int if whole number, otherwise as float
        cantidad_formatted = int(cantidad) if cantidad == int(cantidad) else cantidad

        # Find all <detalle> blocks containing this barcode
        detalle_blocks = re.findall(r'<detalle>(.*?)</detalle>', inner_xml, re.DOTALL)

        first_occurrence = True
        for detalle in detalle_blocks:
            if f'<codigoPrincipal>{codigo_barras}</codigoPrincipal>' in detalle:
                old_detalle = f'<detalle>{detalle}</detalle>'

                if first_occurrence:
                    # Update first occurrence with total quantity
                    new_detalle = re.sub(
                        r'<cantidad>.*?</cantidad>',
                        f'<cantidad>{cantidad_formatted}</cantidad>',
                        old_detalle
                    )
                    inner_xml = inner_xml.replace(old_detalle, new_detalle, 1)
                    cantidad_replacements += 1
                    first_occurrence = False
                else:
                    # Remove subsequent occurrences to avoid duplication
                    inner_xml = inner_xml.replace(old_detalle, '', 1)
                    detalles_removed += 1

    logger.info(f"Cantidad replacements made: {cantidad_replacements}")
    logger.info(f"Duplicate detalles removed: {detalles_removed}")

    # Reconstruct full XML with updated CDATA
    updated_xml = re.sub(
        r'<comprobante><!\[CDATA\[.*?\]\]></comprobante>',
        f'<comprobante><![CDATA[{inner_xml}]]></comprobante>',
        xml_content,
        flags=re.DOTALL
    )

    # Extract filename from numeroAutorizacion or use default
    filename_match = re.search(r'<numeroAutorizacion>(.*?)</numeroAutorizacion>', xml_content)
    filename = f"{filename_match.group(1)}_actualizado.xml" if filename_match else "factura_actualizada.xml"

    return [{
        'filename': filename,
        'content': updated_xml
    }]


def unescape_xml(text: str) -> str:
    """Unescape XML entities."""
    return (text
            .replace('&lt;', '<')
            .replace('&gt;', '>')
            .replace('&quot;', '"')
            .replace('&apos;', "'")
            .replace('&amp;', '&'))


def update_xml_with_barcodes_consolidated(unified_xml: str, codigo_map: Dict[str, Dict[str, Any]]) -> List[Dict[str, str]]:
    """
    Update unified XML and consolidate all invoices into a single XML with all products.

    This function:
    1. Extracts all products from all invoices
    2. Consolidates products with the same barcode (summing quantities)
    3. Updates barcodes and quantities from codigo_map
    4. Generates a single XML with all consolidated products

    Args:
        unified_xml: Unified XML content with multiple invoices
        codigo_map: Dictionary mapping codigo_original -> {'barcode': str, 'cantidad': float}

    Returns:
        List with single dict containing consolidated XML
    """
    import logging
    from datetime import datetime
    logger = logging.getLogger(__name__)

    logger.info("Starting consolidated XML update")
    logger.info(f"Codigo map entries: {len(codigo_map)}")

    # Check if this is a single SRI authorization XML
    if '<autorizacion>' in unified_xml and '<facturasUnificadas>' not in unified_xml:
        logger.info("Single XML detected, using standard update")
        return _update_sri_authorization_xml(unified_xml, codigo_map)

    # Extract all facturas
    logger.info("Extracting all invoices from unified XML")
    factura_pattern = re.compile(r'<factura[^>]*>(.*?)</factura>', re.DOTALL)
    facturas = list(factura_pattern.finditer(unified_xml))
    logger.info(f"Found {len(facturas)} invoices")

    if len(facturas) == 0:
        logger.error("No invoices found in unified XML")
        return []

    # Use first invoice as template
    first_match = facturas[0]
    first_factura_content = first_match.group(1)
    decoded_first = unescape_xml(first_factura_content.strip())

    # Extract comprobante from first invoice
    comprobante_match = re.search(r'<comprobante><!\[CDATA\[(.*?)\]\]></comprobante>', decoded_first, re.DOTALL)
    if not comprobante_match:
        logger.error("No comprobante found in first invoice")
        return []

    template_xml = comprobante_match.group(1)
    logger.info("Using first invoice as template")

    # Collect all productos from all invoices (already with mapped barcodes and quantities)
    all_productos = []

    for barcode, data in codigo_map.items():
        producto_xml = f'''    <detalle>
      <codigoPrincipal>{barcode}</codigoPrincipal>
      <codigoAuxiliar>{barcode}</codigoAuxiliar>
      <descripcion>Producto {barcode}</descripcion>
      <cantidad>{data['cantidad']}</cantidad>
      <precioUnitario>0.00</precioUnitario>
      <descuento>0.00</descuento>
      <precioTotalSinImpuesto>0.00</precioTotalSinImpuesto>
      <impuestos>
        <impuesto>
          <codigo>2</codigo>
          <codigoPorcentaje>4</codigoPorcentaje>
          <tarifa>15.00</tarifa>
          <baseImponible>0.00</baseImponible>
          <valor>0.00</valor>
        </impuesto>
      </impuestos>
    </detalle>'''
        all_productos.append(producto_xml)

    logger.info(f"Created {len(all_productos)} consolidated products")

    # Build new detalles section
    new_detalles = '\n'.join(all_productos)

    # Replace detalles section in template
    # First, remove all existing detalle elements
    inner_xml = re.sub(r'<detalle>.*?</detalle>', '', template_xml, flags=re.DOTALL)

    # Find detalles wrapper and replace its content
    inner_xml = re.sub(
        r'(<detalles>).*?(</detalles>)',
        r'\1\n' + new_detalles + '\n  \\2',
        inner_xml,
        flags=re.DOTALL
    )

    # Update invoice metadata
    current_date = datetime.now().strftime('%d/%m/%Y')
    inner_xml = re.sub(
        r'<fechaEmision>.*?</fechaEmision>',
        f'<fechaEmision>{current_date}</fechaEmision>',
        inner_xml
    )

    # Update secuencial to CONSOLIDADO
    inner_xml = re.sub(
        r'<secuencial>.*?</secuencial>',
        '<secuencial>CONSOLIDADO</secuencial>',
        inner_xml
    )

    # Update numeroAutorizacion to CONSOLIDADO
    inner_xml = re.sub(
        r'<numeroAutorizacion>.*?</numeroAutorizacion>',
        '<numeroAutorizacion>CONSOLIDADO</numeroAutorizacion>',
        inner_xml
    )

    inner_xml = re.sub(
        r'<claveAcceso>.*?</claveAcceso>',
        '<claveAcceso>CONSOLIDADO</claveAcceso>',
        inner_xml
    )

    # Update totals to 0.00 (since we don't have price info)
    inner_xml = re.sub(
        r'<totalSinImpuestos>.*?</totalSinImpuestos>',
        '<totalSinImpuestos>0.00</totalSinImpuestos>',
        inner_xml
    )

    inner_xml = re.sub(
        r'<importeTotal>.*?</importeTotal>',
        '<importeTotal>0.00</importeTotal>',
        inner_xml
    )

    # Reconstruct authorization XML
    consolidated_xml = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<autorizacion>
<estado>AUTORIZADO</estado>
<numeroAutorizacion>CONSOLIDADO</numeroAutorizacion>
<fechaAutorizacion>{datetime.now().isoformat()}</fechaAutorizacion>
<ambiente>PRODUCCIÓN</ambiente>
<comprobante><![CDATA[{inner_xml}]]></comprobante>
</autorizacion>'''

    logger.info("Consolidated XML created successfully")

    return [{
        'filename': 'factura_consolidada.xml',
        'content': consolidated_xml
    }]
