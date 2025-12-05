"""
Factura processing endpoints.
"""
from typing import List
from fastapi import APIRouter, File, UploadFile, HTTPException, status, Depends
from fastapi.responses import Response, StreamingResponse
import io
import openpyxl

from app.schemas.auth import UserInfo
from app.features.auth.dependencies import require_admin
from .service import FacturaService
from .schemas import ExtractProductsResponse


router = APIRouter(prefix="/facturas", tags=["Facturas"])


@router.post("/extract-products", response_model=ExtractProductsResponse)
async def extract_products(
    xml_files: List[UploadFile] = File(...),
    current_user: UserInfo = Depends(require_admin)
):
    """
    Extract products from multiple XML factura files.

    **Requires:** Admin role

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


@router.post("/generate-excel")
async def generate_excel(
    xml_files: List[UploadFile] = File(...),
    current_user: UserInfo = Depends(require_admin)
):
    """
    Generate Excel file with products from XMLs.

    **Requires:** Admin role

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


@router.post("/generate-unified-xml")
async def generate_unified_xml(
    xml_files: List[UploadFile] = File(...),
    current_user: UserInfo = Depends(require_admin)
):
    """
    Generate unified XML from multiple factura XMLs.

    **Requires:** Admin role

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


@router.post("/update-xmls")
async def update_xmls_with_barcodes(
    excel_file: UploadFile = File(...),
    unified_xml_file: UploadFile = File(...),
    current_user: UserInfo = Depends(require_admin)
):
    """
    Update XMLs with barcodes from Excel file.

    **Requires:** Admin role

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
