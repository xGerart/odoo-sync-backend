"""
Product management endpoints.
"""
from fastapi import APIRouter, Depends, File, UploadFile, Form, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.core.database import get_db
from app.infrastructure.odoo import get_odoo_manager, OdooConnectionManager
from app.schemas.product import (
    ProductInput,
    ProductResponse,
    SyncResponse,
    SyncRequest,
    XMLParseResponse,
    InconsistencyResponse
)
from app.schemas.common import MessageResponse
from app.schemas.auth import UserInfo
from app.features.auth.dependencies import (
    get_current_user,
    require_admin,
    require_admin_or_bodeguero
)
from app.features.products.service import ProductService
from app.features.products.xml_parser import XMLInvoiceParser
from app.core.constants import XMLProvider, QuantityMode
from app.core.exceptions import ValidationError
from app.utils.validators import validate_xml_file


router = APIRouter(prefix="/products", tags=["Products"])


@router.post("/upload-xml")
async def upload_xml(
    file: UploadFile = File(...),
    provider: str = Form(default="D'Mujeres"),
    profit_margin: float = Form(default=0.50),
    quantity_mode: str = Form(default="replace"),
    apply_iva: bool = Form(default=True),
    current_user: UserInfo = Depends(require_admin_or_bodeguero)
):
    """
    Upload and parse XML invoice file.

    **Requires:** Admin or Bodeguero role

    - **file**: XML file from supplier
    - **provider**: XML provider type (D'Mujeres, LANSEY, generic)
    - **profit_margin**: Profit margin to apply (0-1, default 0.50 = 50%)
    - **quantity_mode**: 'replace' or 'add' for stock quantities
    - **apply_iva**: Whether to calculate display price with IVA

    Returns parsed and mapped product list ready for sync.
    """
    import logging
    logger = logging.getLogger(__name__)

    logger.info(f"=== XML UPLOAD DEBUG ===")
    logger.info(f"Filename: {file.filename}")
    logger.info(f"Provider received: {provider}")
    logger.info(f"Profit margin: {profit_margin}")
    logger.info(f"Quantity mode: {quantity_mode}")

    # Validate file
    is_valid, error_msg = validate_xml_file(file.filename)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg
        )

    try:
        # Read file content
        content = await file.read()
        xml_content = content.decode('utf-8')

        logger.info(f"XML content length: {len(xml_content)} chars")
        logger.info(f"First 500 chars: {xml_content[:500]}")

        # Parse provider
        try:
            provider_enum = XMLProvider(provider)
            logger.info(f"Provider enum: {provider_enum.value}")
        except ValueError:
            provider_enum = XMLProvider.GENERIC
            logger.warning(f"Invalid provider '{provider}', using GENERIC")

        # Parse XML
        parser = XMLInvoiceParser()
        result = parser.parse_xml_file(xml_content, provider_enum)

        logger.info(f"Products parsed: {len(result.products)}")
        if result.products:
            product_details = [{'codigo': p.codigo_auxiliar, 'desc': p.descripcion[:30]} for p in result.products[:3]]
            logger.info(f"Product details: {product_details}")

        # Map to Odoo format with calculated prices
        mapped_products = parser.map_to_odoo_format(
            products=result.products,
            profit_margin=profit_margin,
            quantity_mode=quantity_mode,
            apply_iva=apply_iva
        )

        logger.info(f"Products mapped: {len(mapped_products)}")
        if mapped_products:
            mapped_details = [{
                'barcode': p['barcode'],
                'name': p['name'][:30],
                'cost': p['standard_price'],
                'sale': p['list_price'],
                'display': p.get('display_price')
            } for p in mapped_products[:3]]
            logger.info(f"Mapped product details: {mapped_details}")

        # Return response with mapped products
        return {
            "products": mapped_products,
            "total_found": len(mapped_products),
            "provider": provider_enum.value
        }

    except Exception as e:
        logger.error(f"Error parsing XML: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to parse XML: {str(e)}"
        )


@router.post("/sync", response_model=SyncResponse)
async def sync_products(
    request: SyncRequest,
    manager: OdooConnectionManager = Depends(get_odoo_manager),
    db: Session = Depends(get_db),
    current_user: UserInfo = Depends(require_admin_or_bodeguero)
):
    """
    Sync products to Odoo (bulk operation).

    **Requires:** Admin or Bodeguero role

    - **products**: List of mapped products
    - **profit_margin**: Profit margin to apply (0-1, default 0.50 = 50%)
    - **quantity_mode**: 'replace' or 'add' for stock quantities

    Creates or updates products in Odoo.
    """
    import logging
    logger = logging.getLogger(__name__)

    try:
        logger.info("=== SYNC PRODUCTS DEBUG ===")
        logger.info(f"Number of products: {len(request.products)}")
        logger.info(f"Profit margin: {request.profit_margin}")
        logger.info(f"Quantity mode: {request.quantity_mode}")

        if request.products:
            logger.info(f"First product sample: {request.products[0]}")
            logger.info(f"Product keys: {request.products[0].keys() if request.products[0] else 'N/A'}")

        client = manager.get_principal_client()
        service = ProductService(client, db)

        # Apply profit margin if needed
        parser = XMLInvoiceParser()

        # Validate quantity mode
        try:
            mode = QuantityMode(request.quantity_mode)
        except ValueError:
            mode = QuantityMode.REPLACE

        # Sync products
        result = service.sync_products_bulk(request.products, username=current_user.username)

        return result

    except Exception as e:
        logger.error(f"Sync error: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Sync failed: {str(e)}"
        )


