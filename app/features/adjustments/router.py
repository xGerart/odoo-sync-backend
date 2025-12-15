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
    AdjustmentHistoryResponse,
    AdjustmentHistoryDetailResponse,
    AdjustmentHistoryListResponse,
    UnifiedAdjustmentHistoryResponse
)
from app.schemas.auth import UserInfo
from app.features.auth.dependencies import require_admin, require_admin_or_bodeguero, get_current_user
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


@router.get("/history/complete", response_model=AdjustmentHistoryListResponse)
def get_complete_adjustment_history(
    skip: int = 0,
    limit: int = 50,
    adjustment_type: Optional[str] = Query(None, description="Filter by adjustment type"),
    executed_by: Optional[str] = Query(None, description="Filter by executor"),
    db: Session = Depends(get_db),
    current_user: UserInfo = Depends(require_admin)
):
    """
    Get complete adjustment execution history (Admin only).

    Returns detailed records from adjustment_history table with snapshots and PDFs.

    **Requires:** Admin role ONLY

    Query parameters:
    - **skip**: Number of records to skip (pagination)
    - **limit**: Maximum number of records to return
    - **adjustment_type**: Filter by type (entry/exit/adjustment)
    - **executed_by**: Filter by user who executed

    Returns:
    - List of complete adjustment history records
    - Total count
    """
    from app.models.adjustment_history import AdjustmentHistory, AdjustmentHistoryItem

    logger.info(f"Getting complete adjustment history (skip={skip}, limit={limit})")

    try:
        query = db.query(AdjustmentHistory)

        # Apply filters
        if adjustment_type:
            # Filter by items' adjustment type (need to join)
            query = query.join(AdjustmentHistoryItem).filter(
                AdjustmentHistoryItem.adjustment_type == adjustment_type
            ).distinct()

        if executed_by:
            query = query.filter(AdjustmentHistory.executed_by == executed_by)

        # Get total before pagination
        total = query.count()

        # Apply pagination and ordering
        histories = query.order_by(
            AdjustmentHistory.executed_at.desc()
        ).offset(skip).limit(limit).all()

        logger.info(f"Retrieved {len(histories)} complete adjustment records (total: {total})")

        return AdjustmentHistoryListResponse(
            history=[AdjustmentHistoryDetailResponse.model_validate(h) for h in histories],
            total=total
        )

    except Exception as e:
        logger.error(f"Error retrieving complete adjustment history: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve adjustment history: {str(e)}"
        )


@router.get("/history/me", response_model=AdjustmentHistoryListResponse)
def get_my_adjustment_history(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: UserInfo = Depends(get_current_user)
):
    """
    Get adjustment history for current user.

    Returns complete adjustment records executed by the current user.

    Query parameters:
    - **skip**: Number of records to skip (pagination)
    - **limit**: Maximum number of records to return

    Returns:
    - List of user's adjustment history
    - Total count
    """
    from app.models.adjustment_history import AdjustmentHistory

    logger.info(f"Getting adjustment history for user {current_user.username}")

    try:
        query = db.query(AdjustmentHistory).filter(
            AdjustmentHistory.executed_by == current_user.username
        )

        total = query.count()

        histories = query.order_by(
            AdjustmentHistory.executed_at.desc()
        ).offset(skip).limit(limit).all()

        logger.info(f"Retrieved {len(histories)} adjustment records for user {current_user.username}")

        return AdjustmentHistoryListResponse(
            history=[AdjustmentHistoryDetailResponse.model_validate(h) for h in histories],
            total=total
        )

    except Exception as e:
        logger.error(f"Error retrieving user adjustment history: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve adjustment history: {str(e)}"
        )


