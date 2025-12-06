"""
Transfer report PDF template.
Generates detailed transfer reports with before/after comparison.
"""
from datetime import datetime
from typing import List, Dict, Any
from io import BytesIO
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, Spacer

from .base_report import BaseReport
from app.services.pdf_service import PDFService


class TransferReport(BaseReport):
    """Generate PDF reports for inventory transfer operations."""

    def generate(
        self,
        transfer_data: Dict[str, Any],
        origin_before: List[Dict],
        origin_after: List[Dict],
        destination_before: List[Dict],
        destination_after: List[Dict],
        new_products: List[Dict]
    ) -> BytesIO:
        """
        Generate complete transfer report PDF.

        Args:
            transfer_data: Transfer metadata (id, date, user, destination, etc.)
            origin_before: Origin stock before transfer
            origin_after: Origin stock after transfer
            destination_before: Destination stock/prices before transfer
            destination_after: Destination stock/prices after transfer
            new_products: List of newly created products

        Returns:
            BytesIO: PDF file buffer
        """
        buffer = BytesIO()
        doc = PDFService.create_document(buffer)

        # Build PDF content
        story = []

        # Header
        story.extend(self._build_header(transfer_data))
        story.append(Spacer(1, 0.3*inch))

        # Summary
        story.extend(self._build_summary(
            transfer_data,
            len(new_products),
            len(destination_before)
        ))
        story.append(Spacer(1, 0.3*inch))

        # Origin changes
        story.append(Paragraph("ORIGEN - ALMACÉN PRINCIPAL", self.styles['SectionHeader']))
        story.append(Spacer(1, 0.1*inch))
        story.extend(self._build_origin_table(origin_before, origin_after))
        story.append(Spacer(1, 0.3*inch))

        # New products in destination
        if new_products:
            story.append(Paragraph("DESTINO - PRODUCTOS NUEVOS CREADOS", self.styles['SectionHeader']))
            story.append(Spacer(1, 0.1*inch))
            story.extend(self._build_new_products_table(new_products))
            story.append(Spacer(1, 0.3*inch))

        # Updated products in destination
        if destination_before:
            story.append(Paragraph("DESTINO - PRODUCTOS ACTUALIZADOS", self.styles['SectionHeader']))
            story.append(Spacer(1, 0.1*inch))
            story.extend(self._build_updated_products_table(destination_before, destination_after))

        # Build PDF
        doc.build(story)
        buffer.seek(0)
        return buffer

    def _build_header(self, transfer_data: Dict) -> List:
        """Build PDF header section."""
        elements = []

        # Title
        title = Paragraph(
            "INFORME DE TRANSFERENCIA DE INVENTARIO",
            self.styles['CustomTitle']
        )
        elements.append(title)

        # Transfer info
        info_data = [
            f"<b>ID Transferencia:</b> #{transfer_data.get('id', 'N/A')}",
            f"<b>Fecha:</b> {transfer_data.get('date', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))}",
            f"<b>Usuario:</b> {transfer_data.get('username', 'N/A')}",
            f"<b>Confirmado por:</b> {transfer_data.get('confirmed_by', 'N/A')}",
            f"<b>Destino:</b> {transfer_data.get('destination', 'Sucursal')}",
        ]

        for info_line in info_data:
            elements.append(Paragraph(info_line, self.styles['InfoText']))
            elements.append(Spacer(1, 0.05*inch))

        return elements

    def _build_summary(self, transfer_data: Dict, new_count: int, updated_count: int) -> List:
        """Build summary section."""
        elements = []

        elements.append(Paragraph("RESUMEN", self.styles['CustomSubtitle']))

        summary_data = [
            ['Total de productos transferidos:', str(transfer_data.get('total_items', 0))],
            ['Total de unidades:', str(transfer_data.get('total_quantity', 0))],
            ['Productos nuevos creados:', str(new_count)],
            ['Productos actualizados:', str(updated_count)],
        ]

        summary_table = self.create_table(
            summary_data,
            col_widths=[4*inch, 2*inch],
            header_color='#333333'
        )

        # Customize for summary (no header row)
        from reportlab.platypus import TableStyle
        from reportlab.lib import colors
        summary_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 0, colors.white),  # No grid for summary
        ]))

        elements.append(summary_table)
        return elements

    def _build_origin_table(self, before: List[Dict], after: List[Dict]) -> List:
        """Build origin stock changes table."""
        after_dict = {item['barcode']: item for item in after}

        # Table data
        data = [['Código', 'Producto', 'Stock Antes', 'Transferido', 'Stock Después', 'Diferencia']]

        for before_item in before:
            barcode = before_item['barcode']
            after_item = after_dict.get(barcode, {})

            stock_before = before_item.get('qty_available', 0)
            stock_after = after_item.get('qty_available', 0)
            transferred = before_item.get('quantity', 0)
            difference = stock_after - stock_before

            data.append([
                barcode,
                PDFService.truncate_text(before_item.get('name', ''), 30),
                PDFService.format_quantity(stock_before),
                PDFService.format_quantity(transferred),
                PDFService.format_quantity(stock_after),
                PDFService.format_quantity(difference)
            ])

        table = self.create_table(
            data,
            col_widths=[1.2*inch, 2.5*inch, 1*inch, 1*inch, 1*inch, 1*inch],
            header_color='#0066cc'
        )

        # Center numeric columns
        from reportlab.platypus import TableStyle
        table.setStyle(TableStyle([
            ('ALIGN', (2, 1), (-1, -1), 'CENTER'),
        ]))

        return [table]

    def _build_new_products_table(self, new_products: List[Dict]) -> List:
        """Build table of newly created products."""
        data = [['Código', 'Producto', 'Costo', 'Precio Venta', 'Stock Inicial']]

        for product in new_products:
            data.append([
                product.get('barcode', ''),
                PDFService.truncate_text(product.get('name', ''), 30),
                PDFService.format_currency(product.get('standard_price', 0)),
                PDFService.format_currency(product.get('list_price', 0)),
                PDFService.format_quantity(product.get('quantity', 0))
            ])

        table = self.create_table(
            data,
            col_widths=[1.2*inch, 2.8*inch, 1.2*inch, 1.2*inch, 1.2*inch],
            header_color='#00aa00'
        )

        # Right-align price columns
        from reportlab.platypus import TableStyle
        table.setStyle(TableStyle([
            ('ALIGN', (2, 1), (-1, -1), 'RIGHT'),
        ]))

        return [table]

    def _build_updated_products_table(self, before: List[Dict], after: List[Dict]) -> List:
        """Build table of updated products."""
        after_dict = {item['barcode']: item for item in after}

        data = [[
            'Código', 'Producto',
            'Stock\nAntes', 'Stock\nDespués',
            'Costo\nAntes', 'Costo\nDespués',
            'Precio\nAntes', 'Precio\nDespués'
        ]]

        for before_item in before:
            barcode = before_item['barcode']
            after_item = after_dict.get(barcode)

            if not after_item:
                continue

            data.append([
                barcode,
                PDFService.truncate_text(before_item.get('name', ''), 25),
                PDFService.format_quantity(before_item.get('qty_available', 0)),
                PDFService.format_quantity(after_item.get('qty_available', 0)),
                PDFService.format_currency(before_item.get('standard_price', 0)),
                PDFService.format_currency(after_item.get('standard_price', 0)),
                PDFService.format_currency(before_item.get('list_price', 0)),
                PDFService.format_currency(after_item.get('list_price', 0))
            ])

        table = self.create_table(
            data,
            col_widths=[0.9*inch, 2*inch, 0.8*inch, 0.8*inch, 0.9*inch, 0.9*inch, 0.9*inch, 0.9*inch],
            header_color='#ff8800'
        )

        # Center all data columns
        from reportlab.platypus import TableStyle
        table.setStyle(TableStyle([
            ('ALIGN', (2, 1), (-1, -1), 'CENTER'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
        ]))

        return [table]
