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
    PendingTransferResponse
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
                pending_transfer = service.save_pending_transfer(
                    items=request.products,
                    user=current_user,
                    product_details=processed_products
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
            username=current_user.username
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
