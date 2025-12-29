"""
Transfer management endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.infrastructure.odoo import get_odoo_manager, OdooConnectionManager
from app.schemas.transfer import (
    TransferRequest,
    VerifyTransferRequest,
    ConfirmTransferRequest,
    TransferResponse,
    TransferValidationResponse,
    PendingTransferListResponse,
    PendingTransferResponse,
    TransferHistoryResponse,
    TransferHistoryListResponse,
    TransferHistoryProductSearchResponse,
    TransferHistorySearchResult,
    ProductMatchInfo
)
from app.schemas.auth import UserInfo
from app.features.auth.dependencies import (
    require_admin,
    require_admin_or_bodeguero,
    require_bodeguero,
    require_admin_or_bodeguero_or_cajero,
    get_current_user
)
from app.features.transfers.service import TransferService
from app.models import TransferStatus


router = APIRouter(prefix="/transfers", tags=["Transfers"])


@router.post("/prepare", response_model=TransferResponse)
def prepare_transfer(
    request: TransferRequest,
    manager: OdooConnectionManager = Depends(get_odoo_manager),
    db: Session = Depends(get_db),
    current_user: UserInfo = Depends(require_admin_or_bodeguero_or_cajero)
):
    """
    Prepare a transfer (Step 1).

    **Requires:** Admin, Bodeguero, or Cajero role

    Validates stock availability, generates transfer data, and SAVES to database.
    **Does NOT reduce inventory** - that happens on confirmation.

    **Flow:**
    - Cajero: Transfer goes to PENDING_VERIFICATION (requires bodeguero verification)
    - Bodeguero/Admin: Transfer goes to PENDING (directly to admin for confirmation)

    - **products**: List of products with barcodes and quantities

    Returns:
    - Transfer validation results
    - XML content for branch upload
    - Inventory NOT reduced flag
    - Transfer saved to database for admin confirmation

    Use `/transfers/confirm` to actually execute the transfer.
    """
    import logging
    logger = logging.getLogger(__name__)

    logger.info(f"=== PREPARE TRANSFER ===")
    logger.info(f"User: {current_user.username}")
    logger.info(f"Products count: {len(request.products)}")

    try:
        principal_client = manager.get_principal_client()
        service = TransferService(principal_client, db=db)

        # First, validate and prepare the transfer (returns product details)
        result, processed_products = service.prepare_transfer_with_details(request.products)

        if result.success and processed_products:
            # Save to database for admin confirmation
            try:
                # Get destination name if location_id provided
                destination_name = None
                if request.destination_location_id:
                    from app.core.locations import LocationService
                    location_service = LocationService()
                    destination = location_service.get_location_by_id(request.destination_location_id)
                    destination_name = destination.name if destination else None

                pending_transfer = service.save_pending_transfer(
                    items=request.products,
                    user=current_user,
                    product_details=processed_products,
                    destination_location_id=request.destination_location_id,
                    destination_location_name=destination_name
                )
                logger.info(f"Transfer saved to database with ID: {pending_transfer.id}")
                result.message += f" Transfer ID: {pending_transfer.id}"
            except Exception as save_error:
                logger.error(f"Failed to save transfer to database: {str(save_error)}")
                import traceback
                logger.error(traceback.format_exc())
                # Don't fail the entire request if save fails
                result.message += " (Warning: Could not save to database)"

        return result

    except Exception as e:
        logger.error(f"Error in prepare_transfer: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Transfer preparation failed: {str(e)}"
        )


@router.get("/pending", response_model=PendingTransferListResponse)
def get_pending_transfers(
    manager: OdooConnectionManager = Depends(get_odoo_manager),
    db: Session = Depends(get_db),
    current_user: UserInfo = Depends(get_current_user)
):
    """
    Get list of pending transfers based on user role.

    **Role-based filtering:**
    - **Admin**: Only transfers with status='pending' (ready for confirmation)
    - **Bodeguero**: Only transfers with status='pending_verification' (from cajeros needing verification)
    - **Cajero**: Only their own transfers (any status)

    Returns:
    - List of pending transfers with all items
    - Total count
    """
    import logging
    logger = logging.getLogger(__name__)

    try:
        principal_client = manager.get_principal_client()
        service = TransferService(principal_client, db=db)

        result = service.get_pending_transfers(user=current_user)

        logger.info(f"Retrieved {result.total} pending transfers for {current_user.role.value}")

        return result

    except Exception as e:
        logger.error(f"Error getting pending transfers: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve pending transfers: {str(e)}"
        )


@router.post("/verify", response_model=PendingTransferResponse)
def verify_transfer(
    request: VerifyTransferRequest,
    manager: OdooConnectionManager = Depends(get_odoo_manager),
    db: Session = Depends(get_db),
    current_user: UserInfo = Depends(require_bodeguero)
):
    """
    Verify a transfer prepared by cajero (verification step).

    **Requires:** Bodeguero role ONLY

    Changes transfer status from PENDING_VERIFICATION to PENDING.
    Allows editing quantities before passing to admin for final confirmation.

    - **transfer_id**: ID of transfer to verify
    - **products**: Verified products (can be edited from original)

    Returns:
    - Updated transfer with status='pending'
    - Transfer ready for admin confirmation
    """
    import logging
    logger = logging.getLogger(__name__)

    logger.info(f"=== VERIFY TRANSFER ===")
    logger.info(f"Transfer ID: {request.transfer_id}")
    logger.info(f"Verified by: {current_user.username}")
    logger.info(f"Products count: {len(request.products)}")

    try:
        principal_client = manager.get_principal_client()
        service = TransferService(principal_client, db=db)

        result = service.verify_transfer(
            transfer_id=request.transfer_id,
            items=request.products,
            verified_by=current_user.username
        )

        logger.info(f"Transfer {request.transfer_id} verified successfully")

        return result

    except Exception as e:
        logger.error(f"Error verifying transfer: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to verify transfer: {str(e)}"
        )


@router.delete("/pending/{transfer_id}")
def cancel_pending_transfer(
    transfer_id: int,
    manager: OdooConnectionManager = Depends(get_odoo_manager),
    db: Session = Depends(get_db),
    current_user: UserInfo = Depends(require_admin)
):
    """
    Cancel a pending transfer.

    **Requires:** Admin role ONLY

    Marks the transfer as cancelled. This action cannot be undone.

    Returns:
    - Success message
    """
    import logging
    logger = logging.getLogger(__name__)

    try:
        principal_client = manager.get_principal_client()
        service = TransferService(principal_client, db=db)

        # Update status to cancelled
        service.update_transfer_status(
            transfer_id=transfer_id,
            status=TransferStatus.CANCELLED,
            confirmed_by=current_user.username
        )

        logger.info(f"Transfer {transfer_id} cancelled by {current_user.username}")

        from app.schemas.common import MessageResponse
        return MessageResponse(
            message=f"Transferencia #{transfer_id} cancelada exitosamente",
            success=True
        )

    except Exception as e:
        logger.error(f"Error cancelling transfer: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel transfer: {str(e)}"
        )


@router.post("/validate", response_model=TransferValidationResponse)
def validate_transfer(
    request: TransferRequest,
    manager: OdooConnectionManager = Depends(get_odoo_manager),
    db: Session = Depends(get_db),
    current_user: UserInfo = Depends(require_admin_or_bodeguero)
):
    """
    Validate transfer items without making changes.

    **Requires:** Admin or Bodeguero role

    Checks stock availability and transfer limits without preparing the transfer.

    - **products**: List of products to validate

    Returns validation errors and warnings.
    """
    try:
        principal_client = manager.get_principal_client()
        service = TransferService(principal_client)

        result = service.validate_transfer(request.products)

        return result

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Validation failed: {str(e)}"
        )


@router.post("/confirm", response_model=TransferResponse)
def confirm_transfer(
    request: ConfirmTransferRequest,
    transfer_id: int = None,
    manager: OdooConnectionManager = Depends(get_odoo_manager),
    db: Session = Depends(get_db),
    current_user: UserInfo = Depends(require_admin)
):
    """
    Confirm and execute transfer (Step 2).

    **Requires:** Admin role ONLY

    **IMPORTANT:** This endpoint:
    1. Reduces inventory in principal location
    2. Creates/updates products in branch
    3. Adds inventory to branch location
    4. Updates transfer status in database if transfer_id provided

    This action is irreversible. Make sure you've validated the transfer first.

    - **products**: Final confirmed list of products to transfer
    - **transfer_id**: Optional ID of pending transfer (will mark as confirmed)

    **Prerequisites:**
    - Both principal AND branch Odoo must be connected
    - Call `/auth/login/odoo` for principal
    - Call connection endpoint for branch

    Returns:
    - Transfer execution results
    - XML content for records
    - Inventory reduced flag = true
    """
    import logging
    logger = logging.getLogger(__name__)

    logger.info(f"=== CONFIRM TRANSFER START ===")
    logger.info(f"Transfer ID: {transfer_id}")
    logger.info(f"Admin: {current_user.username}")
    logger.info(f"Products in request: {len(request.products)}")

    # Validate that products have quantities > 0
    if not request.products:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No products in transfer request"
        )

    total_quantity = sum(item.quantity for item in request.products)
    if total_quantity == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Transfer has no products with quantity > 0"
        )

    try:
        # Verify both connections exist
        if not manager.is_principal_connected():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Principal Odoo not connected"
            )

        if not manager.is_branch_connected():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Branch Odoo not connected. Connect to branch first."
            )

        principal_client = manager.get_principal_client()
        branch_client = manager.get_branch_client()

        service = TransferService(principal_client, branch_client, db=db)

        # Execute the transfer with report generation
        result = service.confirm_transfer(
            items=request.products,
            transfer_id=transfer_id,
            username=current_user.username,
            destination_location_id=request.destination_location_id
        )

        # If successful and transfer_id provided, update status in database
        if result.success and transfer_id:
            try:
                service.update_transfer_status(
                    transfer_id=transfer_id,
                    status=TransferStatus.CONFIRMED,
                    confirmed_by=current_user.username
                )
                logger.info(f"Transfer {transfer_id} marked as confirmed by {current_user.username}")
                # Create new response with updated message (Pydantic objects are immutable)
                result = TransferResponse(
                    success=result.success,
                    message=result.message + f" (Transfer ID: {transfer_id} confirmed)",
                    xml_content=result.xml_content,
                    pdf_content=result.pdf_content,
                    pdf_filename=result.pdf_filename,
                    processed_count=result.processed_count,
                    inventory_reduced=result.inventory_reduced,
                    products=result.products
                )
            except Exception as update_error:
                logger.warning(f"Failed to update transfer status: {str(update_error)}")
                # Don't fail the entire request if status update fails
                result = TransferResponse(
                    success=result.success,
                    message=result.message + " (Warning: Status not updated in database)",
                    xml_content=result.xml_content,
                    pdf_content=result.pdf_content,
                    pdf_filename=result.pdf_filename,
                    processed_count=result.processed_count,
                    inventory_reduced=result.inventory_reduced,
                    products=result.products
                )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Transfer confirmation failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Transfer confirmation failed: {str(e)}"
        )


# Transfer History Endpoints

@router.get("/history", response_model=TransferHistoryListResponse)
def get_transfer_history(
    skip: int = 0,
    limit: int = 50,
    destination_location_id: str = None,
    executed_by: str = None,
    db: Session = Depends(get_db),
    current_user: UserInfo = Depends(require_admin)
):
    """
    Get transfer execution history (Admin only).

    **Requires:** Admin role ONLY

    Returns ALL transfers (pending and completed) from all users.
    Combines pending_transfers and transfer_history.

    Query parameters:
    - **skip**: Number of records to skip (pagination)
    - **limit**: Maximum number of records to return
    - **destination_location_id**: Filter by destination location
    - **executed_by**: Filter by user who executed/prepared the transfer

    Returns:
    - List of ALL transfer records (pending + completed)
    - Total count
    """
    import logging
    from app.models.transfer_history import TransferHistory
    from app.models.pending_transfer import PendingTransfer, TransferStatus
    from app.schemas.transfer import TransferHistoryItemResponse

    logger = logging.getLogger(__name__)

    try:
        all_records = []

        # 1. Get completed transfers (from transfer_history)
        completed_query = db.query(TransferHistory)

        # Apply filters for completed transfers
        if destination_location_id:
            completed_query = completed_query.filter(TransferHistory.destination_location_id == destination_location_id)
        if executed_by:
            completed_query = completed_query.filter(TransferHistory.executed_by == executed_by)

        completed_transfers = completed_query.all()

        for record in completed_transfers:
            history_dict = {
                "id": record.id,
                "status": "COMPLETED",
                "pending_transfer_id": record.pending_transfer_id,
                "origin_location": record.origin_location,
                "destination_location_id": record.destination_location_id,
                "destination_location_name": record.destination_location_name,
                "executed_by": record.executed_by,
                "executed_at": record.executed_at,
                "total_items": record.total_items,
                "successful_items": record.successful_items,
                "failed_items": record.failed_items,
                "total_quantity_requested": record.total_quantity_requested,
                "total_quantity_transferred": record.total_quantity_transferred,
                "has_errors": record.has_errors,
                "error_summary": record.error_summary,
                "pdf_filename": record.pdf_filename,
                "items": [TransferHistoryItemResponse.model_validate(item) for item in record.items]
            }
            all_records.append((record.executed_at, TransferHistoryResponse(**history_dict)))

        # 2. Get pending, cancelled, and confirmed (without history) transfers (from pending_transfers)
        # Note: CONFIRMED transfers should have a history record, but we include them
        # here as fallback in case history creation failed
        pending_query = db.query(PendingTransfer).filter(
            PendingTransfer.status.in_([
                TransferStatus.PENDING,
                TransferStatus.PENDING_VERIFICATION,
                TransferStatus.CANCELLED,
                TransferStatus.CONFIRMED
            ])
        )

        # Apply filters for pending transfers
        if destination_location_id:
            pending_query = pending_query.filter(PendingTransfer.destination_location_id == destination_location_id)
        if executed_by:
            pending_query = pending_query.filter(PendingTransfer.username == executed_by)

        pending_transfers = pending_query.all()

        # Get IDs of pending_transfers that already have history records (to avoid duplicates)
        pending_ids_with_history = {record.pending_transfer_id for record in completed_transfers if record.pending_transfer_id}

        for pending in pending_transfers:
            # Skip if this pending transfer already has a history record (avoid duplicates)
            if pending.id in pending_ids_with_history:
                continue
            # Convert pending_transfer to history format
            total_quantity = sum(item.quantity for item in pending.items)

            # Convert pending items to history item format
            items_list = []
            for item in pending.items:
                item_dict = {
                    "id": item.id,
                    "barcode": item.barcode,
                    "product_id": item.product_id,
                    "product_name": item.product_name,
                    "quantity_requested": item.quantity,
                    "quantity_transferred": 0,  # Not yet transferred
                    "success": False,  # Not yet executed
                    "error_message": None,
                    "unit_price": item.unit_price,
                    "total_value": 0,
                    "is_new_product": False
                }
                items_list.append(item_dict)

            history_dict = {
                "id": pending.id,
                "status": pending.status,  # "PENDING" or "PENDING_VERIFICATION"
                "pending_transfer_id": pending.id,
                "origin_location": "principal",
                "destination_location_id": pending.destination_location_id or "unknown",
                "destination_location_name": pending.destination_location_name or "Sin destino",
                "executed_by": pending.username,
                "executed_at": pending.created_at,  # Use created_at for pending
                "total_items": len(pending.items),
                "successful_items": 0,  # Not yet executed
                "failed_items": 0,
                "total_quantity_requested": total_quantity,
                "total_quantity_transferred": 0,  # Not yet transferred
                "has_errors": False,
                "error_summary": None,
                "pdf_filename": None,
                "items": items_list
            }
            all_records.append((pending.created_at, TransferHistoryResponse(**history_dict)))

        # 3. Sort all records by date (most recent first)
        all_records.sort(key=lambda x: x[0], reverse=True)

        # 4. Apply pagination
        total = len(all_records)
        paginated_records = [record[1] for record in all_records[skip:skip + limit]]

        logger.info(f"Retrieved {len(paginated_records)} transfer history records for admin (total: {total})")

        return TransferHistoryListResponse(
            history=paginated_records,
            total=total
        )

    except Exception as e:
        logger.error(f"Error retrieving transfer history: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve transfer history: {str(e)}"
        )


@router.get("/history/me", response_model=TransferHistoryListResponse)
def get_my_transfer_history(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: UserInfo = Depends(get_current_user)
):
    """
    Get transfer history for current user (Bodeguero/Cajero/Admin).

    Returns ALL transfers (pending and completed) prepared by the current user.
    Combines pending_transfers and transfer_history.

    Query parameters:
    - **skip**: Number of records to skip (pagination)
    - **limit**: Maximum number of records to return

    Returns:
    - List of ALL transfer records for user (pending + completed)
    - Total count
    """
    import logging
    from app.models.transfer_history import TransferHistory
    from app.models.pending_transfer import PendingTransfer, TransferStatus
    from app.schemas.transfer import TransferHistoryItemResponse

    logger = logging.getLogger(__name__)

    try:
        all_records = []

        # 1. Get completed transfers (from transfer_history)
        # Include transfers executed by user OR prepared by user (even if executed by admin)
        completed_query = db.query(TransferHistory).outerjoin(
            PendingTransfer,
            TransferHistory.pending_transfer_id == PendingTransfer.id
        ).filter(
            (TransferHistory.executed_by == current_user.username) |  # Executed by user
            (PendingTransfer.username == current_user.username)        # Prepared by user
        )
        completed_transfers = completed_query.all()

        for record in completed_transfers:
            history_dict = {
                "id": record.id,
                "status": "COMPLETED",
                "pending_transfer_id": record.pending_transfer_id,
                "origin_location": record.origin_location,
                "destination_location_id": record.destination_location_id,
                "destination_location_name": record.destination_location_name,
                "executed_by": record.executed_by,
                "executed_at": record.executed_at,
                "total_items": record.total_items,
                "successful_items": record.successful_items,
                "failed_items": record.failed_items,
                "total_quantity_requested": record.total_quantity_requested,
                "total_quantity_transferred": record.total_quantity_transferred,
                "has_errors": record.has_errors,
                "error_summary": record.error_summary,
                "pdf_filename": record.pdf_filename,
                "items": [TransferHistoryItemResponse.model_validate(item) for item in record.items]
            }
            all_records.append((record.executed_at, TransferHistoryResponse(**history_dict)))

        # 2. Get pending, cancelled, and confirmed (without history) transfers (from pending_transfers)
        # Note: CONFIRMED transfers should have a history record, but we include them
        # here as fallback in case history creation failed
        pending_query = db.query(PendingTransfer).filter(
            PendingTransfer.username == current_user.username,
            PendingTransfer.status.in_([
                TransferStatus.PENDING,
                TransferStatus.PENDING_VERIFICATION,
                TransferStatus.CANCELLED,
                TransferStatus.CONFIRMED
            ])
        )
        pending_transfers = pending_query.all()

        # Get IDs of pending_transfers that already have history records (to avoid duplicates)
        pending_ids_with_history = {record.pending_transfer_id for record in completed_transfers if record.pending_transfer_id}

        for pending in pending_transfers:
            # Skip if this pending transfer already has a history record (avoid duplicates)
            if pending.id in pending_ids_with_history:
                continue
            # Convert pending_transfer to history format
            total_quantity = sum(item.quantity for item in pending.items)

            # Convert pending items to history item format
            items_list = []
            for item in pending.items:
                item_dict = {
                    "id": item.id,
                    "barcode": item.barcode,
                    "product_id": item.product_id,
                    "product_name": item.product_name,
                    "quantity_requested": item.quantity,
                    "quantity_transferred": 0,  # Not yet transferred
                    "success": False,  # Not yet executed
                    "error_message": None,
                    "unit_price": item.unit_price,
                    "total_value": 0,
                    "is_new_product": False
                }
                items_list.append(item_dict)

            history_dict = {
                "id": pending.id,
                "status": pending.status,  # "PENDING" or "PENDING_VERIFICATION"
                "pending_transfer_id": pending.id,
                "origin_location": "principal",
                "destination_location_id": pending.destination_location_id or "unknown",
                "destination_location_name": pending.destination_location_name or "Sin destino",
                "executed_by": pending.username,
                "executed_at": pending.created_at,  # Use created_at for pending
                "total_items": len(pending.items),
                "successful_items": 0,  # Not yet executed
                "failed_items": 0,
                "total_quantity_requested": total_quantity,
                "total_quantity_transferred": 0,  # Not yet transferred
                "has_errors": False,
                "error_summary": None,
                "pdf_filename": None,
                "items": items_list
            }
            all_records.append((pending.created_at, TransferHistoryResponse(**history_dict)))

        # 3. Sort all records by date (most recent first)
        all_records.sort(key=lambda x: x[0], reverse=True)

        # 4. Apply pagination
        total = len(all_records)
        paginated_records = [record[1] for record in all_records[skip:skip + limit]]

        logger.info(f"Retrieved {len(paginated_records)} transfer history records for user {current_user.username} (total: {total})")

        return TransferHistoryListResponse(
            history=paginated_records,
            total=total
        )

    except Exception as e:
        logger.error(f"Error retrieving user transfer history: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve transfer history: {str(e)}"
        )


@router.get("/history/{history_id}", response_model=TransferHistoryResponse)
def get_transfer_history_detail(
    history_id: int,
    db: Session = Depends(get_db),
    current_user: UserInfo = Depends(get_current_user)
):
    """
    Get detailed transfer history record.

    Returns complete details of a single transfer execution including
    all items, stock snapshots, and errors.

    **Access control:**
    - Admin: Can view any transfer
    - Bodeguero/Cajero: Can only view their own transfers

    Returns:
    - Complete transfer history record with all items
    """
    import logging
    from app.models.transfer_history import TransferHistory
    from app.models.pending_transfer import PendingTransfer

    logger = logging.getLogger(__name__)

    try:
        history = db.query(TransferHistory).filter_by(id=history_id).first()

        if not history:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Transfer history record {history_id} not found"
            )

        # Validate permissions: Admin can see all, others only their own
        if current_user.role.value != 'admin':
            if history.pending_transfer_id:
                pending = db.query(PendingTransfer).filter_by(id=history.pending_transfer_id).first()
                if not pending or pending.username != current_user.username:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Not authorized to view this transfer"
                    )
            else:
                # History without pending_transfer (direct admin transfers) - only admin can see
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Not authorized to view this transfer"
                )

        logger.info(f"Retrieved transfer history detail for ID {history_id}")

        return TransferHistoryResponse.model_validate(history)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving transfer history detail: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve transfer history: {str(e)}"
        )


@router.get("/history/{history_id}/pdf")
def download_transfer_pdf(
    history_id: int,
    db: Session = Depends(get_db),
    current_user: UserInfo = Depends(get_current_user)
):
    """
    Download PDF report for a transfer history record.

    Returns the PDF file for download.

    **Access control:**
    - Admin: Can download any PDF
    - Bodeguero/Cajero: Can only download PDFs for their own transfers
    """
    import logging
    import base64
    from fastapi.responses import Response
    from app.models.transfer_history import TransferHistory
    from app.models.pending_transfer import PendingTransfer

    logger = logging.getLogger(__name__)

    try:
        history = db.query(TransferHistory).filter_by(id=history_id).first()

        if not history:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Transfer history record {history_id} not found"
            )

        # Validate permissions (same as detail endpoint)
        if current_user.role.value != 'admin':
            if history.pending_transfer_id:
                pending = db.query(PendingTransfer).filter_by(id=history.pending_transfer_id).first()
                if not pending or pending.username != current_user.username:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Not authorized to download this PDF"
                    )
            else:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Not authorized to download this PDF"
                )

        if not history.pdf_content:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="PDF not available for this transfer"
            )

        # Decode base64 PDF content
        pdf_bytes = base64.b64decode(history.pdf_content)

        filename = history.pdf_filename or f"transfer_{history_id}.pdf"

        logger.info(f"Downloading PDF for transfer history {history_id}: {filename}")

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading transfer PDF: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to download PDF: {str(e)}"
        )


@router.get("/history/search/products", response_model=TransferHistoryProductSearchResponse)
def search_product_in_transfers(
    search_query: str,
    search_type: str = "barcode",
    status_filter: str = None,
    db: Session = Depends(get_db),
    current_user: UserInfo = Depends(get_current_user)
):
    """
    Search for a product in transfer history.

    **Requires:** Any authenticated user

    Searches for products by barcode or name in transfer history and returns
    all transfers that contain the matched product.

    **Access control:**
    - Admin: Sees all transfers
    - Bodeguero/Cajero: Only see their own transfers

    Query parameters:
    - **search_query**: Product barcode or name to search (minimum 2 characters)
    - **search_type**: Type of search - "barcode", "name", or "both" (default: "barcode")
    - **status_filter**: Optional filter by status (COMPLETED, PENDING, etc.)

    Returns:
    - List of transfers containing the product
    - Total count of matching transfers
    - Search query and type used
    """
    import logging
    from sqlalchemy import or_
    from sqlalchemy.orm import joinedload
    from app.models.transfer_history import TransferHistory, TransferHistoryItem

    logger = logging.getLogger(__name__)

    try:
        # Validate search query length
        if len(search_query) < 2:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Search query must be at least 2 characters"
            )

        # Validate search_type
        if search_type not in ["barcode", "name", "both"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="search_type must be 'barcode', 'name', or 'both'"
            )

        # Build query: join TransferHistory with TransferHistoryItem
        query = db.query(TransferHistory, TransferHistoryItem).join(
            TransferHistoryItem,
            TransferHistory.id == TransferHistoryItem.history_id
        )

        # Apply search filter
        search_pattern = f"%{search_query}%"
        if search_type == "barcode":
            query = query.filter(TransferHistoryItem.barcode.ilike(search_pattern))
        elif search_type == "name":
            query = query.filter(TransferHistoryItem.product_name.ilike(search_pattern))
        elif search_type == "both":
            query = query.filter(
                or_(
                    TransferHistoryItem.barcode.ilike(search_pattern),
                    TransferHistoryItem.product_name.ilike(search_pattern)
                )
            )

        # Apply permission filter: admin sees all, others only their own
        if current_user.role.value != 'admin':
            query = query.filter(TransferHistory.executed_by == current_user.username)

        # Apply status filter if provided
        # Note: TransferHistory records are always "COMPLETED" status
        # We're filtering on the history table which only has completed transfers
        if status_filter and status_filter != "COMPLETED":
            # If filtering for non-COMPLETED statuses, return empty results
            # as TransferHistory only stores completed transfers
            return TransferHistoryProductSearchResponse(
                results=[],
                total=0,
                search_query=search_query,
                search_type=search_type
            )

        # Order by most recent first and limit to 500 results
        query = query.order_by(TransferHistory.executed_at.desc()).limit(500)

        # Execute query
        results = query.all()

        # Build response: group by transfer_history and include matched product info
        transfers_dict = {}
        for history, item in results:
            if history.id not in transfers_dict:
                transfers_dict[history.id] = {
                    "history": history,
                    "matched_item": item
                }

        # Convert to response format
        search_results = []
        for transfer_data in transfers_dict.values():
            history = transfer_data["history"]
            matched_item = transfer_data["matched_item"]

            search_results.append(
                TransferHistorySearchResult(
                    id=history.id,
                    status="COMPLETED",
                    executed_by=history.executed_by,
                    executed_at=history.executed_at,
                    destination_location_name=history.destination_location_name,
                    destination_location_id=history.destination_location_id,
                    total_items=history.total_items,
                    successful_items=history.successful_items,
                    failed_items=history.failed_items,
                    has_errors=history.has_errors,
                    pdf_filename=history.pdf_filename,
                    matched_product=ProductMatchInfo(
                        barcode=matched_item.barcode,
                        product_name=matched_item.product_name,
                        quantity_requested=matched_item.quantity_requested,
                        quantity_transferred=matched_item.quantity_transferred,
                        success=matched_item.success
                    )
                )
            )

        logger.info(f"Product search for '{search_query}' ({search_type}): found {len(search_results)} transfers")

        return TransferHistoryProductSearchResponse(
            results=search_results,
            total=len(search_results),
            search_query=search_query,
            search_type=search_type
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error searching products in transfers: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to search products: {str(e)}"
        )
