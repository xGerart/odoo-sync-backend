"""
Authentication endpoints.
"""
from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.locations import LocationService, OdooLocation
from app.schemas.auth import LoginRequest, OdooLoginRequest, LoginResponse, UserInfo
from app.schemas.user import UserCreate, UserUpdate, UserResponse, UserListResponse
from app.schemas.common import MessageResponse, OdooCredentials
from app.features.auth.service import AuthService
from app.features.auth.dependencies import get_current_user, require_admin
from app.infrastructure.odoo import get_odoo_manager, OdooConnectionManager


router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.get("/locations", response_model=List[OdooLocation])
def get_locations():
    """
    Get available Odoo locations for login.

    Returns list of configured Odoo locations from environment.
    """
    return LocationService.get_available_locations()


@router.post("/login", response_model=LoginResponse)
def login_database(
    request: LoginRequest,
    db: Session = Depends(get_db)
):
    """
    Login with database credentials (cajero/bodeguero).

    - **username**: Username or email
    - **password**: Password

    Returns JWT token and user information.
    """
    auth_service = AuthService(db)
    return auth_service.login(request)


@router.post("/login/odoo", response_model=LoginResponse)
def login_odoo_admin(
    request: OdooLoginRequest,
    db: Session = Depends(get_db),
    manager: OdooConnectionManager = Depends(get_odoo_manager)
):
    """
    Login as administrator using Odoo credentials.

    - **username**: Odoo username
    - **password**: Odoo password
    - **odoo_url**: Odoo server URL
    - **odoo_database**: Odoo database name
    - **odoo_port**: Odoo server port (default: 443)
    - **verify_ssl**: Verify SSL certificate (default: true)

    Returns JWT token with admin role.
    """
    auth_service = AuthService(db)
    return auth_service.login_odoo(request, odoo_manager=manager)


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register_user(
    user_data: UserCreate,
    db: Session = Depends(get_db),
    current_user: UserInfo = Depends(require_admin)
):
    """
    Register a new cajero or bodeguero user.

    **Admin access required.**

    - **username**: Unique username (3-50 characters)
    - **email**: Valid email address
    - **password**: Password (min 8 characters)
    - **role**: User role (cajero or bodeguero)
    - **full_name**: Full name (optional)

    Returns created user information.
    """
    auth_service = AuthService(db)
    user = auth_service.register_user(user_data)
    return UserResponse.model_validate(user)


@router.get("/me", response_model=UserInfo)
def get_current_user_info(
    current_user: UserInfo = Depends(get_current_user)
):
    """
    Get current authenticated user information.

    Returns user details from JWT token.
    """
    return current_user


@router.post("/logout", response_model=MessageResponse)
def logout(
    current_user: UserInfo = Depends(get_current_user)
):
    """
    Logout current user.

    Note: Since we use stateless JWT tokens, this is mainly a placeholder.
    The frontend should delete the token from storage.

    In a production system, you might want to implement token blacklisting.
    """
    return MessageResponse(
        message="Logged out successfully",
        success=True
    )


@router.post("/users/{user_id}/deactivate", response_model=MessageResponse)
def deactivate_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: UserInfo = Depends(require_admin)
):
    """
    Deactivate a user account.

    **Admin access required.**

    - **user_id**: ID of user to deactivate

    Deactivated users cannot login until reactivated.
    """
    auth_service = AuthService(db)
    auth_service.deactivate_user(user_id)

    return MessageResponse(
        message=f"User {user_id} deactivated successfully",
        success=True
    )


@router.post("/users/{user_id}/activate", response_model=MessageResponse)
def activate_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: UserInfo = Depends(require_admin)
):
    """
    Activate a user account.

    **Admin access required.**

    - **user_id**: ID of user to activate

    Activated users can login normally.
    """
    auth_service = AuthService(db)
    auth_service.activate_user(user_id)

    return MessageResponse(
        message=f"User {user_id} activated successfully",
        success=True
    )


@router.get("/users", response_model=UserListResponse)
def list_users(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: UserInfo = Depends(require_admin)
):
    """
    List all users with pagination.

    **Admin access required.**

    - **skip**: Number of records to skip (default: 0)
    - **limit**: Maximum number of records (default: 100)

    Returns list of users and total count.
    """
    auth_service = AuthService(db)
    users, total = auth_service.get_all_users(skip=skip, limit=limit)

    return UserListResponse(
        users=[UserResponse.model_validate(u) for u in users],
        total=total
    )


@router.put("/users/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    user_data: UserUpdate,
    db: Session = Depends(get_db),
    current_user: UserInfo = Depends(require_admin)
):
    """
    Update a user's information.

    **Admin access required.**

    - **user_id**: ID of user to update
    - **email**: New email (optional)
    - **full_name**: New full name (optional)
    - **password**: New password (optional, min 8 characters)
    - **is_active**: Active status (optional)
    - **role**: New role (optional, cajero or bodeguero only)

    Returns updated user information.
    """
    auth_service = AuthService(db)
    user = auth_service.update_user(user_id, user_data)

    return UserResponse.model_validate(user)


@router.delete("/users/{user_id}", response_model=MessageResponse)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: UserInfo = Depends(require_admin)
):
    """
    Delete a user account.

    **Admin access required.**

    - **user_id**: ID of user to delete

    This is a permanent deletion.
    """
    auth_service = AuthService(db)
    auth_service.delete_user(user_id)

    return MessageResponse(
        message=f"User {user_id} deleted successfully",
        success=True
    )


@router.post("/connect/branch", response_model=MessageResponse)
def connect_branch(
    credentials: OdooCredentials,
    manager: OdooConnectionManager = Depends(get_odoo_manager),
    current_user: UserInfo = Depends(require_admin)
):
    """
    Connect to a branch Odoo instance.

    **Admin access required.**

    - **credentials**: Odoo credentials for branch

    This connection is required before confirming transfers.
    """
    import logging
    logger = logging.getLogger(__name__)

    try:
        logger.info(f"Attempting to connect to branch: {credentials.database} at {credentials.url}")
        result = manager.connect_branch(credentials)
        logger.info(f"Successfully connected to branch: {credentials.database}")
        return MessageResponse(
            message=f"Connected to branch: {credentials.database}",
            success=True
        )
    except Exception as e:
        logger.error(f"Failed to connect to branch: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        from fastapi import HTTPException
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to connect to branch: {str(e)}"
        )


@router.get("/connection/status")
def get_connection_status(
    manager: OdooConnectionManager = Depends(get_odoo_manager),
    current_user: UserInfo = Depends(get_current_user)
):
    """
    Get connection status for principal and branch.

    Returns:
    - Connection status for principal and branch
    - Database names and versions
    """
    return manager.get_connection_status()


@router.post("/disconnect/branch", response_model=MessageResponse)
def disconnect_branch(
    manager: OdooConnectionManager = Depends(get_odoo_manager),
    current_user: UserInfo = Depends(require_admin)
):
    """
    Disconnect from branch Odoo instance.

    **Admin access required.**
    """
    manager.disconnect_branch()
    return MessageResponse(
        message="Disconnected from branch successfully",
        success=True
    )
