from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
from typing import List, Optional
import logging
import json
import asyncio

from models import (
    OdooConfig, ProductMapped, ProductInput, SyncResponse,
    XMLParseResponse, OdooConnectionTest, ErrorResponse, SyncResult, CierreCajaResponse,
    TransferRequest, TransferResponse, ConfirmTransferRequest,
    PriceInconsistency, InconsistenciesResponse, FixInconsistenciesRequest, FixInconsistenciesResponse
)
from odoo_client import OdooClient
from xml_parser import XMLInvoiceParser

# Configure logging with more detailed format
import os
import sys

# Use environment variable to detect production
IS_PRODUCTION = os.getenv('RENDER', False)

if IS_PRODUCTION:
    # In production (Render), only log to console
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )
else:
    # In development, log to both console and file
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('sync_logs.log', encoding='utf-8')
        ]
    )

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Odoo Product Sync API",
    description="API for synchronizing XML invoice products with Odoo",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://odoo-sync-frontend.vercel.app",
        "https://*.vercel.app"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global parser instance
xml_parser = XMLInvoiceParser()

# Global Odoo client (will be set after connection test)
odoo_client: Optional[OdooClient] = None

# Global branch Odoo client for dual authentication
branch_client: Optional[OdooClient] = None


@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "Odoo Product Sync API", "version": "1.0.0"}


@app.post("/test-connection", response_model=OdooConnectionTest)
async def test_odoo_connection(config: OdooConfig):
    """Test connection to principal Odoo server"""
    global odoo_client
    
    try:
        # Create client instance
        client = OdooClient(config)
        
        # Test authentication
        result = client.authenticate()
        
        # If successful, store the client for future use
        if result.success:
            odoo_client = client
            logger.info(f"Successfully connected to principal Odoo as user ID: {result.user_id}")
        else:
            logger.warning(f"Principal Odoo connection failed: {result.message}")
        
        return result
        
    except Exception as e:
        logger.error(f"Error testing principal Odoo connection: {e}")
        return OdooConnectionTest(
            success=False,
            message=f"Connection error: {str(e)}"
        )


@app.post("/test-branch-connection", response_model=OdooConnectionTest)
async def test_branch_odoo_connection(config: OdooConfig):
    """Test connection to branch Odoo server"""
    global branch_client
    
    try:
        # Create client instance for branch
        client = OdooClient(config)
        
        # Test authentication
        result = client.authenticate()
        
        # If successful, store the branch client for future use
        if result.success:
            branch_client = client
            logger.info(f"Successfully connected to branch Odoo as user ID: {result.user_id}")
        else:
            logger.warning(f"Branch Odoo connection failed: {result.message}")
        
        return result
        
    except Exception as e:
        logger.error(f"Error testing branch Odoo connection: {e}")
        return OdooConnectionTest(
            success=False,
            message=f"Branch connection error: {str(e)}"
        )


@app.post("/upload-xml", response_model=XMLParseResponse)
async def upload_xml_invoice(file: UploadFile = File(...), provider: str = "D'Mujeres"):
    """Upload and parse XML invoice file"""
    try:
        # Validate file type
        if not file.filename.lower().endswith('.xml'):
            raise HTTPException(
                status_code=400, 
                detail="Only XML files are supported"
            )
        
        # Read file content
        xml_content = await file.read()
        xml_string = xml_content.decode('utf-8')
        
        # Parse XML using specified provider
        result = xml_parser.parse_xml_file(xml_string, provider)
        
        logger.info(f"Successfully parsed XML file: {file.filename} using {provider} provider, found {result.total_found} products")
        return result
        
    except Exception as e:
        logger.error(f"Error parsing XML file {file.filename}: {e}")
        raise HTTPException(
            status_code=400,
            detail=f"Error parsing XML file: {str(e)}"
        )


