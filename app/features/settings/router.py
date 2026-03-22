"""
Application settings endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.core.database import get_db
from app.models.app_setting import AppSetting
from app.schemas.auth import UserInfo
from app.features.auth.dependencies import require_admin
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["Settings"])

# Setting keys
AUTO_CONFIRM_ADJUSTMENTS = "auto_confirm_adjustments"


class SettingResponse(BaseModel):
    key: str
    value: str


class SettingUpdateRequest(BaseModel):
    value: str


class AdjustmentSettingsResponse(BaseModel):
    auto_confirm_adjustments: bool


def get_setting(db: Session, key: str, default: str = "false") -> str:
    """Get a setting value by key."""
    setting = db.query(AppSetting).filter(AppSetting.key == key).first()
    return setting.value if setting else default


def set_setting(db: Session, key: str, value: str, username: str) -> AppSetting:
    """Set a setting value."""
    setting = db.query(AppSetting).filter(AppSetting.key == key).first()
    if setting:
        setting.value = value
        setting.updated_by = username
    else:
        setting = AppSetting(key=key, value=value, updated_by=username)
        db.add(setting)
    db.commit()
    db.refresh(setting)
    return setting


@router.get("/adjustments", response_model=AdjustmentSettingsResponse)
def get_adjustment_settings(
    db: Session = Depends(get_db),
    current_user: UserInfo = Depends(require_admin)
):
    """
    Get adjustment-related settings.

    **Requires:** Admin role
    """
    auto_confirm = get_setting(db, AUTO_CONFIRM_ADJUSTMENTS, "false")

    return AdjustmentSettingsResponse(
        auto_confirm_adjustments=auto_confirm.lower() == "true"
    )


@router.put("/adjustments/auto-confirm", response_model=AdjustmentSettingsResponse)
def update_auto_confirm_setting(
    request: SettingUpdateRequest,
    db: Session = Depends(get_db),
    current_user: UserInfo = Depends(require_admin)
):
    """
    Toggle auto-confirm for bodeguero adjustments.

    When enabled, adjustments submitted by bodegueros are automatically
    confirmed and executed in Odoo without requiring admin review.

    **Requires:** Admin role
    """
    value = request.value.lower()
    if value not in ("true", "false"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Value must be 'true' or 'false'"
        )

    logger.info(f"Admin {current_user.username} setting auto_confirm_adjustments to {value}")
    set_setting(db, AUTO_CONFIRM_ADJUSTMENTS, value, current_user.username)

    return AdjustmentSettingsResponse(
        auto_confirm_adjustments=value == "true"
    )
