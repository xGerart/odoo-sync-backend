"""
Factura processing endpoints.
"""
from typing import List, Optional
from fastapi import APIRouter, File, UploadFile, HTTPException, status, Depends
from fastapi.responses import Response, StreamingResponse
import io
import zipfile
import openpyxl
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.infrastructure.odoo import get_odoo_manager, OdooConnectionManager
from app.schemas.auth import UserInfo
from app.features.auth.dependencies import (
    require_admin,
    require_bodeguero,
    require_admin_or_bodeguero
)
from app.schemas.invoice import (
    InvoiceItemUpdateRequest,
    InvoiceItemSalePriceUpdateRequest,
    AdminItemUpdateRequest,
    ItemExcludeRequest,
    InvoiceSubmitRequest,
    InvoiceSyncRequest,
    PendingInvoiceListResponse,
    PendingInvoiceResponse,
    InvoiceItemResponse,
    InvoiceUploadResponse,
    InvoiceSyncResponse,
    InvoiceHistoryListResponse,
    InvoicePreviewResponse
)
from .service import FacturaService
from .schemas import ExtractProductsResponse


router = APIRouter(prefix="/facturas", tags=["Facturas"])


# ============================================================================
# NEW INVOICE WORKFLOW ENDPOINTS
# ============================================================================

@router.post("/upload", response_model=InvoiceUploadResponse)
async def upload_invoices(
    xml_files: List[UploadFile] = File(...),
    barcode_source: str = 'codigoAuxiliar',
    db: Session = Depends(get_db),
    current_user: UserInfo = Depends(require_admin)
):
    """
    Upload XML invoices from SRI and create pending invoices.

    **Requires:** Admin role

    Parses XML files, extracts invoice metadata and items,
    and saves them to database for bodeguero review.

    **Parameters:**
    - barcode_source: Which XML field to use as barcode ('codigoPrincipal' or 'codigoAuxiliar')
    """
    try:
        # Read all XML files
        xml_data_list = []
        for xml_file in xml_files:
            content = await xml_file.read()
            xml_data_list.append({
                'filename': xml_file.filename,
                'content': content.decode('utf-8')
            })

        # Create pending invoices with barcode source preference
        service = FacturaService(db=db)
        result = service.upload_and_create_pending_invoices(
            xml_data_list,
            current_user,
            barcode_source=barcode_source
        )

        return result

    except Exception as e:
        import traceback
        print(f"ERROR uploading invoices: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error uploading invoices: {str(e)}"
        )


@router.post("/preview", response_model=InvoicePreviewResponse)
async def preview_invoices(
    xml_files: List[UploadFile] = File(...),
    current_user: UserInfo = Depends(require_admin)
):
    """
    Preview XML invoices without processing.

    **Requires:** Admin role

    Parses XML files and returns preview of ALL products with BOTH
    codigo_principal and codigo_auxiliar fields visible. This allows
    users to see which barcode field contains data before selecting
    a barcode source.

    Does NOT create any database records - this is a read-only preview.

    **Parameters:**
    - xml_files: One or more XML files from SRI

    **Returns:**
    - Preview data for each file with all products
    """
    try:
        # Read all XML files
        xml_data_list = []
        for xml_file in xml_files:
            content = await xml_file.read()
            xml_data_list.append({
                'filename': xml_file.filename,
                'content': content.decode('utf-8')
            })

        # Generate preview (no DB writes)
        service = FacturaService()
        result = service.preview_invoices(xml_data_list)

        return result

    except Exception as e:
        import traceback
        print(f"ERROR previewing invoices: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error previewing invoices: {str(e)}"
        )


@router.get("/pending", response_model=PendingInvoiceListResponse)
def get_pending_invoices(
    status_filter: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: UserInfo = Depends(require_admin_or_bodeguero)
):
    """
    Get pending invoices filtered by role and status.

    **Requires:** Admin or Bodeguero role

    - Admin: can see all statuses
    - Bodeguero: only sees PENDIENTE_REVISION and EN_REVISION
    - Prices are filtered based on role (bodeguero cannot see prices)
    """
    try:
        service = FacturaService(db=db)
        result = service.get_pending_invoices(current_user, status=status_filter)
        return result

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching pending invoices: {str(e)}"
        )