@app.post("/sync-products", response_model=SyncResponse)
async def sync_products_to_odoo(products: List[ProductMapped]):
    """Synchronize products to Odoo"""
    global odoo_client
    
    # Check if Odoo client is configured
    if not odoo_client:
        raise HTTPException(
            status_code=400,
            detail="Odoo connection not established. Please test connection first."
        )
    
    try:
        # Sync products and get PDF path
        results, pdf_path = odoo_client.sync_products_with_pdf(products)

        # Calculate statistics
        created_count = sum(1 for r in results if r.success and r.action == "created")
        updated_count = sum(1 for r in results if r.success and r.action == "updated")
        errors_count = sum(1 for r in results if not r.success)

        # Enhanced logging with error details
        logger.info(f"Sync completed: {created_count} created, {updated_count} updated, {errors_count} errors")

        # Log detailed information about errors
        if errors_count > 0:
            logger.warning(f"\n\u274c SYNC ERRORS DETECTED ({errors_count} total):")
            for i, result in enumerate(results):
                if not result.success:
                    logger.warning(f"  • Error {i+1}: {result.message}")
                    print(f"\u274c Error {i+1}: {result.message}")

        # Log successful operations
        if created_count > 0 or updated_count > 0:
            logger.info(f"\n\u2705 SUCCESSFUL OPERATIONS:")
            for i, result in enumerate(results):
                if result.success:
                    logger.info(f"  • {result.action.title()}: {result.message}")
                    print(f"\u2705 {result.action.title()}: {result.message}")
        
        # Store PDF filename for download
        import os
        pdf_filename = os.path.basename(pdf_path) if pdf_path and os.path.exists(pdf_path) else None

        response = SyncResponse(
            results=results,
            total_processed=len(results),
            created_count=created_count,
            updated_count=updated_count,
            errors_count=errors_count,
            pdf_filename=pdf_filename
        )

        if pdf_filename:
            logger.info(f"📋 PDF report available: {pdf_filename}")

        return response
        
    except Exception as e:
        logger.error(f"Error syncing products: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error syncing products: {str(e)}"
        )


@app.get("/download-pdf/{filename}")
async def download_pdf(filename: str):
    """Download PDF report file"""
    import os

    # Security: only allow files from reports directory with specific patterns
    allowed_prefixes = ["stock_report_", "transfer_admin_report_"]
    if not any(filename.startswith(prefix) for prefix in allowed_prefixes) or not filename.endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Invalid PDF filename"
        )

    reports_dir = os.path.join(os.path.dirname(__file__), 'reports')
    file_path = os.path.join(reports_dir, filename)

    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=404,
            detail="PDF file not found"
        )

    # Verify the file is a valid PDF by checking its first few bytes
    try:
        with open(file_path, 'rb') as f:
            header = f.read(5)
            if not header.startswith(b'%PDF-'):
                raise HTTPException(
                    status_code=500,
                    detail="Corrupted PDF file detected"
                )
    except Exception as e:
        logger.error(f"Error validating PDF file {filename}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Error accessing PDF file"
        )

    return FileResponse(
        path=file_path,
        filename=filename,
        media_type='application/pdf',
        headers={
            "Content-Disposition": f"attachment; filename=\"{filename}\"",
            "Content-Type": "application/pdf",
            "Content-Transfer-Encoding": "binary",
            "Accept-Ranges": "bytes"
        }
    )


@app.post("/fix-tracking-products", response_model=SyncResponse)
async def fix_products_tracking_issues(products: List[ProductMapped]):
    """
    Corrige productos que tienen problemas de rastreo de inventario.
    Archiva el producto original y crea uno nuevo con rastreo activado.
    """
    global odoo_client

    # Check if Odoo client is configured
    if not odoo_client:
        raise HTTPException(
            status_code=400,
            detail="Odoo connection not established. Please test connection first."
        )

    try:
        # Fix tracking issues
        results = odoo_client.fix_tracking_products(products)

        # Calculate statistics
        fixed_count = sum(1 for r in results if r.success and r.action == "tracking_fix_success")
        failed_count = sum(1 for r in results if not r.success)

        logger.info(f"Tracking fix completed: {fixed_count} fixed, {failed_count} failed")

        return SyncResponse(
            results=results,
            total_processed=len(results),
            created_count=fixed_count,  # Los productos "fijados" son técnicamente nuevos productos
            updated_count=0,  # No actualizamos productos existentes
            errors_count=failed_count
        )

    except Exception as e:
        logger.error(f"Error fixing tracking issues: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error fixing tracking issues: {str(e)}"
        )