@router.get("/history/unified", response_model=UnifiedAdjustmentHistoryResponse)
def get_unified_adjustment_history(
    skip: int = 0,
    limit: int = 50,
    status_filter: Optional[str] = Query(None, description="Filter by status: pending, confirmed, rejected"),
    adjustment_type: Optional[str] = Query(None, description="Filter by type: entry, exit, adjustment"),
    executed_by: Optional[str] = Query(None, description="Filter by username"),
    db: Session = Depends(get_db),
    current_user: UserInfo = Depends(get_current_user)
):
    """
    Get unified adjustment history (pending + confirmed + rejected).

    Combines pending_adjustments and adjustment_history into a single response.

    **Access control:**
    - Admin: Sees all records
    - Bodeguero: Sees only their own records

    **Query parameters:**
    - **skip**: Number of records to skip for pagination
    - **limit**: Maximum number of records to return
    - **status_filter**: Filter by status (pending, confirmed, rejected)
    - **adjustment_type**: Filter by type (entry, exit, adjustment)
    - **executed_by**: Filter by username (admin only)

    Returns a unified list sorted by creation date (most recent first).
    """
    from app.models.pending_adjustment import PendingAdjustment, AdjustmentStatus
    from app.models.adjustment_history import AdjustmentHistory

    logger.info(f"=== GET UNIFIED ADJUSTMENT HISTORY ===")
    logger.info(f"User: {current_user.username}, Role: {current_user.role}")
    logger.info(f"Filters: status={status_filter}, type={adjustment_type}, executed_by={executed_by}")

    try:
        unified_records = []

        # 1. Get pending and rejected adjustments (PENDING, REJECTED)
        pending_query = db.query(PendingAdjustment).filter(
            PendingAdjustment.status.in_([AdjustmentStatus.PENDING, AdjustmentStatus.REJECTED])
        )

        # Filter by role
        if current_user.role.value != 'admin':
            pending_query = pending_query.filter(PendingAdjustment.username == current_user.username)

        # Apply filters
        if status_filter:
            pending_query = pending_query.filter(PendingAdjustment.status == status_filter)
        if adjustment_type:
            pending_query = pending_query.filter(PendingAdjustment.adjustment_type == adjustment_type)
        if executed_by and current_user.role.value == 'admin':
            pending_query = pending_query.filter(PendingAdjustment.username == executed_by)

        pending_adjustments = pending_query.all()
        logger.info(f"Found {len(pending_adjustments)} pending/rejected adjustments")

        # Convert pending to unified format
        for pending in pending_adjustments:
            unified_records.append({
                'id': f'pending_{pending.id}',
                'original_id': pending.id,
                'source': 'pending',
                'status': pending.status.value,
                'adjustment_type': pending.adjustment_type.value,
                'username': pending.username,
                'created_at': pending.created_at,
                'updated_at': pending.updated_at,
                'confirmed_at': pending.confirmed_at,
                'confirmed_by': pending.confirmed_by,
                'total_items': len(pending.items),
                'successful_items': None,
                'failed_items': None,
                'items': [
                    {
                        'barcode': item.barcode,
                        'product_name': item.product_name,
                        'quantity': item.quantity,
                        'adjustment_type': item.adjustment_type.value,
                        'reason': item.reason.value if item.reason else None,
                        'description': item.description,
                        'available_stock': item.available_stock
                    }
                    for item in pending.items
                ],
                'has_pdf': False,
                'pdf_filename': None,
                'has_errors': None
            })

        # 2. Get executed adjustments (from adjustment_history)
        # Only fetch if not filtering for pending/rejected specifically
        if not status_filter or status_filter == 'confirmed':
            history_query = db.query(AdjustmentHistory)

            # Filter by role
            if current_user.role.value != 'admin':
                history_query = history_query.filter(AdjustmentHistory.executed_by == current_user.username)

            # Apply filters
            if executed_by and current_user.role.value == 'admin':
                history_query = history_query.filter(AdjustmentHistory.executed_by == executed_by)

            history_records = history_query.all()
            logger.info(f"Found {len(history_records)} executed adjustments")

            # Convert history to unified format
            for history in history_records:
                # Determine adjustment type from items (all items should have same type)
                adjustment_type_value = history.items[0].adjustment_type if history.items else 'adjustment'

                # Apply adjustment_type filter if specified
                if adjustment_type and adjustment_type_value != adjustment_type:
                    continue

                unified_records.append({
                    'id': f'history_{history.id}',
                    'original_id': history.id,
                    'source': 'history',
                    'status': 'confirmed',  # All history records are confirmed
                    'adjustment_type': adjustment_type_value,
                    'username': history.executed_by,
                    'created_at': history.executed_at,
                    'updated_at': history.executed_at,
                    'confirmed_at': history.executed_at,
                    'confirmed_by': history.executed_by,
                    'total_items': history.total_items,
                    'successful_items': history.successful_items,
                    'failed_items': history.failed_items,
                    'items': [
                        {
                            'barcode': item.barcode,
                            'product_name': item.product_name,
                            'quantity': item.quantity_adjusted,
                            'adjustment_type': item.adjustment_type,
                            'reason': item.reason,
                            'success': item.success,
                            'stock_before': item.stock_before,
                            'stock_after': item.stock_after,
                            'error_message': item.error_message
                        }
                        for item in history.items
                    ],
                    'has_pdf': bool(history.pdf_filename),
                    'pdf_filename': history.pdf_filename,
                    'has_errors': history.has_errors
                })

        # 3. Sort by date (most recent first)
        unified_records.sort(key=lambda x: x['created_at'], reverse=True)

        # 4. Apply pagination
        total = len(unified_records)
        paginated = unified_records[skip:skip+limit]

        logger.info(f"Returning {len(paginated)} records out of {total} total")

        return {
            'records': paginated,
            'total': total
        }

    except Exception as e:
        logger.error(f"Error in get_unified_adjustment_history: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve unified adjustment history: {str(e)}"
        )


