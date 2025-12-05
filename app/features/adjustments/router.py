"""
Inventory Adjustment management endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional
from app.core.database import get_db
from app.infrastructure.odoo import get_odoo_manager, OdooConnectionManager
from app.schemas.adjustment import (
    AdjustmentRequest,
    ConfirmAdjustmentRequest,
    AdjustmentResponse,
    PendingAdjustmentListResponse,
    AdjustmentHistoryResponse
)
from app.schemas.auth import UserInfo
from app.features.auth.dependencies import require_admin, require_admin_or_bodeguero
from app.features.adjustments.service import AdjustmentService
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/adjustments", tags=["Adjustments"])


@router.post("/prepare", response_model=AdjustmentResponse)
def prepare_adjustment(
    request: AdjustmentRequest,
    manager: OdooConnectionManager = Depends(get_odoo_manager),
    db: Session = Depends(get_db),
    current_user: UserInfo = Depends(require_admin_or_bodeguero)
):
    """
    Prepare an inventory adjustment (Step 1).

    **Requires:** Admin or Bodeguero role

    Validates items and saves to database.
    **Does NOT update inventory** - that happens on confirmation.

    - **items**: List of adjustment items with product info, quantities, reasons, and descriptions

    Returns:
    - Adjustment validation results
    - Inventory NOT updated flag
    - Adjustment saved to database for admin confirmation

    Use `/adjustments/confirm` to actually execute the adjustment.
    """
    logger.info(f"=== PREPARE ADJUSTMENT ===")
    logger.info(f"User: {current_user.username}")
    logger.info(f"Items count: {len(request.items)}")

    try:
        principal_client = manager.get_principal_client()
        service = AdjustmentService(principal_client, db=db)

        result = service.prepare_adjustment(request.items, current_user)
        return result

    except Exception as e:
        logger.error(f"Error in prepare_adjustment: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Adjustment preparation failed: {str(e)}"
        )


@router.get("/pending", response_model=PendingAdjustmentListResponse)
def get_pending_adjustments(
    manager: OdooConnectionManager = Depends(get_odoo_manager),
    db: Session = Depends(get_db),
    current_user: UserInfo = Depends(require_admin)
):
    """
    Get list of pending adjustments awaiting confirmation.

    **Requires:** Admin role

    Returns all adjustments prepared by bodegueros that are still pending admin confirmation.
    """
    logger.info(f"=== GET PENDING ADJUSTMENTS ===")
    logger.info(f"User: {current_user.username}")

    try:
        principal_client = manager.get_principal_client()
        service = AdjustmentService(principal_client, db=db)

        result = service.get_pending_adjustments()
        logger.info(f"Found {result.total} pending adjustments")
        return result

    except Exception as e:
        logger.error(f"Error in get_pending_adjustments: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve pending adjustments: {str(e)}"
        )


@router.post("/confirm", response_model=AdjustmentResponse)
def confirm_adjustment(
    request: ConfirmAdjustmentRequest,
    adjustment_id: Optional[int] = Query(None, description="ID of pending adjustment to confirm"),
    manager: OdooConnectionManager = Depends(get_odoo_manager),
    db: Session = Depends(get_db),
    current_user: UserInfo = Depends(require_admin)
):
    """
    Confirm and execute an inventory adjustment (Step 2).

    **Requires:** Admin role

    Updates inventory in Odoo based on the adjustment items.
    Marks the pending adjustment as confirmed if adjustment_id is provided.

    - **items**: Final confirmed list of adjustment items
    - **adjustment_id**: (Optional) ID of pending adjustment to confirm

    Returns:
    - Execution results
    - Inventory UPDATED flag
    - Count of successfully processed items

    **WARNING:** This operation updates inventory in Odoo and cannot be undone!
    """
    logger.info(f"=== CONFIRM ADJUSTMENT ===")
    logger.info(f"User: {current_user.username}")
    logger.info(f"Adjustment ID: {adjustment_id}")
    logger.info(f"Items count: {len(request.items)}")

    try:
        principal_client = manager.get_principal_client()
        service = AdjustmentService(principal_client, db=db)

        result = service.confirm_adjustment(request.items, current_user, adjustment_id)
        return result

    except Exception as e:
        logger.error(f"Error in confirm_adjustment: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Adjustment confirmation failed: {str(e)}"
        )


@router.delete("/pending/{adjustment_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_pending_adjustment(
    adjustment_id: int,
    manager: OdooConnectionManager = Depends(get_odoo_manager),
    db: Session = Depends(get_db),
    current_user: UserInfo = Depends(require_admin)
):
    """
    Cancel a pending adjustment.

    **Requires:** Admin role

    Marks the adjustment as rejected/cancelled.
    Does not delete the record (for audit purposes).
    """
    logger.info(f"=== CANCEL PENDING ADJUSTMENT ===")
    logger.info(f"User: {current_user.username}")
    logger.info(f"Adjustment ID: {adjustment_id}")

    try:
        principal_client = manager.get_principal_client()
        service = AdjustmentService(principal_client, db=db)

        service.cancel_pending_adjustment(adjustment_id)
        logger.info(f"Successfully cancelled adjustment {adjustment_id}")
        return None

    except ValueError as e:
        logger.error(f"Validation error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error in cancel_pending_adjustment: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel adjustment: {str(e)}"
        )


@router.get("/history", response_model=AdjustmentHistoryResponse)
def get_adjustment_history(
    start_date: Optional[str] = Query(None, description="Start date (ISO format)"),
    end_date: Optional[str] = Query(None, description="End date (ISO format)"),
    adjustment_type: Optional[str] = Query(None, description="Filter by adjustment type"),
    user_id: Optional[int] = Query(None, description="Filter by user ID"),
    manager: OdooConnectionManager = Depends(get_odoo_manager),
    db: Session = Depends(get_db),
    current_user: UserInfo = Depends(require_admin)
):
    """
    Get adjustment history with optional filters.

    **Requires:** Admin role

    Returns all confirmed adjustments with optional filtering by:
    - Date range
    - Adjustment type (entry/exit/adjustment)
    - User who created the adjustment
    """
    logger.info(f"=== GET ADJUSTMENT HISTORY ===")
    logger.info(f"User: {current_user.username}")
    logger.info(f"Filters - Start: {start_date}, End: {end_date}, Type: {adjustment_type}, User: {user_id}")

    try:
        principal_client = manager.get_principal_client()
        service = AdjustmentService(principal_client, db=db)

        result = service.get_adjustment_history(
            start_date=start_date,
            end_date=end_date,
            adjustment_type=adjustment_type,
            user_id=user_id
        )
        logger.info(f"Found {result.total} history items")
        return result

    except Exception as e:
        logger.error(f"Error in get_adjustment_history: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve adjustment history: {str(e)}"
        )
