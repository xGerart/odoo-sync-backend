"""
Authentication dependencies for FastAPI routes.
"""
from typing import List
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import decode_access_token
from app.core.constants import UserRole, AuthSource
from app.core.exceptions import AuthenticationError, AuthorizationError
from app.schemas.auth import UserInfo, TokenPayload
from app.features.auth.service import AuthService


# Security scheme for JWT bearer tokens
security = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> UserInfo:
    """
    Dependency to get current authenticated user from JWT token.

    Args:
        credentials: HTTP Authorization header with bearer token
        db: Database session

    Returns:
        User information from token

    Raises:
        HTTPException: If token is invalid or user not found

    Usage:
        @router.get("/me")
        def get_me(current_user: UserInfo = Depends(get_current_user)):
            return current_user
    """
    token = credentials.credentials

    # Decode token
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Extract user info from token
    try:
        token_data = TokenPayload(**payload)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Parse role and auth source
    try:
        role = UserRole(token_data.role)
        auth_source = AuthSource(token_data.auth_source)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token data",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # For database users, verify user still exists and is active
    if auth_source == AuthSource.DATABASE:
        try:
            user_id = int(token_data.sub)
            auth_service = AuthService(db)
            user = auth_service.get_user_by_id(user_id)

            if not user.is_active:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User account is disabled",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            return UserInfo(
                username=user.username,
                role=user.role,
                auth_source=AuthSource.DATABASE,
                full_name=user.full_name,
                user_id=user.id
            )
        except ValueError:
            # sub is not a valid user_id
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user ID in token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )

    # For Odoo users (admins), trust the token
    return UserInfo(
        username=token_data.username,
        role=role,
        auth_source=auth_source,
        full_name=None,
        user_id=None
    )


def require_role(allowed_roles: List[UserRole]):
    """
    Dependency factory to require specific roles.

    Args:
        allowed_roles: List of allowed roles

    Returns:
        Dependency function that checks user role

    Usage:
        @router.post("/admin-only")
        def admin_only(current_user: UserInfo = Depends(require_role([UserRole.ADMIN]))):
            return {"message": "Admin access granted"}

        @router.post("/warehouse")
        def warehouse_ops(
            current_user: UserInfo = Depends(require_role([UserRole.ADMIN, UserRole.BODEGUERO]))
        ):
            return {"message": "Warehouse access granted"}
    """
    def check_role(current_user: UserInfo = Depends(get_current_user)) -> UserInfo:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required roles: {[r.value for r in allowed_roles]}",
            )
        return current_user

    return check_role


# Convenience dependencies for common role checks
def require_admin(current_user: UserInfo = Depends(get_current_user)) -> UserInfo:
    """Require admin role."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


def require_admin_or_bodeguero(current_user: UserInfo = Depends(get_current_user)) -> UserInfo:
    """Require admin or bodeguero role."""
    if current_user.role not in [UserRole.ADMIN, UserRole.BODEGUERO]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or bodeguero access required",
        )
    return current_user


def require_admin_or_cajero(current_user: UserInfo = Depends(get_current_user)) -> UserInfo:
    """Require admin or cajero role."""
    if current_user.role not in [UserRole.ADMIN, UserRole.CAJERO]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or cajero access required",
        )
    return current_user


def require_bodeguero(current_user: UserInfo = Depends(get_current_user)) -> UserInfo:
    """Require bodeguero role only."""
    if current_user.role != UserRole.BODEGUERO:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bodeguero access required",
        )
    return current_user


def require_admin_or_bodeguero_or_cajero(current_user: UserInfo = Depends(get_current_user)) -> UserInfo:
    """Require admin, bodeguero, or cajero role (all roles)."""
    if current_user.role not in [UserRole.ADMIN, UserRole.BODEGUERO, UserRole.CAJERO]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin, bodeguero, or cajero access required",
        )
    return current_user
