"""
Adjustment report PDF template.
Generates detailed adjustment reports with before/after comparison.
"""
from datetime import datetime
from typing import List, Dict, Any
from io import BytesIO
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, Spacer, TableStyle
from reportlab.lib import colors

from .base_report import BaseReport
from app.services.pdf_service import PDFService


class AdjustmentReport(BaseReport):
    """Generate PDF reports for inventory adjustment operations."""

    def generate(
        self,
        adjustment_data: Dict[str, Any],
        snapshots_before: List[Dict],
        snapshots_after: List[Dict]
    ) -> BytesIO:
        """
        Generate complete adjustment report PDF.

        Args:
            adjustment_data: Adjustment metadata (id, date, user, type, reason, etc.)
            snapshots_before: Stock before adjustment
            snapshots_after: Stock after adjustment

        Returns:
            BytesIO: PDF file buffer
        """
        buffer = BytesIO()
        doc = PDFService.create_document(buffer)

        story = []

        # Header
        story.extend(self._build_header(adjustment_data))
        story.append(Spacer(1, 0.3*inch))

        # Summary
        story.extend(self._build_summary(adjustment_data))
        story.append(Spacer(1, 0.3*inch))

        # Stock changes
        story.append(Paragraph("CAMBIOS EN INVENTARIO", self.styles['SectionHeader']))
        story.append(Spacer(1, 0.1*inch))
        story.extend(self._build_changes_table(snapshots_before, snapshots_after, adjustment_data))

        doc.build(story)
        buffer.seek(0)
        return buffer

    def _build_header(self, adjustment_data: Dict) -> List:
        """Build PDF header section."""
        elements = []

        # Title based on adjustment type
        type_titles = {
            'entry': 'INGRESO DE INVENTARIO',
            'exit': 'SALIDA DE INVENTARIO',
            'adjustment': 'AJUSTE DE INVENTARIO'
        }
        title = type_titles.get(
            adjustment_data.get('adjustment_type', ''),
            'AJUSTE DE INVENTARIO'
        )

        title_p = Paragraph(f"INFORME DE {title}", self.styles['CustomTitle'])
        elements.append(title_p)

        # Adjustment info
        info_data = [
            f"<b>ID Ajuste:</b> #{adjustment_data.get('id', 'N/A')}",
            f"<b>Fecha:</b> {adjustment_data.get('date', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))}",
            f"<b>Usuario:</b> {adjustment_data.get('username', 'N/A')}",
            f"<b>Confirmado por:</b> {adjustment_data.get('confirmed_by', 'N/A')}",
            f"<b>Ubicación:</b> {adjustment_data.get('location_name', 'Principal')}",
        ]

        for info_line in info_data:
            elements.append(Paragraph(info_line, self.styles['InfoText']))
            elements.append(Spacer(1, 0.05*inch))

        return elements

    def _build_summary(self, adjustment_data: Dict) -> List:
        """Build summary section."""
        elements = []

        elements.append(Paragraph("RESUMEN", self.styles['CustomSubtitle']))

        # Format reason for display
        reason_display = adjustment_data.get('reason', 'N/A')
        reason_map = {
            'purchase': 'Compra',
            'return_in': 'Devolución de cliente',
            'correction_in': 'Corrección positiva',
            'sale': 'Venta',
            'damage': 'Producto dañado',
            'loss': 'Pérdida',
            'theft': 'Robo',
            'return_out': 'Devolución a proveedor',
            'correction_out': 'Corrección negativa',
            'local_service_use': 'Uso local de servicios',
            'expired': 'Caducado',
            'physical_count': 'Conteo físico',
            'system_correction': 'Corrección de sistema'
        }
        reason_display = reason_map.get(reason_display, reason_display)

        type_display = adjustment_data.get('adjustment_type', 'N/A')
        type_map = {
            'entry': 'Entrada',
            'exit': 'Salida',
            'adjustment': 'Ajuste/Conteo'
        }
        type_display = type_map.get(type_display, type_display)

        summary_data = [
            ['Total de productos ajustados:', str(adjustment_data.get('total_items', 0))],
            ['Total de unidades:', str(adjustment_data.get('total_quantity', 0))],
            ['Tipo de ajuste:', type_display],
            ['Razón:', reason_display],
        ]

        summary_table = self.create_table(
            summary_data,
            col_widths=[4*inch, 2*inch],
            header_color='#333333'
        )

        # Customize for summary
        summary_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 0, colors.white),
        ]))

        elements.append(summary_table)
        return elements

    def _build_changes_table(
        self,
        before: List[Dict],
        after: List[Dict],
        adjustment_data: Dict
    ) -> List:
        """Build stock changes table."""
        after_dict = {item['barcode']: item for item in after}

        # Determine color based on adjustment type
        type_colors = {
            'entry': '#00aa00',    # Green
            'exit': '#cc0000',     # Red
            'adjustment': '#ff8800' # Orange
        }
        header_color = type_colors.get(
            adjustment_data.get('adjustment_type', ''),
            '#0066cc'
        )

        data = [['Código', 'Producto', 'Stock Antes', 'Ajustado', 'Stock Después', 'Diferencia']]

        for before_item in before:
            barcode = before_item['barcode']
            after_item = after_dict.get(barcode, {})

            stock_before = before_item.get('qty_available', 0)
            stock_after = after_item.get('qty_available', 0)
            adjusted = stock_after - stock_before

            data.append([
                barcode,
                PDFService.truncate_text(before_item.get('name', ''), 30),
                PDFService.format_quantity(stock_before),
                PDFService.format_quantity(adjusted),
                PDFService.format_quantity(stock_after),
                PDFService.format_quantity(adjusted)
            ])

        table = self.create_table(
            data,
            col_widths=[1.2*inch, 2.5*inch, 1*inch, 1*inch, 1*inch, 1*inch],
            header_color=header_color
        )

        # Center numeric columns
        table.setStyle(TableStyle([
            ('ALIGN', (2, 1), (-1, -1), 'CENTER'),
        ]))

        return [table]