@app.post("/create-product", response_model=SyncResult)
async def create_single_product(product: ProductInput):
    """Create a single product manually"""
    global odoo_client
    
    # Check if Odoo client is configured
    if not odoo_client:
        raise HTTPException(
            status_code=400,
            detail="Odoo connection not established. Please test connection first."
        )
    
    try:
        # Convert ProductInput to ProductMapped
        # If display_price is provided, calculate list_price without IVA
        if product.display_price:
            list_price_without_iva = product.display_price / 1.15
        else:
            list_price_without_iva = product.list_price
            
        mapped_product = ProductMapped(
            name=product.name,
            qty_available=product.qty_available,
            barcode=product.barcode,
            standard_price=product.standard_price,
            list_price=round(list_price_without_iva, 8),
            display_price=product.display_price or (product.list_price * 1.15),
            type='storable',
            tracking='none',
            available_in_pos=True
        )
        
        # Add quantity mode for stock updates
        mapped_product.quantity_mode = product.quantity_mode
        
        # Sync the product
        result = odoo_client.sync_product(mapped_product)
        
        logger.info(f"Manual product sync result: {result.message}")
        return result
        
    except Exception as e:
        logger.error(f"Error creating product manually: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error creating product: {str(e)}"
        )


@app.post("/parse-transfer-xml")
async def parse_transfer_xml(file: UploadFile = File(...)):
    """Parse transfer XML file generated in step 1"""
    try:
        # Validate file type
        if not file.filename.lower().endswith('.xml'):
            raise HTTPException(
                status_code=400, 
                detail="Only XML files are supported"
            )
        
        # Read and parse XML
        xml_content = await file.read()
        xml_string = xml_content.decode('utf-8')
        
        # Parse transfer XML to extract products
        products = xml_parser.parse_transfer_xml(xml_string)
        
        logger.info(f"Parsed transfer XML: {file.filename}, found {len(products)} products")
        return {"products": products}
        
    except Exception as e:
        logger.error(f"Error parsing transfer XML: {e}")
        raise HTTPException(
            status_code=400,
            detail=f"Error processing transfer XML file: {str(e)}"
        )


@app.post("/parse-and-map")
async def parse_and_map_xml(file: UploadFile = File(...), profit_margin: float = 50.0, iva_rate: float = 15.0, provider: str = "D'Mujeres"):
    """Parse XML and return mapped products ready for sync"""
    try:
        # Validate file type
        if not file.filename.lower().endswith('.xml'):
            raise HTTPException(
                status_code=400, 
                detail="Only XML files are supported"
            )
        
        # Read and parse XML
        xml_content = await file.read()
        xml_string = xml_content.decode('utf-8')
        
        # Parse XML to get ProductData list using specified provider
        parse_result = xml_parser.parse_xml_file(xml_string, provider)
        
        # Map to Odoo format with profit margin and IVA calculation
        mapped_products = xml_parser.map_to_odoo_format(parse_result.products, profit_margin, iva_rate)
        
        logger.info(f"Parsed and mapped {len(mapped_products)} products from {file.filename} using {provider} provider with {profit_margin}% margin and {iva_rate}% IVA")
        return mapped_products
        
    except Exception as e:
        logger.error(f"Error parsing and mapping XML: {e}")
        raise HTTPException(
            status_code=400,
            detail=f"Error processing XML file: {str(e)}"
        )


@app.get("/search-product/{barcode}")
async def search_product_by_barcode(barcode: str):
    """Search for an existing product by barcode"""
    global odoo_client
    
    if not odoo_client:
        raise HTTPException(
            status_code=400,
            detail="Odoo connection not established. Please test connection first."
        )
    
    try:
        # Search for product by barcode
        product_id = odoo_client.search_product_by_barcode(barcode)
        
        if not product_id:
            return {"found": False, "message": "Producto no encontrado"}
        
        # Get product details
        product_details = odoo_client.get_product_details(product_id)
        
        if not product_details:
            return {"found": False, "message": "Error al obtener detalles del producto"}
        
        # Format response with current data
        response_data = {
            "found": True,
            "product_id": product_id,
            "name": product_details.get('name', ''),
            "barcode": product_details.get('barcode', ''),
            "standard_price": product_details.get('standard_price', 0),
            "list_price": product_details.get('list_price', 0),
            "qty_available": product_details.get('qty_available', 0),
            "tracking": product_details.get('tracking', 'none'),
            "available_in_pos": product_details.get('available_in_pos', True)
        }
        
        # Calculate display price with IVA
        if response_data['list_price']:
            response_data['display_price'] = round(response_data['list_price'] * 1.15, 2)
        else:
            response_data['display_price'] = 0
        
        logger.info(f"Found existing product: {product_details.get('name')} (ID: {product_id})")
        return response_data
        
    except Exception as e:
        logger.error(f"Error searching product by barcode {barcode}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error searching product: {str(e)}"
        )