@router.post("/", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
def create_product(
    product: ProductInput,
    manager: OdooConnectionManager = Depends(get_odoo_manager),
    db: Session = Depends(get_db),
    current_user: UserInfo = Depends(require_admin)
):
    """
    Create a new product manually.

    **Requires:** Admin role only

    - **name**: Product name
    - **barcode**: Product barcode/SKU
    - **standard_price**: Cost price
    - **list_price**: Sale price (without IVA)
    - **qty_available**: Initial stock quantity
    - **quantity_mode**: 'replace' or 'add'

    Returns created product details.
    """
    try:
        client = manager.get_principal_client()
        service = ProductService(client, db)

        result = service.create_product(product)

        if not result.success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.message
            )

        # Fetch created product details
        product_response = service.search_product_by_barcode(product.barcode)

        if not product_response:
            # Fallback response
            from app.utils.formatters import calculate_price_with_iva
            product_response = ProductResponse(
                id=result.product_id,
                name=product.name,
                barcode=product.barcode,
                qty_available=product.qty_available,
                standard_price=product.standard_price,
                list_price=product.list_price,
                display_price=calculate_price_with_iva(product.list_price),
                tracking="none",
                available_in_pos=True
            )

        return product_response

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create product: {str(e)}"
        )


@router.get("/search/{barcode}", response_model=ProductResponse)
@router.get("/barcode/{barcode}", response_model=ProductResponse)
def search_product(
    barcode: str,
    manager: OdooConnectionManager = Depends(get_odoo_manager),
    db: Session = Depends(get_db),
    current_user: UserInfo = Depends(get_current_user)
):
    """
    Search for a product by barcode.

    **Requires:** Any authenticated user

    - **barcode**: Product barcode/SKU

    Returns product details if found.
    """
    import logging
    logger = logging.getLogger(__name__)
    from app.core.exceptions import ValidationError, OdooOperationError, OdooConnectionError

    try:
        logger.info(f"[SEARCH] Searching for barcode: {barcode}")
        logger.info(f"[SEARCH] User: {current_user.username}, Role: {current_user.role}")

        logger.info("[SEARCH] Getting principal client...")
        client = manager.get_principal_client()
        logger.info(f"[SEARCH] Got client, authenticated: {client.is_authenticated()}")

        logger.info("[SEARCH] Creating ProductService...")
        service = ProductService(client, db)
        logger.info("[SEARCH] ProductService created")

        product = service.search_product_by_barcode(barcode)

        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product with barcode '{barcode}' not found"
            )

        return product

    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except OdooConnectionError as e:
        # Check if it's a session expiry or just no connection
        if e.is_session_expired:
            # Admin's Odoo session expired
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Sesión Odoo expirada. Por favor, cierra sesión y vuelve a iniciar sesión."
            )
        else:
            # No Odoo connection established yet (bodeguero/cajero users)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(e) or "No hay conexión a Odoo. Un administrador debe iniciar sesión primero."
            )
    except OdooOperationError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Odoo operation failed: {str(e)}"
        )
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"Unexpected error in search_product: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {str(e)}"
        )


@router.get("/", response_model=List[ProductResponse])
def list_products(
    limit: int = 100,
    manager: OdooConnectionManager = Depends(get_odoo_manager),
    db: Session = Depends(get_db),
    current_user: UserInfo = Depends(get_current_user)
):
    """
    List all products.

    **Requires:** Any authenticated user

    - **limit**: Maximum number of products to return (default 100, max 1000)

    Returns list of products.
    """
    if limit > 1000:
        limit = 1000

    try:
        client = manager.get_principal_client()
        service = ProductService(client, db)

        products = service.get_all_products(limit=limit)

        return products

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list products: {str(e)}"
        )


@router.patch("/{product_id}", response_model=MessageResponse)
def update_product(
    product_id: int,
    product: ProductInput,
    manager: OdooConnectionManager = Depends(get_odoo_manager),
    db: Session = Depends(get_db),
    current_user: UserInfo = Depends(require_admin)
):
    """
    Update an existing product.

    **Requires:** Admin role only

    - **product_id**: Product ID to update
    - Product fields to update

    Returns success message.
    """
    try:
        client = manager.get_principal_client()
        service = ProductService(client, db)

        result = service.update_product(product_id, product)

        if not result.success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.message
            )

        return MessageResponse(
            message=result.message,
            success=True
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Update failed: {str(e)}"
        )
