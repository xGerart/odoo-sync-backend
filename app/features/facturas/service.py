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

        Args:
            xml_files: List of dicts with 'filename' and 'content'

        Returns:
            Tuple of (productos list, unified_xml string)
        """
        all_productos = []
        productos_map = {}  # Use dict to track unique products by codigo

        for xml_data in xml_files:
            content = xml_data['content']
            productos = extract_productos_from_xml(content)

            for producto in productos:
                codigo = producto['codigo']
                # Only add if not already in map (keep first occurrence)
                if codigo not in productos_map:
                    productos_map[codigo] = producto
                    all_productos.append(producto)

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
        headers = ['CÓDIGO', 'DESCRIPCIÓN', 'PRECIO UNITARIO', 'CÓDIGO DE BARRAS']
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
                producto['precio_unitario'],
                ''  # Empty barcode column
            ])

        # Set column widths
        sheet.column_dimensions['A'].width = 15
        sheet.column_dimensions['B'].width = 70
        sheet.column_dimensions['C'].width = 18
        sheet.column_dimensions['D'].width = 20

        # Format price column
        for row in range(2, len(productos) + 2):
            cell = sheet.cell(row=row, column=3)
            cell.number_format = '$#,##0.00'

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
            codigo_barras = str(row[3]).strip() if row[3] else None

            if codigo and codigo_barras and codigo_barras != '':
                # Store both trimmed and with-space versions to handle XMLs with trailing spaces
                codigo_map[codigo] = codigo_barras
                codigo_map[codigo + ' '] = codigo_barras  # Handle trailing space in XML

        # Update XMLs
        updated_xmls = update_xml_with_barcodes(unified_xml, codigo_map)

        return updated_xmls
