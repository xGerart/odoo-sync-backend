"""Utils package for facturas processing."""
from .xml_parser import (
    extract_productos_from_xml,
    create_unified_xml,
    update_xml_with_barcodes
)

__all__ = [
    'extract_productos_from_xml',
    'create_unified_xml',
    'update_xml_with_barcodes'
]