@app.get("/cierre-caja/{date}", response_model=CierreCajaResponse)
async def get_cierre_caja(date: str):
    """Get sales data for cash register closing"""
    global odoo_client
    
    if not odoo_client:
        raise HTTPException(
            status_code=400,
            detail="Odoo connection not established. Please test connection first."
        )
    
    try:
        # Validate date format
        from datetime import datetime
        try:
            datetime.strptime(date, '%Y-%m-%d')
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid date format. Use YYYY-MM-DD"
            )
        
        # Get sales data from Odoo
        sales_data = odoo_client.get_sales_data_by_date(date)
        
        logger.info(f"Retrieved sales data for {date}: {sales_data.total_sales} total sales")
        return sales_data
        
    except Exception as e:
        logger.error(f"Error getting sales data for {date}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving sales data: {str(e)}"
        )


@app.post("/process-transfer", response_model=TransferResponse)
async def process_branch_transfer(transfer_request: TransferRequest):
    """Prepare branch transfer - generate XML and PDF for verification (NO inventory reduction)"""
    global odoo_client
    
    if not odoo_client:
        raise HTTPException(
            status_code=400,
            detail="Odoo connection not established. Please test connection first."
        )
    
    try:
        # Convert transfer request to format expected by OdooClient
        transfer_items = [
            {"barcode": item.barcode, "quantity": item.quantity}
            for item in transfer_request.products
        ]
        
        # Process the transfer
        result = odoo_client.process_branch_transfer(transfer_items)
        
        logger.info(f"Branch transfer processed: {result.processed_count} products transferred")
        return result
        
    except Exception as e:
        logger.error(f"Error processing branch transfer: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error processing transfer: {str(e)}"
        )


@app.post("/process-transfer-stream")
async def process_branch_transfer_stream(transfer_request: TransferRequest):
    """Process branch transfer with SSE progress updates"""
    global odoo_client

    if not odoo_client:
        raise HTTPException(
            status_code=400,
            detail="Odoo connection not established. Please test connection first."
        )

    async def generate_progress():
        try:
            # Convert transfer request to format expected by OdooClient
            transfer_items = [
                {"barcode": item.barcode, "quantity": item.quantity}
                for item in transfer_request.products
            ]

            total_items = len(transfer_items)
            processed_products = []

            # Send initial event
            yield f"data: {json.dumps({'type': 'start', 'total': total_items, 'progress': 0})}\n\n"

            # Process each product
            for index, item in enumerate(transfer_items):
                barcode = item['barcode']
                requested_quantity = item['quantity']

                # Send progress event
                progress_percent = int((index / total_items) * 70)  # 0-70% for processing products
                yield f"data: {json.dumps({'type': 'progress', 'current': index + 1, 'total': total_items, 'progress': progress_percent, 'message': f'Procesando producto {index + 1}/{total_items}'})}\n\n"

                # Search product by barcode
                product_id = odoo_client.search_product_by_barcode(barcode)
                if not product_id:
                    logger.warning(f"Product not found: {barcode}")
                    continue

                # Get product details
                product_details = odoo_client.get_product_details(product_id)
                if not product_details:
                    logger.warning(f"Could not get details for product: {barcode}")
                    continue

                # Validate stock availability
                available_stock = product_details.get('qty_available', 0)
                max_allowed = int(available_stock * 0.5)

                if requested_quantity > available_stock or requested_quantity > max_allowed:
                    logger.warning(f"Stock validation failed for {barcode}")
                    continue

                # Add to processed list
                processed_products.append({
                    'name': product_details['name'],
                    'barcode': barcode,
                    'quantity': requested_quantity,
                    'standard_price': product_details['standard_price'],
                    'list_price': product_details['list_price'],
                    'tracking': product_details.get('tracking', 'none'),
                    'available_in_pos': product_details.get('available_in_pos', True)
                })

            if not processed_products:
                yield f"data: {json.dumps({'type': 'error', 'message': 'No se pudieron procesar productos'})}\n\n"
                return

            # Generate XML
            yield f"data: {json.dumps({'type': 'progress', 'progress': 75, 'message': 'Generando archivo XML...'})}\n\n"
            xml_content = odoo_client._generate_transfer_xml(processed_products)

            # Generate PDF
            yield f"data: {json.dumps({'type': 'progress', 'progress': 85, 'message': 'Generando archivo PDF...'})}\n\n"
            pdf_content = odoo_client._generate_transfer_pdf(processed_products)

            # Complete
            yield f"data: {json.dumps({'type': 'progress', 'progress': 100, 'message': 'Proceso completado'})}\n\n"

            # Send final result
            result = {
                'type': 'complete',
                'success': True,
                'message': f'Transferencia preparada: {len(processed_products)} productos',
                'xml_content': xml_content,
                'pdf_content': pdf_content,
                'processed_count': len(processed_products),
                'inventory_reduced': False
            }
            yield f"data: {json.dumps(result)}\n\n"

        except Exception as e:
            logger.error(f"Error in transfer stream: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        generate_progress(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@app.post("/confirm-transfer", response_model=TransferResponse)
async def confirm_branch_transfer(transfer_request: ConfirmTransferRequest):
    """Confirm branch transfer - ACTUALLY reduce inventory after verification"""
    global odoo_client, branch_client
    
    if not odoo_client:
        raise HTTPException(
            status_code=400,
            detail="Principal Odoo connection not established. Please test connection first."
        )
    
    if not branch_client:
        raise HTTPException(
            status_code=400,
            detail="Branch Odoo connection not established. Please authenticate with branch first."
        )
    
    try:
        # Convert transfer request to format expected by OdooClient
        transfer_items = [
            {"barcode": item.barcode, "quantity": item.quantity}
            for item in transfer_request.products
        ]
        
        # Confirm the transfer using dual authentication (principal and branch)
        result = odoo_client.confirm_branch_transfer_with_dual_auth(transfer_items, branch_client)
        
        logger.info(f"Branch transfer CONFIRMED: {result.processed_count} products transferred, inventory reduced")
        return result
        
    except Exception as e:
        logger.error(f"Error confirming branch transfer: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error confirming transfer: {str(e)}"
        )


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "odoo_connected": odoo_client is not None and odoo_client.uid is not None
    }