@router.get("/pending/{invoice_id}", response_model=PendingInvoiceResponse)
def get_pending_invoice_detail(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: UserInfo = Depends(require_admin_or_bodeguero)
):
    """
    Get single pending invoice with items.

    **Requires:** Admin or Bodeguero role

    Prices are automatically filtered based on role:
    - Admin: sees all fields including prices
    - Bodeguero: prices are set to None
    """
    try:
        service = FacturaService(db=db)
        result = service.get_pending_invoice_by_id(invoice_id, current_user)

        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Invoice {invoice_id} not found"
            )

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching invoice: {str(e)}"
        )


@router.put("/pending/{invoice_id}/items/{item_id}")
def update_invoice_item(
    invoice_id: int,
    item_id: int,
    request: InvoiceItemUpdateRequest,
    db: Session = Depends(get_db),
    current_user: UserInfo = Depends(require_bodeguero)
):
    """
    Update invoice item quantity and/or barcode (bodeguero only).

    **Requires:** Bodeguero role

    Allows bodeguero to:
    - Update quantity (convert from boxes to units)
    - Add or correct barcode

    Invoice must be in PENDIENTE_REVISION or EN_REVISION status.
    """
    try:
        service = FacturaService(db=db)
        result = service.update_invoice_item(
            invoice_id,
            item_id,
            request.quantity,
            request.barcode,
            current_user
        )

        return result

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating item: {str(e)}"
        )


@router.patch("/pending/{invoice_id}/items/{item_id}/price")
def update_item_sale_price(
    invoice_id: int,
    item_id: int,
    request: InvoiceItemSalePriceUpdateRequest,
    db: Session = Depends(get_db),
    current_user: UserInfo = Depends(require_admin)
):
    """
    Update manual sale price for an invoice item (admin only).

    **Requires:** Admin role

    Allows admin to override the calculated sale price with a manual value.
    - Set manual_sale_price to a value to override calculated price
    - Set manual_sale_price to null to revert to calculated price
    - Price should include IVA (will be subtracted when syncing if apply_iva is enabled)

    Invoice must be in CORREGIDA or PARCIALMENTE_SINCRONIZADA status.
    """
    try:
        service = FacturaService(db=db)
        result = service.update_item_sale_price(
            invoice_id,
            item_id,
            request.manual_sale_price,
            current_user
        )

        return result

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating sale price: {str(e)}"
        )


@router.patch("/pending/{invoice_id}/items/{item_id}", response_model=InvoiceItemResponse)
def admin_update_invoice_item(
    invoice_id: int,
    item_id: int,
    request: AdminItemUpdateRequest,
    db: Session = Depends(get_db),
    current_user: UserInfo = Depends(require_admin)
):
    """
    Update invoice item (admin only - can edit all fields).

    **Requires:** Admin role

    Allows admin to:
    - Update quantity
    - Update barcode
    - Update product name (to correct errors)

    Invoice must be in CORREGIDA or PARCIALMENTE_SINCRONIZADA status.
    """
    try:
        service = FacturaService(db=db)
        result = service.admin_update_invoice_item(
            invoice_id,
            item_id,
            quantity=request.quantity,
            barcode=request.barcode,
            product_name=request.product_name,
            user=current_user
        )

        return result

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating item: {str(e)}"
        )


@router.patch("/pending/{invoice_id}/items/{item_id}/exclude", response_model=InvoiceItemResponse)
def exclude_invoice_item(
    invoice_id: int,
    item_id: int,
    request: ItemExcludeRequest,
    db: Session = Depends(get_db),
    current_user: UserInfo = Depends(require_admin)
):
    """
    Exclude or include an invoice item from sync (admin only).

    **Requires:** Admin role

    Allows admin to exclude items that are not for sale (e.g., "TRANSPORTE", services).
    Excluded items will NOT be synced to Odoo but remain visible in the invoice.

    - Set is_excluded=true to exclude the item
    - Set is_excluded=false to include the item again
    - Optionally provide a reason for exclusion

    Invoice must be in CORREGIDA or PARCIALMENTE_SINCRONIZADA status.
    """
    try:
        service = FacturaService(db=db)
        result = service.exclude_invoice_item(
            invoice_id,
            item_id,
            is_excluded=request.is_excluded,
            reason=request.reason,
            user=current_user
        )

        return result

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error excluding item: {str(e)}"
        )


