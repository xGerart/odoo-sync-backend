"""Utils package for facturas processing."""
from .xml_parser import (
    extract_productos_from_xml,
    create_unified_xml,
    update_xml_with_barcodes,
    update_xml_with_barcodes_consolidated
)

__all__ = [
    'extract_productos_from_xml',
    'create_unified_xml',
    'update_xml_with_barcodes',
    'update_xml_with_barcodes_consolidated'
]
