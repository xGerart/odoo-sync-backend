"""
Service for factura processing.
Handles both legacy Excel workflow and new pending invoices workflow.
"""
import io
import re
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment

from app.infrastructure.odoo import OdooClient
from app.models import (
    PendingInvoice,
    PendingInvoiceItem,
    InvoiceHistory,
    InvoiceHistoryItem,
    InvoiceStatus
)
from app.schemas.auth import UserInfo
from app.schemas.invoice import (
    InvoiceUploadResponse,
    PendingInvoiceListResponse,
    PendingInvoiceResponse,
    InvoiceItemResponse,
    InvoiceSyncResponse,
    InvoiceHistoryListResponse,
    InvoiceHistoryResponse
)
from app.core.constants import UserRole, OdooModel
from app.utils.timezone import get_ecuador_now
from .utils import extract_productos_from_xml, create_unified_xml, update_xml_with_barcodes


logger = logging.getLogger(__name__)


class FacturaService:
    """Service for processing facturas and generating Excel."""

    def __init__(self, db: Session = None, odoo_client: OdooClient = None):
        """
        Initialize factura service.

        Args:
            db: Database session for persistence
            odoo_client: Odoo client for syncing
        """
        self.db = db
        self.odoo_client = odoo_client

    # ========================================================================
    # NEW METHODS - PENDING INVOICES WORKFLOW
    # ========================================================================

    def upload_and_create_pending_invoices(
        self,
        xml_files: List[Dict[str, str]],
        uploaded_by: UserInfo
    ) -> InvoiceUploadResponse:
        """
        Admin uploads XML invoices from SRI and creates pending invoices.

        Args:
            xml_files: List of dicts with 'filename' and 'content'
            uploaded_by: User uploading the invoices

        Returns:
            InvoiceUploadResponse with summary
        """
        if not self.db:
            raise ValueError("Database session required")

        invoice_ids = []
        total_products = 0

        for xml_data in xml_files:
            try:
                filename = xml_data['filename']
                content = xml_data['content']

                # Extract products from XML
                productos = extract_productos_from_xml(content)

                # Extract invoice metadata
                metadata = self._extract_invoice_metadata(content)

                # Create pending invoice
                pending_invoice = PendingInvoice(
                    invoice_number=metadata.get('invoice_number'),
                    supplier_name=metadata.get('supplier_name'),
                    invoice_date=metadata.get('invoice_date'),
                    uploaded_by_id=uploaded_by.user_id if uploaded_by.user_id else None,
                    uploaded_by_username=uploaded_by.username,
                    xml_filename=filename,
                    xml_content=content,
                    status=InvoiceStatus.PENDIENTE_REVISION
                )

                self.db.add(pending_invoice)
                self.db.flush()  # Get ID

                # Create items
                for producto in productos:
                    item = PendingInvoiceItem(
                        invoice_id=pending_invoice.id,
                        codigo_original=producto['codigo'],
                        product_name=producto['descripcion'],
                        quantity=producto.get('cantidad', 0),
                        cantidad_original=producto.get('cantidad', 0),
                        barcode=None,  # Bodeguero will fill this
                        unit_price=producto.get('precio_unitario'),
                        total_price=producto.get('precio_total'),
                        modified_by_bodeguero=False
                    )
                    self.db.add(item)

                self.db.commit()

                invoice_ids.append(pending_invoice.id)
                total_products += len(productos)

                logger.info(f"Created pending invoice {pending_invoice.id} from {filename} with {len(productos)} products")

            except Exception as e:
                self.db.rollback()
                logger.error(f"Error processing {xml_data.get('filename')}: {str(e)}")
                raise

        return InvoiceUploadResponse(
            success=True,
            message=f"Successfully created {len(invoice_ids)} pending invoices",
            invoices_created=len(invoice_ids),
            invoice_ids=invoice_ids,
            total_products=total_products
        )

    def get_pending_invoices(
        self,
        user: UserInfo,
        status: Optional[str] = None
    ) -> PendingInvoiceListResponse:
        """
        Get pending invoices filtered by role.

        Args:
            user: Current user
            status: Optional status filter

        Returns:
            List of pending invoices
        """
        if not self.db:
            raise ValueError("Database session required")

        query = self.db.query(PendingInvoice)

        # Filter by role
        if user.role == UserRole.BODEGUERO:
            # Bodeguero only sees PENDIENTE_REVISION and EN_REVISION
            query = query.filter(
                PendingInvoice.status.in_([
                    InvoiceStatus.PENDIENTE_REVISION,
                    InvoiceStatus.EN_REVISION
                ])
            )

        # Additional status filter
        if status:
            query = query.filter(PendingInvoice.status == status)

        # Order by created_at desc
        query = query.order_by(PendingInvoice.created_at.desc())

        invoices = query.all()

        # Convert to response with price filtering
        invoice_responses = [
            self._invoice_to_response(invoice, user)
            for invoice in invoices
        ]

        return PendingInvoiceListResponse(
            invoices=invoice_responses,
            total=len(invoice_responses)
        )

    def get_pending_invoice_by_id(
        self,
        invoice_id: int,
        user: UserInfo
    ) -> PendingInvoiceResponse:
        """
        Get single pending invoice with items.

        Args:
            invoice_id: Invoice ID
            user: Current user

        Returns:
            Invoice detail with price filtering
        """
        if not self.db:
            raise ValueError("Database session required")

        invoice = self.db.query(PendingInvoice).filter(
            PendingInvoice.id == invoice_id
        ).first()

        if not invoice:
            raise ValueError(f"Invoice {invoice_id} not found")

        return self._invoice_to_response(invoice, user)

    def update_invoice_item(
        self,
        invoice_id: int,
        item_id: int,
        quantity: float,
        barcode: Optional[str],
        user: UserInfo
    ) -> InvoiceItemResponse:
        """
        Bodeguero updates quantity and/or barcode for an item.

        Args:
            invoice_id: Invoice ID
            item_id: Item ID
            quantity: New quantity
            barcode: New barcode (optional)
            user: Current user (must be bodeguero)

        Returns:
            Updated item
        """
        if not self.db:
            raise ValueError("Database session required")

        # Verify user is bodeguero
        if user.role != UserRole.BODEGUERO:
            raise ValueError("Only bodegueros can update invoice items")

        # Get invoice
        invoice = self.db.query(PendingInvoice).filter(
            PendingInvoice.id == invoice_id
        ).first()

        if not invoice:
            raise ValueError(f"Invoice {invoice_id} not found")

        # Verify status
        if invoice.status not in [InvoiceStatus.PENDIENTE_REVISION, InvoiceStatus.EN_REVISION]:
            raise ValueError(f"Cannot update invoice in status {invoice.status}")

        # Get item
        item = self.db.query(PendingInvoiceItem).filter(
            PendingInvoiceItem.id == item_id,
            PendingInvoiceItem.invoice_id == invoice_id
        ).first()

        if not item:
            raise ValueError(f"Item {item_id} not found in invoice {invoice_id}")

        # Update item
        item.quantity = quantity
        if barcode is not None:
            item.barcode = barcode
        item.modified_by_bodeguero = True

        # Update invoice status to EN_REVISION if not already
        if invoice.status == InvoiceStatus.PENDIENTE_REVISION:
            invoice.status = InvoiceStatus.EN_REVISION

        self.db.commit()

        logger.info(f"Updated item {item_id} in invoice {invoice_id} by {user.username}")

        return self._item_to_response(item, user)

    def submit_invoice(
        self,
        invoice_id: int,
        user: UserInfo,
        notes: Optional[str]
    ) -> PendingInvoiceResponse:
        """
        Bodeguero marks invoice as completed.

        Args:
            invoice_id: Invoice ID
            user: Current user (must be bodeguero)
            notes: Optional notes

        Returns:
            Updated invoice
        """
        if not self.db:
            raise ValueError("Database session required")

        # Verify user is bodeguero
        if user.role != UserRole.BODEGUERO:
            raise ValueError("Only bodegueros can submit invoices")

        # Get invoice
        invoice = self.db.query(PendingInvoice).filter(
            PendingInvoice.id == invoice_id
        ).first()

        if not invoice:
            raise ValueError(f"Invoice {invoice_id} not found")

        # Update invoice
        invoice.status = InvoiceStatus.CORREGIDA
        invoice.submitted_at = get_ecuador_now().replace(tzinfo=None)
        invoice.submitted_by = user.username
        if notes:
            invoice.notes = notes

        self.db.commit()

        logger.info(f"Invoice {invoice_id} submitted by {user.username}")

        return self._invoice_to_response(invoice, user)

    def sync_invoice_to_odoo(
        self,
        invoice_id: int,
        user: UserInfo,
        notes: Optional[str]
    ) -> InvoiceSyncResponse:
        """
        Admin synchronizes invoice to Odoo.

        Args:
            invoice_id: Invoice ID
            user: Current user (must be admin)
            notes: Optional admin notes

        Returns:
            Sync result with errors
        """
        if not self.db:
            raise ValueError("Database session required")

        if not self.odoo_client:
            raise ValueError("Odoo client required")

        # Verify user is admin
        if user.role != UserRole.ADMIN:
            raise ValueError("Only admins can sync invoices")

        # Get invoice
        invoice = self.db.query(PendingInvoice).filter(
            PendingInvoice.id == invoice_id
        ).first()

        if not invoice:
            raise ValueError(f"Invoice {invoice_id} not found")

        # Verify status
        if invoice.status != InvoiceStatus.CORREGIDA:
            raise ValueError(f"Invoice must be in CORREGIDA status to sync (current: {invoice.status})")

        successful_items = []
        failed_items = []
        errors = []

        # Process each item
        for item in invoice.items:
            try:
                if not item.barcode:
                    failed_items.append({
                        'item': item,
                        'error': 'No barcode provided'
                    })
                    errors.append(f"{item.product_name}: No barcode")
                    continue

                # Search product by barcode in Odoo
                products = self.odoo_client.search_read(
                    OdooModel.PRODUCT_PRODUCT,
                    domain=[['barcode', '=', item.barcode]],
                    fields=['id', 'name', 'qty_available'],
                    limit=1
                )

                if not products:
                    failed_items.append({
                        'item': item,
                        'error': 'Product not found in Odoo'
                    })
                    errors.append(f"{item.product_name} ({item.barcode}): Not found in Odoo")
                    item.sync_success = False
                    item.sync_error = "Product not found in Odoo"
                    continue

                product = products[0]
                item.product_id = product['id']

                # TODO: Update stock in Odoo (inventory adjustment or stock.quant update)
                # For now, just mark as successful
                # In real implementation, you would:
                # 1. Create inventory adjustment
                # 2. Or update stock.quant directly
                # 3. Handle stock locations

                item.sync_success = True
                successful_items.append(item)

                logger.info(f"Synced item {item.id}: {item.product_name} ({item.barcode})")

            except Exception as e:
                logger.error(f"Error syncing item {item.id}: {str(e)}")
                failed_items.append({
                    'item': item,
                    'error': str(e)
                })
                errors.append(f"{item.product_name}: {str(e)}")
                item.sync_success = False
                item.sync_error = str(e)

        # Update invoice status
        invoice.status = InvoiceStatus.SINCRONIZADA
        invoice.synced_at = get_ecuador_now().replace(tzinfo=None)
        invoice.synced_by = user.username
        if notes:
            invoice.notes = (invoice.notes or "") + f"\nAdmin: {notes}"

        # Create history record
        self._create_history_record(
            invoice,
            successful_items,
            failed_items,
            user.username
        )

        self.db.commit()

        return InvoiceSyncResponse(
            success=len(failed_items) == 0,
            message=f"Synced {len(successful_items)}/{len(invoice.items)} items successfully",
            successful_items=len(successful_items),
            failed_items=len(failed_items),
            errors=errors
        )

    def get_invoice_history(
        self,
        skip: int = 0,
        limit: int = 50
    ) -> InvoiceHistoryListResponse:
        """
        Get invoice history (admin only).

        Args:
            skip: Pagination offset
            limit: Page size

        Returns:
            List of history records
        """
        if not self.db:
            raise ValueError("Database session required")

        query = self.db.query(InvoiceHistory).order_by(
            InvoiceHistory.synced_at.desc()
        )

        total = query.count()
        history_records = query.offset(skip).limit(limit).all()

        history_responses = [
            self._history_to_response(record)
            for record in history_records
        ]

        return InvoiceHistoryListResponse(
            history=history_responses,
            total=total
        )

    # ========================================================================
    # HELPER METHODS
    # ========================================================================

    def _extract_invoice_metadata(self, xml_content: str) -> Dict:
        """Extract invoice number, supplier, date from XML."""
        metadata = {
            'invoice_number': None,
            'supplier_name': None,
            'invoice_date': None
        }

        try:
            # Extract invoice number (numeroAutorizacion or estab-ptoEmi-secuencial)
            auth_match = re.search(r'<numeroAutorizacion>(.*?)</numeroAutorizacion>', xml_content)
            if auth_match:
                metadata['invoice_number'] = auth_match.group(1)[:50]  # Limit to 50 chars

            # Extract supplier name (razonSocial)
            supplier_match = re.search(r'<razonSocial>(.*?)</razonSocial>', xml_content)
            if supplier_match:
                metadata['supplier_name'] = supplier_match.group(1)[:255]

            # Extract date (fechaEmision)
            date_match = re.search(r'<fechaEmision>(.*?)</fechaEmision>', xml_content)
            if date_match:
                date_str = date_match.group(1)
                # Try to parse date (format: DD/MM/YYYY)
                try:
                    metadata['invoice_date'] = datetime.strptime(date_str, '%d/%m/%Y')
                except ValueError:
                    pass

        except Exception as e:
            logger.warning(f"Error extracting invoice metadata: {str(e)}")

        return metadata

    def _create_history_record(
        self,
        pending_invoice: PendingInvoice,
        successful_items: List[PendingInvoiceItem],
        failed_items: List[Dict],
        synced_by: str
    ) -> InvoiceHistory:
        """Create history record after sync."""
        total_quantity = sum(item.quantity for item in pending_invoice.items)
        total_value = sum(
            item.total_price for item in pending_invoice.items
            if item.total_price is not None
        )

        history = InvoiceHistory(
            pending_invoice_id=pending_invoice.id,
            invoice_number=pending_invoice.invoice_number or "N/A",
            supplier_name=pending_invoice.supplier_name,
            invoice_date=pending_invoice.invoice_date,
            uploaded_by=pending_invoice.uploaded_by_username,
            synced_by=synced_by,
            synced_at=get_ecuador_now().replace(tzinfo=None),
            total_items=len(pending_invoice.items),
            successful_items=len(successful_items),
            failed_items=len(failed_items),
            total_quantity=total_quantity,
            total_value=total_value if total_value > 0 else None,
            xml_content=pending_invoice.xml_content,
            has_errors=len(failed_items) > 0,
            error_summary="; ".join([f"{f['item'].product_name}: {f['error']}" for f in failed_items]) if failed_items else None
        )

        self.db.add(history)

        # Create history items
        for item in pending_invoice.items:
            history_item = InvoiceHistoryItem(
                history_id=history.id,
                codigo_original=item.codigo_original,
                barcode=item.barcode,
                product_id=item.product_id,
                product_name=item.product_name,
                quantity=item.quantity,
                unit_price=item.unit_price,
                total_value=item.total_price,
                success=item.sync_success or False,
                error_message=item.sync_error,
                was_modified=item.modified_by_bodeguero
            )
            self.db.add(history_item)

        return history

    def _invoice_to_response(
        self,
        invoice: PendingInvoice,
        user: UserInfo
    ) -> PendingInvoiceResponse:
        """Convert invoice to response with price filtering."""
        items = [self._item_to_response(item, user) for item in invoice.items]

        return PendingInvoiceResponse(
            id=invoice.id,
            invoice_number=invoice.invoice_number,
            supplier_name=invoice.supplier_name,
            invoice_date=invoice.invoice_date,
            status=invoice.status.value if isinstance(invoice.status, InvoiceStatus) else invoice.status,
            uploaded_by_username=invoice.uploaded_by_username,
            xml_filename=invoice.xml_filename,
            created_at=invoice.created_at,
            updated_at=invoice.updated_at,
            submitted_at=invoice.submitted_at,
            submitted_by=invoice.submitted_by,
            notes=invoice.notes,
            items=items,
            total_items=len(items),
            total_quantity=sum(item.quantity for item in invoice.items)
        )

    def _item_to_response(
        self,
        item: PendingInvoiceItem,
        user: UserInfo
    ) -> InvoiceItemResponse:
        """Convert item to response with price filtering."""
        # Filter prices for bodeguero
        unit_price = item.unit_price if user.role != UserRole.BODEGUERO else None
        total_price = item.total_price if user.role != UserRole.BODEGUERO else None

        return InvoiceItemResponse(
            id=item.id,
            codigo_original=item.codigo_original,
            product_name=item.product_name,
            quantity=item.quantity,
            cantidad_original=item.cantidad_original,
            barcode=item.barcode,
            modified_by_bodeguero=item.modified_by_bodeguero,
            unit_price=unit_price,
            total_price=total_price
        )

    def _history_to_response(self, history: InvoiceHistory) -> InvoiceHistoryResponse:
        """Convert history to response."""
        items = [
            InvoiceHistoryItemResponse(
                id=item.id,
                codigo_original=item.codigo_original,
                barcode=item.barcode,
                product_id=item.product_id,
                product_name=item.product_name,
                quantity=item.quantity,
                unit_price=item.unit_price,
                total_value=item.total_value,
                success=item.success,
                error_message=item.error_message,
                was_modified=item.was_modified
            )
            for item in history.items
        ]

        return InvoiceHistoryResponse(
            id=history.id,
            invoice_number=history.invoice_number,
            supplier_name=history.supplier_name,
            uploaded_by=history.uploaded_by,
            synced_by=history.synced_by,
            synced_at=history.synced_at,
            total_items=history.total_items,
            successful_items=history.successful_items,
            failed_items=history.failed_items,
            has_errors=history.has_errors,
            items=items
        )

    # ========================================================================
    # LEGACY METHODS - Excel workflow (deprecated)
    # ========================================================================

    @staticmethod
    def extract_productos_from_xmls(xml_files: List[Dict[str, str]]) -> tuple[List[Dict[str, Any]], str]:
        """
        Extract unique products from multiple XML files.
        Sums quantities for products with the same codigo.

        DEPRECATED: Use upload_and_create_pending_invoices instead

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

        DEPRECATED: Use new pending invoices workflow instead

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

        DEPRECATED: Use new pending invoices workflow instead

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