@router.post("/pending/{invoice_id}/submit", response_model=PendingInvoiceResponse)
def submit_invoice(
    invoice_id: int,
    request: InvoiceSubmitRequest,
    db: Session = Depends(get_db),
    current_user: UserInfo = Depends(require_bodeguero)
):
    """
    Submit invoice as completed (bodeguero marks as ready for admin review).

    **Requires:** Bodeguero role

    Changes invoice status to CORREGIDA, indicating bodeguero has finished
    reviewing and correcting quantities and barcodes.
    """
    try:
        service = FacturaService(db=db)
        result = service.submit_invoice(invoice_id, current_user, request.notes)

        return result

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error submitting invoice: {str(e)}"
        )


@router.patch("/pending/{invoice_id}/config", response_model=PendingInvoiceResponse)
async def update_invoice_config(
    invoice_id: int,
    profit_margin: Optional[float] = None,
    apply_iva: Optional[bool] = None,
    quantity_mode: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: UserInfo = Depends(require_admin)
):
    """
    Update invoice sync configuration (admin only).

    **Requires:** Admin role

    Configure price calculation before syncing:
    - **profit_margin**: Profit margin (0.5 = 50%, range: 0-2)
    - **apply_iva**: Apply IVA to sale price calculation
    - **quantity_mode**: 'add' (sum to existing) or 'replace' (override) stock

    Can only update invoices in PENDIENTE_REVISION, EN_REVISION, or CORREGIDA status.
    """
    try:
        service = FacturaService(odoo_client=None, db=db)

        # Validate profit margin
        if profit_margin is not None and not (0 <= profit_margin <= 2):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Profit margin must be between 0 and 2 (0-200%)"
            )

        # Validate quantity mode
        if quantity_mode is not None and quantity_mode not in ['add', 'replace']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Quantity mode must be 'add' or 'replace'"
            )

        return service.update_invoice_config(
            invoice_id=invoice_id,
            profit_margin=profit_margin,
            apply_iva=apply_iva,
            quantity_mode=quantity_mode,
            user=current_user
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating invoice config: {str(e)}"
        )


@router.post("/pending/{invoice_id}/sync", response_model=InvoiceSyncResponse)
def sync_invoice_to_odoo(
    invoice_id: int,
    request: InvoiceSyncRequest,
    manager: OdooConnectionManager = Depends(get_odoo_manager),
    db: Session = Depends(get_db),
    current_user: UserInfo = Depends(require_admin)
):
    """
    Sync invoice to Odoo (admin only).

    **Requires:** Admin role

    **Supports partial sync:** Optionally provide `item_ids` to sync only specific items.

    Synchronizes invoice items to Odoo inventory:
    - Searches products by barcode
    - Creates/updates products with calculated prices (cost + margin + IVA)
    - Updates stock quantities (add or replace mode)
    - Creates history record with results
    - Changes invoice status:
      - SINCRONIZADA if all items synced
      - PARCIALMENTE_SINCRONIZADA if some items synced

    Invoice must be in CORREGIDA or PARCIALMENTE_SINCRONIZADA status.
    """
    try:
        odoo_client = manager.get_principal_client()
        service = FacturaService(db=db, odoo_client=odoo_client)
        result = service.sync_invoice_to_odoo(
            invoice_id=invoice_id,
            user=current_user,
            notes=request.notes,
            item_ids=request.item_ids
        )

        return result

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        import traceback
        print(f"ERROR IN SYNC: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error syncing invoice: {str(e)}"
        )


@router.get("/history", response_model=InvoiceHistoryListResponse)
def get_invoice_history(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: UserInfo = Depends(require_admin)
):
    """
    Get invoice processing history (admin only).

    **Requires:** Admin role

    Returns historical records of all synced invoices with:
    - Sync results (successful/failed items)
    - Error details for failed items
    - Modification tracking
    """
    try:
        service = FacturaService(db=db)
        result = service.get_invoice_history(skip=skip, limit=limit)

        return result

    except Exception as e:
        import traceback
        print(f"ERROR IN HISTORY: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching history: {str(e)}"
        )