@router.get("/history/{history_id}", response_model=AdjustmentHistoryDetailResponse)
def get_adjustment_history_detail(
    history_id: int,
    db: Session = Depends(get_db),
    current_user: UserInfo = Depends(get_current_user)
):
    """
    Get detailed adjustment history record.

    Returns complete details of a single adjustment execution including
    all items, stock snapshots, and errors.

    **Access control:**
    - Admin: Can view any adjustment
    - Bodeguero: Can only view their own adjustments

    Returns:
    - Complete adjustment history record with all items
    """
    from app.models.adjustment_history import AdjustmentHistory

    logger.info(f"Getting adjustment history detail for ID {history_id}")

    try:
        history = db.query(AdjustmentHistory).filter_by(id=history_id).first()

        if not history:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Adjustment history record {history_id} not found"
            )

        # Validate permissions
        if current_user.role.value != 'admin':
            if history.executed_by != current_user.username:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Not authorized to view this adjustment"
                )

        logger.info(f"Retrieved adjustment history detail for ID {history_id}")

        return AdjustmentHistoryDetailResponse.model_validate(history)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving adjustment history detail: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve adjustment history: {str(e)}"
        )


@router.get("/history/{history_id}/pdf")
def download_adjustment_pdf(
    history_id: int,
    db: Session = Depends(get_db),
    current_user: UserInfo = Depends(get_current_user)
):
    """
    Download PDF report for an adjustment history record.

    Returns the PDF file for download.

    **Access control:**
    - Admin: Can download any PDF
    - Bodeguero: Can only download PDFs for their own adjustments
    """
    import base64
    from fastapi.responses import Response
    from app.models.adjustment_history import AdjustmentHistory

    logger.info(f"Downloading PDF for adjustment history ID {history_id}")

    try:
        history = db.query(AdjustmentHistory).filter_by(id=history_id).first()

        if not history:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Adjustment history record {history_id} not found"
            )

        # Validate permissions
        if current_user.role.value != 'admin':
            if history.executed_by != current_user.username:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Not authorized to download this PDF"
                )

        if not history.pdf_content:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="PDF not available for this adjustment"
            )

        # Decode base64 PDF
        pdf_bytes = base64.b64decode(history.pdf_content)

        filename = history.pdf_filename or f"adjustment_{history_id}.pdf"

        logger.info(f"Downloading PDF for adjustment history {history_id}: {filename}")

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
        logger.error(f"Error downloading adjustment PDF: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to download PDF: {str(e)}"
        )