@app.get("/detect-inconsistencies", response_model=InconsistenciesResponse)
async def detect_price_inconsistencies():
    """Detect price inconsistencies between principal and branch"""
    global odoo_client, branch_client

    if not odoo_client:
        raise HTTPException(
            status_code=400,
            detail="Principal Odoo connection not established. Please test connection first."
        )

    if not branch_client:
        raise HTTPException(
            status_code=400,
            detail="Branch Odoo connection not established. Please authenticate with branch first."
        )

    try:
        logger.info("Starting price inconsistency detection...")

        # Get products from principal
        principal_products = odoo_client.models.execute_kw(
            odoo_client.db, odoo_client.uid, odoo_client.password,
            'product.product', 'search_read',
            [
                [
                    ['active', '=', True],
                    ['available_in_pos', '=', True],
                    ['barcode', '!=', False],
                    ['barcode', '!=', '']
                ]
            ],
            {
                'fields': [
                    'id', 'name', 'barcode', 'list_price', 'standard_price', 'qty_available'
                ]
            }
        )

        # Get products from branch
        branch_products = branch_client.models.execute_kw(
            branch_client.db, branch_client.uid, branch_client.password,
            'product.product', 'search_read',
            [
                [
                    ['active', '=', True],
                    ['available_in_pos', '=', True],
                    ['barcode', '!=', False],
                    ['barcode', '!=', '']
                ]
            ],
            {
                'fields': [
                    'id', 'name', 'barcode', 'list_price', 'standard_price', 'qty_available'
                ]
            }
        )

        # Create dictionaries indexed by barcode
        principal_by_barcode = {
            p['barcode']: p for p in principal_products if p.get('barcode')
        }
        branch_by_barcode = {
            p['barcode']: p for p in branch_products if p.get('barcode')
        }

        # Find inconsistencies (only products with price differences, not missing products)
        inconsistencies = []
        price_tolerance = 0.01  # 1 centavo

        for barcode, principal_prod in principal_by_barcode.items():
            if barcode in branch_by_barcode:
                branch_prod = branch_by_barcode[barcode]

                list_price_diff = abs(principal_prod['list_price'] - branch_prod['list_price'])
                standard_price_diff = abs(principal_prod['standard_price'] - branch_prod['standard_price'])
                name_different = principal_prod['name'] != branch_prod['name']

                # Check if there are price differences or name differences
                if list_price_diff > price_tolerance or standard_price_diff > price_tolerance or name_different:
                    inconsistencies.append(PriceInconsistency(
                        barcode=barcode,
                        product_name=principal_prod['name'],
                        principal_id=principal_prod['id'],
                        sucursal_id=branch_prod['id'],
                        principal_list_price=principal_prod['list_price'],
                        sucursal_list_price=branch_prod['list_price'],
                        principal_standard_price=principal_prod['standard_price'],
                        sucursal_standard_price=branch_prod['standard_price'],
                        list_price_difference=list_price_diff,
                        standard_price_difference=standard_price_diff,
                        principal_stock=principal_prod['qty_available'],
                        sucursal_stock=branch_prod['qty_available']
                    ))

        logger.info(f"Found {len(inconsistencies)} price inconsistencies")

        return InconsistenciesResponse(
            success=True,
            message=f"Found {len(inconsistencies)} inconsistencies",
            total_inconsistencies=len(inconsistencies),
            inconsistencies=inconsistencies
        )

    except Exception as e:
        logger.error(f"Error detecting inconsistencies: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error detecting inconsistencies: {str(e)}"
        )