@router.get("/pending/{invoice_id}/xml")
def download_invoice_xml(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: UserInfo = Depends(require_admin)
):
    """
    Download original XML file (admin only).

    **Requires:** Admin role

    Returns the original XML content as uploaded from SRI.
    """
    try:
        from app.models import PendingInvoice

        invoice = db.query(PendingInvoice).filter(PendingInvoice.id == invoice_id).first()

        if not invoice:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Invoice {invoice_id} not found"
            )

        filename = invoice.xml_filename or f"invoice_{invoice_id}.xml"

        return Response(
            content=invoice.xml_content.encode('utf-8'),
            media_type="application/xml",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error downloading XML: {str(e)}"
        )


@router.delete("/pending/{invoice_id}")
def delete_pending_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: UserInfo = Depends(require_admin)
):
    """
    Delete a pending invoice (admin only).

    **Requires:** Admin role

    Deletes the invoice and all associated items.
    Cannot delete invoices that have already been synced to Odoo.
    """
    try:
        from app.models import PendingInvoice

        invoice = db.query(PendingInvoice).filter(PendingInvoice.id == invoice_id).first()

        if not invoice:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Invoice {invoice_id} not found"
            )

        # Prevent deletion of synced invoices
        if invoice.status == 'sincronizada':
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete synced invoices. They are already in Odoo."
            )

        # Delete the invoice (cascade will delete items)
        db.delete(invoice)
        db.commit()

        return {
            "success": True,
            "message": f"Invoice {invoice.invoice_number or invoice_id} deleted successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting invoice: {str(e)}"
        )


# ============================================================================
# LEGACY EXCEL-BASED WORKFLOW ENDPOINTS (DEPRECATED)
# ============================================================================

@router.post("/extract-products", response_model=ExtractProductsResponse, deprecated=True)
async def extract_products(
    xml_files: List[UploadFile] = File(...),
    current_user: UserInfo = Depends(require_admin)
):
    """
    [DEPRECATED] Extract products from multiple XML factura files.

    **Requires:** Admin role

    **This endpoint is deprecated.** Use the new /upload workflow instead.

    Uploads multiple XML files and extracts unique products.
    Returns product list and stores unified XML for later use.
    """
    try:
        # Read all XML files
        xml_data_list = []
        for xml_file in xml_files:
            content = await xml_file.read()
            xml_data_list.append({
                'filename': xml_file.filename,
                'content': content.decode('utf-8')
            })

        # Extract productos
        service = FacturaService()
        productos, unified_xml = service.extract_productos_from_xmls(xml_data_list)

        # Store unified_xml in memory (in production, use database or temp storage)
        # For now, we'll return it as metadata in response
        # Client will need to download it separately

        return ExtractProductsResponse(
            success=True,
            productos=productos,
            total_facturas=len(xml_files),
            total_productos=len(productos),
            message=f"Se procesaron {len(xml_files)} facturas y se encontraron {len(productos)} productos únicos"
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error procesando XMLs: {str(e)}"
        )


@router.post("/generate-excel", deprecated=True)
async def generate_excel(
    xml_files: List[UploadFile] = File(...),
    current_user: UserInfo = Depends(require_admin)
):
    """
    [DEPRECATED] Generate Excel file with products from XMLs.

    **Requires:** Admin role

    **This endpoint is deprecated.** Use the new /upload workflow instead.

    Processes XMLs and returns Excel file ready for download.
    """
    try:
        # Read all XML files
        xml_data_list = []
        for xml_file in xml_files:
            content = await xml_file.read()
            xml_data_list.append({
                'filename': xml_file.filename,
                'content': content.decode('utf-8')
            })

        # Extract productos and generate Excel
        service = FacturaService()
        productos, _ = service.extract_productos_from_xmls(xml_data_list)
        excel_bytes = service.generate_excel(productos)

        # Return Excel file
        return Response(
            content=excel_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": "attachment; filename=productos_unificados.xlsx"
            }
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generando Excel: {str(e)}"
        )


