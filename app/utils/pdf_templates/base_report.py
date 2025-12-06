"""
Base class for all PDF reports.
Provides common styling and layout utilities.
"""
from typing import List
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.platypus import Table, TableStyle


class BaseReport:
    """
    Base class for PDF reports.
    Provides common styles and utilities that all reports can use.
    """

    def __init__(self):
        """Initialize base report with common styles."""
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()

    def _setup_custom_styles(self):
        """Setup custom paragraph styles used across all reports."""
        # Title style
        self.styles.add(ParagraphStyle(
            name='CustomTitle',
            parent=self.styles['Heading1'],
            fontSize=18,
            textColor=colors.HexColor('#1a1a1a'),
            spaceAfter=30,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        ))

        # Subtitle style
        self.styles.add(ParagraphStyle(
            name='CustomSubtitle',
            parent=self.styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#333333'),
            spaceAfter=12,
            fontName='Helvetica-Bold'
        ))

        # Section header style
        self.styles.add(ParagraphStyle(
            name='SectionHeader',
            parent=self.styles['Heading3'],
            fontSize=12,
            textColor=colors.HexColor('#0066cc'),
            spaceAfter=10,
            fontName='Helvetica-Bold'
        ))

        # Info text style
        self.styles.add(ParagraphStyle(
            name='InfoText',
            parent=self.styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor('#555555'),
        ))

    def create_table(
        self,
        data: List[List],
        col_widths: List,
        header_color: str = '#0066cc',
        stripe_colors: List = None
    ) -> Table:
        """
        Create a styled table with common formatting.

        Args:
            data: Table data (rows of columns)
            col_widths: Column widths
            header_color: Header background color (hex)
            stripe_colors: Optional row stripe colors

        Returns:
            Styled Table object
        """
        if stripe_colors is None:
            stripe_colors = [colors.white, colors.HexColor('#f0f0f0')]

        table = Table(data, colWidths=col_widths)

        # Apply standard table styling
        table.setStyle(TableStyle([
            # Header
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(header_color)),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),

            # Body
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), stripe_colors),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 1), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
        ]))

        return table
