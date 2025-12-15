"""
XML parsing utilities for facturas.
"""
import re
import xml.etree.ElementTree as ET
from typing import List, Dict, Any
from html import unescape


def extract_productos_from_xml(xml_content: str) -> List[Dict[str, Any]]:
    """
    Extract products from XML factura content.

    Args:
        xml_content: XML string content

    Returns:
        List of product dictionaries
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
        codigo_match = re.search(r'<codigoPrincipal>(.*?)</codigoPrincipal>', detalle_content)
        descripcion_match = re.search(r'<descripcion>(.*?)</descripcion>', detalle_content)
        cantidad_match = re.search(r'<cantidad>(.*?)</cantidad>', detalle_content)
        precio_total_match = re.search(r'<precioTotalSinImpuesto>(.*?)</precioTotalSinImpuesto>', detalle_content)

        if codigo_match and descripcion_match and cantidad_match and precio_total_match:
            codigo = codigo_match.group(1)
            descripcion = unescape(descripcion_match.group(1))

            # Replace common HTML entities
            descripcion = (descripcion
                          .replace('&ntilde;', 'ñ')
                          .replace('&Ntilde;', 'Ñ'))

            cantidad = float(cantidad_match.group(1))

            productos.append({
                'codigo': codigo,
                'descripcion': descripcion,
                'cantidad': cantidad
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
