"""
Sales and cash register endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.infrastructure.odoo import get_odoo_manager, OdooConnectionManager
from app.schemas.sales import CierreCajaResponse
from app.schemas.auth import UserInfo
from app.features.auth.dependencies import require_admin_or_cajero
from app.features.sales.service import SalesService
from app.utils.validators import validate_date_format


router = APIRouter(prefix="/sales", tags=["Sales"])


@router.get("/cierre-caja/{date}", response_model=CierreCajaResponse)
def get_cierre_caja(
    date: str,
    manager: OdooConnectionManager = Depends(get_odoo_manager),
    db: Session = Depends(get_db),
    current_user: UserInfo = Depends(require_admin_or_cajero)
):
    """
    Get cash register closing report for a specific date.

    **Requires:** Admin or Cajero role

    - **date**: Date in format YYYY-MM-DD (e.g., 2024-01-15)

    Returns:
    - Total sales
    - Sales grouped by employee and payment method
    - Payment method summaries
    - POS sessions
    - First and last sale times
    """
    # Validate date format
    is_valid, error_msg = validate_date_format(date)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg
        )

    try:
        client = manager.get_principal_client()
        service = SalesService(client)

        result = service.get_cierre_caja(date)

        return result

    except Exception as e:
        import traceback
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error in get_cierre_caja: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get cierre de caja: {str(e)}"
        )
