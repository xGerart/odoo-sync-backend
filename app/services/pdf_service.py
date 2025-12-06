"""
Generic PDF generation service.
Provides common functionality for all PDF reports.
"""
from io import BytesIO
from typing import Dict, Any
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate
from reportlab.lib.units import inch


class PDFService:
    """
    Base PDF service with common utilities.
    Used by specific report templates.
    """

    @staticmethod
    def create_document(buffer: BytesIO, **kwargs) -> SimpleDocTemplate:
        """
        Create a PDF document with standard settings.

        Args:
            buffer: BytesIO buffer for PDF output
            **kwargs: Optional document settings (pagesize, margins, etc.)

        Returns:
            SimpleDocTemplate: Configured document
        """
        pagesize = kwargs.get('pagesize', letter)
        right_margin = kwargs.get('rightMargin', 0.75 * inch)
        left_margin = kwargs.get('leftMargin', 0.75 * inch)
        top_margin = kwargs.get('topMargin', 0.75 * inch)
        bottom_margin = kwargs.get('bottomMargin', 0.75 * inch)

        return SimpleDocTemplate(
            buffer,
            pagesize=pagesize,
            rightMargin=right_margin,
            leftMargin=left_margin,
            topMargin=top_margin,
            bottomMargin=bottom_margin
        )

    @staticmethod
    def format_currency(amount: float) -> str:
        """Format amount as currency."""
        return f"${amount:.2f}"

    @staticmethod
    def format_quantity(quantity: float) -> str:
        """Format quantity with proper decimals."""
        return f"{quantity:.0f}"

    @staticmethod
    def truncate_text(text: str, max_length: int = 30) -> str:
        """Truncate text to max length."""
        return text[:max_length] if len(text) > max_length else text
