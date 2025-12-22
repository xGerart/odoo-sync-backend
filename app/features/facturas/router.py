"""
Factura processing endpoints.
"""
from typing import List, Optional
from fastapi import APIRouter, File, UploadFile, HTTPException, status, Depends
from fastapi.responses import Response, StreamingResponse
import io
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
    InvoiceSubmitRequest,
    InvoiceSyncRequest,
    PendingInvoiceListResponse,
    PendingInvoiceResponse,
    InvoiceUploadResponse,
    InvoiceSyncResponse,
    InvoiceHistoryListResponse
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
    db: Session = Depends(get_db),
    current_user: UserInfo = Depends(require_admin)
):
    """
    Upload XML invoices from SRI and create pending invoices.

    **Requires:** Admin role

    Parses XML files, extracts invoice metadata and items,
    and saves them to database for bodeguero review.
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

        # Create pending invoices (no Odoo client needed for upload)
        service = FacturaService(db=db)
        result = service.upload_and_create_pending_invoices(xml_data_list, current_user)

        return result

    except Exception as e:
        import traceback
        print(f"ERROR uploading invoices: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error uploading invoices: {str(e)}"
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

    Synchronizes invoice items to Odoo inventory:
    - Searches products by barcode
    - Updates stock quantities
    - Creates history record with results
    - Changes invoice status to SINCRONIZADA

    Invoice must be in CORREGIDA status.
    """
    try:
        odoo_client = manager.get_client()
        service = FacturaService(db=db, odoo_client=odoo_client)
        result = service.sync_invoice_to_odoo(invoice_id, current_user, request.notes)

        return result

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
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

    Uploads Excel with barcodes and unified XML, returns updated XMLs as ZIP.
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

        # For now, return first updated XML (in production, return ZIP with all files)
        if not updated_xmls:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No se pudieron generar XMLs actualizados"
            )

        # Return first XML as example (TODO: return ZIP with all files)
        first_xml = updated_xmls[0]
        logger.info(f"Returning XML: {first_xml['filename']}")
        return Response(
            content=first_xml['content'].encode('utf-8'),
            media_type="application/xml",
            headers={
                "Content-Disposition": f"attachment; filename={first_xml['filename']}"
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
