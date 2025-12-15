"""
Service for factura processing.
"""
import io
from typing import List, Dict, Any
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment
from openpyxl.utils import get_column_letter

from .utils import extract_productos_from_xml, create_unified_xml, update_xml_with_barcodes


class FacturaService:
    """Service for processing facturas and generating Excel."""

    @staticmethod
    def extract_productos_from_xmls(xml_files: List[Dict[str, str]]) -> tuple[List[Dict[str, Any]], str]:
        """
        Extract unique products from multiple XML files.
        Sums quantities for products with the same codigo.

        Args:
            xml_files: List of dicts with 'filename' and 'content'

        Returns:
            Tuple of (productos list, unified_xml string)
        """
        productos_map = {}  # Use dict to track unique products by codigo

        for xml_data in xml_files:
            content = xml_data['content']
            productos = extract_productos_from_xml(content)

            for producto in productos:
                codigo = producto['codigo']
                cantidad = producto.get('cantidad', 0)

                if codigo not in productos_map:
                    # First occurrence: store with cantidad
                    productos_map[codigo] = {
                        'codigo': producto['codigo'],
                        'descripcion': producto['descripcion'],
                        'cantidad': cantidad
                    }
                else:
                    # Duplicate: sum quantities
                    productos_map[codigo]['cantidad'] += cantidad

        # Convert map to list
        all_productos = list(productos_map.values())

        # Create unified XML
        unified_xml = create_unified_xml(xml_files)

        return all_productos, unified_xml

    @staticmethod
    def generate_excel(productos: List[Dict[str, Any]]) -> bytes:
        """
        Generate Excel file from productos list.

        Args:
            productos: List of product dictionaries

        Returns:
            Excel file as bytes
        """
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Productos"

        # Headers
        headers = ['CÓDIGO', 'DESCRIPCIÓN', 'CANTIDAD', 'CÓDIGO DE BARRAS']
        sheet.append(headers)

        # Style headers
        for col_num, header in enumerate(headers, 1):
            cell = sheet.cell(row=1, column=col_num)
            cell.font = Font(bold=True)
            cell.alignment = Alignment(horizontal='center')

        # Add productos
        for producto in productos:
            sheet.append([
                producto['codigo'],
                producto['descripcion'],
                producto['cantidad'],
                ''  # Empty barcode column
            ])

        # Set column widths
        sheet.column_dimensions['A'].width = 15
        sheet.column_dimensions['B'].width = 70
        sheet.column_dimensions['C'].width = 12
        sheet.column_dimensions['D'].width = 20

        # Format cantidad column (integer format)
        for row in range(2, len(productos) + 2):
            cell = sheet.cell(row=row, column=3)
            cell.number_format = '0'

        # Format barcode column as text
        for row in range(2, len(productos) + 2):
            cell = sheet.cell(row=row, column=4)
            cell.number_format = '@'

        # Save to bytes
        excel_buffer = io.BytesIO()
        workbook.save(excel_buffer)
        excel_buffer.seek(0)

        return excel_buffer.getvalue()

    @staticmethod
    def update_xmls_with_barcodes(unified_xml: str, excel_data: List[List[Any]]) -> List[Dict[str, str]]:
        """
        Update XMLs with barcodes from Excel data.

        Args:
            unified_xml: Unified XML content
            excel_data: Excel rows as list of lists

        Returns:
            List of updated XML files with 'filename' and 'content'
        """
        # Build codigo_map from Excel data
        # Row 0 is headers, so start from row 1
        codigo_map = {}

        for row in excel_data[1:]:  # Skip header row
            if len(row) < 4:
                continue

            codigo = str(row[0]).strip() if row[0] else None
            cantidad = float(row[2]) if row[2] else 0  # Column C: cantidad
            codigo_barras = str(row[3]).strip() if row[3] else None

            if codigo:
                # If barcode is empty, use original codigo (no barcode change, only cantidad update)
                if not codigo_barras or codigo_barras == '':
                    codigo_barras = codigo

                # Store barcode and cantidad
                data = {
                    'barcode': codigo_barras,
                    'cantidad': cantidad
                }
                codigo_map[codigo] = data
                codigo_map[codigo + ' '] = data  # Handle trailing space in XML

        # Update XMLs
        updated_xmls = update_xml_with_barcodes(unified_xml, codigo_map)

        return updated_xmls