@router.post("/generate-unified-xml", deprecated=True)
async def generate_unified_xml(
    xml_files: List[UploadFile] = File(...),
    current_user: UserInfo = Depends(require_admin)
):
    """
    [DEPRECATED] Generate unified XML from multiple factura XMLs.

    **Requires:** Admin role

    **This endpoint is deprecated.** Use the new /upload workflow instead.

    Returns a single unified XML file containing all facturas.
    """
    try:
        # Read all XML files
        xml_data_list = []
        for xml_file in xml_files:
            content = await xml_file.read()
            xml_data_list.append({
                'filename': xml_file.filename,
                'content': content.decode('utf-8')
            })

        # Generate unified XML
        service = FacturaService()
        _, unified_xml = service.extract_productos_from_xmls(xml_data_list)

        # Return XML file
        return Response(
            content=unified_xml.encode('utf-8'),
            media_type="application/xml",
            headers={
                "Content-Disposition": "attachment; filename=facturas_unificadas.xml"
            }
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generando XML unificado: {str(e)}"
        )


@router.post("/update-xmls", deprecated=True)
async def update_xmls_with_barcodes(
    excel_file: UploadFile = File(...),
    unified_xml_file: UploadFile = File(...),
    current_user: UserInfo = Depends(require_admin)
):
    """
    [DEPRECATED] Update XMLs with barcodes from Excel file.

    **Requires:** Admin role

    **This endpoint is deprecated.** Use the new /upload workflow instead.

    Uploads Excel with barcodes and unified XML.
    - If there's only 1 XML, returns it directly as XML file
    - If there are multiple XMLs, returns them as a ZIP file containing all updated XMLs
    """
    try:
        import logging
        import traceback
        logger = logging.getLogger(__name__)

        logger.info("Starting XML update process")

        # Read Excel file
        excel_content = await excel_file.read()
        logger.info(f"Excel file size: {len(excel_content)} bytes")

        workbook = openpyxl.load_workbook(io.BytesIO(excel_content))
        sheet = workbook.active
        logger.info(f"Excel loaded, sheet: {sheet.title}")

        # Convert to list of lists
        excel_data = []
        for row in sheet.iter_rows(values_only=True):
            excel_data.append(list(row))

        logger.info(f"Excel rows parsed: {len(excel_data)}")

        # Read unified XML
        unified_xml_content = await unified_xml_file.read()
        unified_xml = unified_xml_content.decode('utf-8')
        logger.info(f"Unified XML size: {len(unified_xml)} chars")

        # Update XMLs
        service = FacturaService()
        logger.info("Calling update_xmls_with_barcodes")
        updated_xmls = service.update_xmls_with_barcodes(unified_xml, excel_data)
        logger.info(f"Updated XMLs generated: {len(updated_xmls)}")

        # Validate we have updated XMLs
        if not updated_xmls:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No se pudieron generar XMLs actualizados"
            )

        # If only one XML, return it directly
        if len(updated_xmls) == 1:
            first_xml = updated_xmls[0]
            logger.info(f"Returning single XML: {first_xml['filename']}")
            return Response(
                content=first_xml['content'].encode('utf-8'),
                media_type="application/xml",
                headers={
                    "Content-Disposition": f"attachment; filename={first_xml['filename']}"
                }
            )

        # Multiple XMLs: create ZIP file
        logger.info(f"Creating ZIP with {len(updated_xmls)} XMLs")
        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for xml_data in updated_xmls:
                filename = xml_data['filename']
                content = xml_data['content']
                logger.info(f"Adding to ZIP: {filename}")
                zip_file.writestr(filename, content.encode('utf-8'))

        zip_buffer.seek(0)
        logger.info("ZIP created successfully")

        return Response(
            content=zip_buffer.getvalue(),
            media_type="application/zip",
            headers={
                "Content-Disposition": "attachment; filename=facturas_actualizadas.zip"
            }
        )

    except Exception as e:
        import logging
        import traceback
        logger = logging.getLogger(__name__)
        logger.error(f"Error in update_xmls: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error actualizando XMLs: {str(e)}"
        )
