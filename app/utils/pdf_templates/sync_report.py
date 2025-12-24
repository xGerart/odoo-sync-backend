"""
PDF report template for product synchronization.
"""
from io import BytesIO
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
)
from reportlab.lib.units import inch
from app.utils.pdf_templates.base_report import BaseReport
from app.services.pdf_service import PDFService


class SyncReport(BaseReport):
    """PDF report for product synchronization operations."""

    def generate(
        self,
        sync_data: dict,
        created_products: list,
        updated_products: list,
        error_products: list
    ) -> BytesIO:
        """
        Generate PDF report for product sync.

        Args:
            sync_data: Dictionary with sync metadata (user, date, totals)
            created_products: List of created products
            updated_products: List of updated products
            error_products: List of products with errors

        Returns:
            BytesIO buffer containing the PDF
        """
        buffer = BytesIO()
        doc = PDFService.create_document(
            buffer,
            pagesize=letter,
            title=f"Reporte de Sincronización - {sync_data.get('date', 'N/A')}"
        )

        story = []

        # Header
        story.extend(self._build_header(sync_data))

        # Summary
        story.extend(self._build_summary(sync_data))

        # Created products table
        if created_products:
            story.extend(self._build_created_products_table(created_products))

        # Updated products table
        if updated_products:
            story.extend(self._build_updated_products_table(updated_products))

        # Error products table
        if error_products:
            story.extend(self._build_error_products_table(error_products))

        # Build PDF
        doc.build(story)
        buffer.seek(0)
        return buffer

    def _build_header(self, sync_data: dict) -> list:
        """Build report header."""
        elements = []

        # Title
        title = Paragraph(
            "REPORTE DE SINCRONIZACIÓN DE PRODUCTOS",
            self.styles['CustomTitle']
        )
        elements.append(title)
        elements.append(Spacer(1, 0.3 * inch))

        # Info table
        info_data = [
            ["Fecha:", sync_data.get('date', 'N/A')],
            ["Usuario:", sync_data.get('user', 'Sistema')],
            ["Origen:", sync_data.get('source', 'Odoo Principal')],
        ]

        info_table = Table(info_data, colWidths=[1.5 * inch, 4 * inch])
        info_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#1a1a1a')),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))

        elements.append(info_table)
        elements.append(Spacer(1, 0.3 * inch))

        return elements

    def _build_summary(self, sync_data: dict) -> list:
        """Build summary section."""
        elements = []

        # Summary title
        summary_title = Paragraph("RESUMEN", self.styles['SectionHeader'])
        elements.append(summary_title)
        elements.append(Spacer(1, 0.1 * inch))

        # Summary data
        total = sync_data.get('total_processed', 0)
        created = sync_data.get('created_count', 0)
        updated = sync_data.get('updated_count', 0)
        errors = sync_data.get('errors_count', 0)

        summary_data = [
            ["Total Procesados", "Creados", "Actualizados", "Errores"],
            [str(total), str(created), str(updated), str(errors)]
        ]

        summary_table = Table(summary_data, colWidths=[1.5 * inch] * 4)
        summary_table.setStyle(TableStyle([
            # Header
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0066cc')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
            # Data rows
            ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#f0f0f0')),
            ('FONTNAME', (0, 1), (-1, 1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 1), (-1, 1), 12),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))

        elements.append(summary_table)
        elements.append(Spacer(1, 0.3 * inch))

        return elements

    def _build_created_products_table(self, products: list) -> list:
        """Build table of created products."""
        elements = []

        # Section title
        title = Paragraph(
            f"PRODUCTOS CREADOS ({len(products)})",
            self.styles['SectionHeader']
        )
        elements.append(title)
        elements.append(Spacer(1, 0.1 * inch))

        # Table header
        data = [["#", "Código de Barras", "Nombre del Producto", "Precio Costo", "Precio Venta", "Stock"]]

        # Table rows
        for idx, product in enumerate(products, 1):
            # Use display_price if available (price with IVA), otherwise calculate it
            display_price = product.get('display_price')
            if display_price is None:
                list_price = product.get('list_price', 0)
                display_price = list_price * 1.15 if list_price else 0

            row = [
                str(idx),
                product.get('barcode', 'N/A'),
                PDFService.truncate_text(product.get('product_name', 'N/A'), 35),
                PDFService.format_currency(product.get('standard_price', 0)),
                PDFService.format_currency(display_price),  # Price WITH IVA
                PDFService.format_quantity(product.get('qty_available', 0))
            ]
            data.append(row)

        # Create table
        col_widths = [0.4 * inch, 1.2 * inch, 2.4 * inch, 1 * inch, 1 * inch, 0.8 * inch]
        table = self.create_table(
            data,
            col_widths,
            header_color='#28a745'
        )

        elements.append(table)
        elements.append(Spacer(1, 0.3 * inch))

        return elements

    def _build_updated_products_table(self, products: list) -> list:
        """Build table of updated products."""
        elements = []

        # Section title
        title = Paragraph(
            f"PRODUCTOS ACTUALIZADOS ({len(products)})",
            self.styles['SectionHeader']
        )
        elements.append(title)
        elements.append(Spacer(1, 0.1 * inch))

        # Table header
        data = [["#", "Código de Barras", "Nombre", "Costo", "P. Venta", "Stock"]]

        # Table rows
        for idx, product in enumerate(products, 1):
            # Calculate price with IVA (15%) for display
            list_price = product.get('list_price', 0)
            price_with_iva = list_price * 1.15 if list_price else 0

            row = [
                str(idx),
                product.get('barcode', 'N/A'),  # Full barcode, no truncation
                PDFService.truncate_text(product.get('product_name', 'N/A'), 28),
                PDFService.format_currency(product.get('standard_price', 0)),
                PDFService.format_currency(price_with_iva),  # Price WITH IVA
                PDFService.format_quantity(product.get('qty_available', 0))
            ]
            data.append(row)

        # Create table
        col_widths = [0.3 * inch, 1.1 * inch, 2.5 * inch, 0.75 * inch, 0.75 * inch, 0.6 * inch]
        table = self.create_table(
            data,
            col_widths,
            header_color='#ffc107'
        )

        elements.append(table)
        elements.append(Spacer(1, 0.3 * inch))

        return elements

    def _build_error_products_table(self, products: list) -> list:
        """Build table of products with errors."""
        elements = []

        # Section title
        title = Paragraph(
            f"PRODUCTOS CON ERRORES ({len(products)})",
            self.styles['SectionHeader']
        )
        elements.append(title)
        elements.append(Spacer(1, 0.1 * inch))

        # Table header
        data = [["#", "Código de Barras", "Nombre del Producto", "Error"]]

        # Table rows
        for idx, product in enumerate(products, 1):
            row = [
                str(idx),
                product.get('barcode', 'N/A'),
                PDFService.truncate_text(product.get('product_name', 'N/A'), 30),
                PDFService.truncate_text(product.get('error_details', 'Error desconocido'), 35)
            ]
            data.append(row)

        # Create table
        col_widths = [0.4 * inch, 1.2 * inch, 2.2 * inch, 2.8 * inch]
        table = self.create_table(
            data,
            col_widths,
            header_color='#dc3545'
        )

        elements.append(table)
        elements.append(Spacer(1, 0.2 * inch))

        return elements
