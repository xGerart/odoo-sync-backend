"""
Custom exception classes for the application.
"""
from typing import Optional, Any, Dict
from fastapi import HTTPException, status


class AppException(Exception):
    """Base exception for application errors."""

    def __init__(
        self,
        message: str,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)


class AuthenticationError(AppException):
    """Raised when authentication fails."""

    def __init__(self, message: str = "Authentication failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            status_code=status.HTTP_401_UNAUTHORIZED,
            details=details
        )


class AuthorizationError(AppException):
    """Raised when user lacks required permissions."""

    def __init__(self, message: str = "Insufficient permissions", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            status_code=status.HTTP_403_FORBIDDEN,
            details=details
        )


class NotFoundError(AppException):
    """Raised when a resource is not found."""

    def __init__(self, resource: str, identifier: Any):
        super().__init__(
            message=f"{resource} not found: {identifier}",
            status_code=status.HTTP_404_NOT_FOUND,
            details={"resource": resource, "identifier": str(identifier)}
        )


class ValidationError(AppException):
    """Raised when input validation fails."""

    def __init__(self, message: str, field: Optional[str] = None):
        details = {"field": field} if field else {}
        super().__init__(
            message=message,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=details
        )


class OdooConnectionError(AppException):
    """Raised when Odoo connection fails."""

    def __init__(
        self,
        message: str = "Failed to connect to Odoo",
        details: Optional[Dict[str, Any]] = None,
        is_session_expired: bool = False
    ):
        # Use 401 for expired sessions, 503 for connection failures
        status_code = (
            status.HTTP_401_UNAUTHORIZED
            if is_session_expired
            else status.HTTP_503_SERVICE_UNAVAILABLE
        )
        super().__init__(
            message=message,
            status_code=status_code,
            details=details
        )


class OdooOperationError(AppException):
    """Raised when an Odoo operation fails."""

    def __init__(self, operation: str, message: str, details: Optional[Dict[str, Any]] = None):
        full_message = f"Odoo {operation} failed: {message}"
        super().__init__(
            message=full_message,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details=details or {"operation": operation}
        )


class ProductNotFoundError(NotFoundError):
    """Raised when a product is not found."""

    def __init__(self, identifier: Any):
        super().__init__(resource="Product", identifier=identifier)


class UserNotFoundError(NotFoundError):
    """Raised when a user is not found."""

    def __init__(self, identifier: Any):
        super().__init__(resource="User", identifier=identifier)


class DuplicateError(AppException):
    """Raised when attempting to create a duplicate resource."""

    def __init__(self, resource: str, field: str, value: Any):
        super().__init__(
            message=f"{resource} with {field}='{value}' already exists",
            status_code=status.HTTP_409_CONFLICT,
            details={"resource": resource, "field": field, "value": str(value)}
        )


class FileValidationError(AppException):
    """Raised when file validation fails."""

    def __init__(self, message: str):
        super().__init__(
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST
        )


class TransferError(AppException):
    """Raised when a transfer operation fails."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST,
            details=details
        )


class InsufficientStockError(TransferError):
    """Raised when there's insufficient stock for an operation."""

    def __init__(self, product_name: str, available: float, requested: float):
        super().__init__(
            message=f"Insufficient stock for {product_name}",
            details={
                "product": product_name,
                "available": available,
                "requested": requested
            }
        )


def exception_to_http_exception(exc: AppException) -> HTTPException:
    """
    Convert an AppException to FastAPI HTTPException.

    Args:
        exc: Application exception

    Returns:
        HTTPException with proper status code and detail
    """
    detail = {
        "message": exc.message,
        **exc.details
    }

    return HTTPException(
        status_code=exc.status_code,
        detail=detail
    )
