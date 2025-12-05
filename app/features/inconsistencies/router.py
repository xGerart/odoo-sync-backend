"""
Inconsistencies detection and fixing endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.core.database import get_db
from app.infrastructure.odoo import get_odoo_manager, OdooConnectionManager
from app.schemas.product import FixInconsistencyItem, InconsistencyResponse
from app.schemas.common import MessageResponse
from app.schemas.auth import UserInfo
from app.features.auth.dependencies import require_admin
from app.features.inconsistencies.service import InconsistencyService


router = APIRouter(prefix="/inconsistencies", tags=["Inconsistencies"])


@router.get("/detect", response_model=InconsistencyResponse)
def detect_inconsistencies(
    manager: OdooConnectionManager = Depends(get_odoo_manager),
    db: Session = Depends(get_db),
    current_user: UserInfo = Depends(require_admin)
):
    """
    Detect price and name inconsistencies between principal and branch.

    **Requires:** Admin role only

    Compares all products between principal and branch locations
    and finds products with:
    - Different prices (>$0.01 difference)
    - Different names

    **Prerequisites:**
    - Both principal and branch must be connected

    Returns list of detected inconsistencies.
    """
    try:
        if not manager.is_branch_connected():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Branch Odoo not connected. Connect to branch first."
            )

        principal_client = manager.get_principal_client()
        branch_client = manager.get_branch_client()

        service = InconsistencyService(principal_client, branch_client)

        result = service.detect_inconsistencies()

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to detect inconsistencies: {str(e)}"
        )


@router.post("/fix", response_model=MessageResponse)
def fix_inconsistencies(
    request: dict,
    manager: OdooConnectionManager = Depends(get_odoo_manager),
    db: Session = Depends(get_db),
    current_user: UserInfo = Depends(require_admin)
):
    """
    Fix detected inconsistencies by updating branch products.

    **Requires:** Admin role only

    Updates branch products to match principal:
    - Sets branch product name if provided
    - Sets branch product list_price if provided
    - Sets branch product standard_price if provided

    **Prerequisites:**
    - Both principal and branch must be connected

    - **items**: List of items to fix

    Returns fix results with count of fixed products.
    """
    try:
        if not manager.is_branch_connected():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Branch Odoo not connected"
            )

        # Parse items from request
        items_data = request.get('items', [])
        items_to_fix = [FixInconsistencyItem(**item) for item in items_data]

        principal_client = manager.get_principal_client()
        branch_client = manager.get_branch_client()

        service = InconsistencyService(principal_client, branch_client)

        result = service.fix_inconsistencies(items_to_fix)

        message = f"Fixed {result['fixed_count']}/{result['total_processed']} inconsistencies"
        if result['errors_count'] > 0:
            message += f". {result['errors_count']} errors occurred."

        return MessageResponse(
            message=message,
            success=result['success']
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fix inconsistencies: {str(e)}"
        )