@app.post("/fix-inconsistencies", response_model=FixInconsistenciesResponse)
async def fix_price_inconsistencies(request: FixInconsistenciesRequest):
    """Fix price inconsistencies by updating branch products with principal prices"""
    global branch_client

    if not branch_client:
        raise HTTPException(
            status_code=400,
            detail="Branch Odoo connection not established. Please authenticate with branch first."
        )

    try:
        logger.info(f"Starting to fix {len(request.items)} inconsistencies...")

        results = []
        fixed_count = 0
        errors_count = 0

        for item in request.items:
            try:
                # Prepare update data
                update_data = {}

                if item.new_name is not None:
                    update_data['name'] = item.new_name

                if item.new_list_price is not None:
                    update_data['list_price'] = item.new_list_price

                if item.new_standard_price is not None:
                    update_data['standard_price'] = item.new_standard_price

                if not update_data:
                    results.append(SyncResult(
                        success=False,
                        message=f"No data to update for product {item.barcode}",
                        product_id=item.sucursal_id,
                        action="error",
                        barcode=item.barcode
                    ))
                    errors_count += 1
                    continue

                # Update product in branch
                branch_client.models.execute_kw(
                    branch_client.db, branch_client.uid, branch_client.password,
                    'product.product', 'write',
                    [[item.sucursal_id], update_data]
                )

                results.append(SyncResult(
                    success=True,
                    message=f"Product {item.barcode} updated successfully",
                    product_id=item.sucursal_id,
                    action="updated",
                    barcode=item.barcode
                ))
                fixed_count += 1
                logger.info(f"Fixed product {item.barcode} (ID: {item.sucursal_id})")

            except Exception as e:
                results.append(SyncResult(
                    success=False,
                    message=f"Error updating product {item.barcode}: {str(e)}",
                    product_id=item.sucursal_id,
                    action="error",
                    barcode=item.barcode,
                    error_details=str(e)
                ))
                errors_count += 1
                logger.error(f"Error fixing product {item.barcode}: {e}")

        logger.info(f"Fixed {fixed_count} inconsistencies, {errors_count} errors")

        return FixInconsistenciesResponse(
            success=True,
            message=f"Processed {len(results)} items: {fixed_count} fixed, {errors_count} errors",
            total_processed=len(results),
            fixed_count=fixed_count,
            errors_count=errors_count,
            results=results
        )

    except Exception as e:
        logger.error(f"Error fixing inconsistencies: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error fixing inconsistencies: {str(e)}"
        )


# Exception handlers
@app.exception_handler(404)
async def not_found_handler(request, exc):
    return JSONResponse(
        status_code=404,
        content={"error": "Endpoint not found", "detail": "The requested endpoint does not exist"}
    )


@app.exception_handler(500)
async def internal_error_handler(request, exc):
    logger.error(f"Internal server error: {exc}")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": "An unexpected error occurred"}
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app", 
        host="127.0.0.1", 
        port=8000, 
        reload=True,
        log_level="info"
    )