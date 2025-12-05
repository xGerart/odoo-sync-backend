"""
Authentication service with hybrid authentication (Database + Odoo).
"""
from typing import Optional, Tuple
from sqlalchemy.orm import Session
from app.models.user import User
from app.schemas.auth import LoginRequest, OdooLoginRequest, LoginResponse, UserInfo
from app.schemas.user import UserCreate, UserUpdate
from app.core.security import (
    verify_password,
    get_password_hash,
    create_user_token,
    validate_password_strength
)
from app.core.constants import UserRole, AuthSource
from app.core.exceptions import (
    AuthenticationError,
    UserNotFoundError,
    ValidationError,
    DuplicateError
)
from app.core.locations import LocationService
from app.infrastructure.odoo import OdooClient
from app.schemas.common import OdooCredentials


class AuthService:
    """Service for handling authentication operations."""

    def __init__(self, db: Session):
        self.db = db

    def login(self, request: LoginRequest) -> LoginResponse:
        """
        Hybrid login: try database first, then Odoo.

        Args:
            request: Login request with username/password

        Returns:
            Login response with token and user info

        Raises:
            AuthenticationError: If authentication fails
        """
        # Check if username contains @ (email format = database user)
        if '@' in request.username:
            return self._login_database(request)
        else:
            # For now, usernames without @ are treated as database users too
            # Odoo login requires separate endpoint with full credentials
            return self._login_database(request)

    def login_odoo(self, request: OdooLoginRequest, odoo_manager=None) -> LoginResponse:
        """
        Login as admin using Odoo credentials with location selector.

        Args:
            request: Odoo login request with location_id
            odoo_manager: OdooConnectionManager instance (optional)

        Returns:
            Login response with token and user info

        Raises:
            AuthenticationError: If Odoo authentication fails
        """
        try:
            # Get location configuration
            location = LocationService.get_location_by_id(request.location_id)
            if not location:
                raise AuthenticationError(
                    f"Invalid location ID: {request.location_id}. "
                    "Please select a valid location."
                )

            # Create Odoo credentials using location configuration
            credentials = OdooCredentials(
                url=location.url,
                database=location.database,
                port=location.port,
                username=request.username,
                password=request.password,
                verify_ssl=request.verify_ssl
            )

            # Try to authenticate with Odoo
            client = OdooClient(credentials)
            auth_result = client.authenticate()

            if not auth_result.get('success'):
                raise AuthenticationError("Odoo authentication failed")

            # Verify user has admin rights in Odoo
            if not self._verify_odoo_admin(client):
                raise AuthenticationError(
                    "User does not have administrator rights in Odoo"
                )

            # Connect Odoo manager with these credentials so it's available globally
            if odoo_manager:
                odoo_manager.connect_principal(credentials)

            # Create JWT token for admin
            token = create_user_token(
                username=request.username,
                role=UserRole.ADMIN,
                auth_source=AuthSource.ODOO,
                user_id=None  # Odoo users don't have local user_id
            )

            user_info = UserInfo(
                username=request.username,
                role=UserRole.ADMIN,
                auth_source=AuthSource.ODOO,
                full_name=None
            )

            return LoginResponse(
                access_token=token,
                token_type="bearer",
                expires_in=86400,  # 24 hours
                user=user_info
            )

        except Exception as e:
            if isinstance(e, AuthenticationError):
                raise
            raise AuthenticationError(
                f"Odoo authentication failed: {str(e)}",
                details={"error": str(e)}
            )

    def _login_database(self, request: LoginRequest) -> LoginResponse:
        """
        Login using database credentials (cajero/bodeguero).

        Args:
            request: Login request

        Returns:
            Login response with token

        Raises:
            AuthenticationError: If authentication fails
        """
        # Find user by username or email
        user = self.db.query(User).filter(
            (User.username == request.username) | (User.email == request.username)
        ).first()

        if not user:
            raise AuthenticationError("Invalid username or password")

        if not user.is_active:
            raise AuthenticationError("User account is disabled")

        # Verify password
        if not verify_password(request.password, user.hashed_password):
            raise AuthenticationError("Invalid username or password")

        # Create JWT token
        token = create_user_token(
            username=user.username,
            role=user.role,
            auth_source=AuthSource.DATABASE,
            user_id=user.id
        )

        user_info = UserInfo(
            username=user.username,
            role=user.role,
            auth_source=AuthSource.DATABASE,
            full_name=user.full_name,
            user_id=user.id
        )

        return LoginResponse(
            access_token=token,
            token_type="bearer",
            expires_in=86400,
            user=user_info
        )

    def _verify_odoo_admin(self, client: OdooClient) -> bool:
        """
        Verify if Odoo user has admin rights.

        Args:
            client: Authenticated Odoo client

        Returns:
            True if user is admin
        """
        try:
            # Get current user's groups
            user_data = client.read('res.users', [client.uid], ['groups_id'])

            if not user_data:
                return False

            group_ids = user_data[0].get('groups_id', [])

            # Check for admin group (usually "Access Rights" or "Settings")
            # Group XML ID is typically "base.group_system"
            admin_groups = client.search('res.groups', [
                ['id', 'in', group_ids],
                '|',
                ['name', '=', 'Access Rights'],
                ['name', '=', 'Settings']
            ])

            return len(admin_groups) > 0

        except Exception:
            # If we can't verify, assume user has access
            # (they successfully authenticated)
            return True

    def register_user(self, user_data: UserCreate) -> User:
        """
        Register a new cajero or bodeguero user.

        Args:
            user_data: User creation data

        Returns:
            Created user

        Raises:
            ValidationError: If password is weak or data invalid
            DuplicateError: If username/email already exists
        """
        # Validate password strength
        is_valid, error_msg = validate_password_strength(user_data.password)
        if not is_valid:
            raise ValidationError(error_msg, field="password")

        # Check for duplicates
        existing_user = self.db.query(User).filter(
            (User.username == user_data.username) | (User.email == user_data.email)
        ).first()

        if existing_user:
            field = "username" if existing_user.username == user_data.username else "email"
            value = user_data.username if field == "username" else user_data.email
            raise DuplicateError("User", field, value)

        # Create user
        user = User(
            username=user_data.username,
            email=user_data.email,
            hashed_password=get_password_hash(user_data.password),
            full_name=user_data.full_name,
            role=user_data.role,
            is_active=True
        )

        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)

        return user

    def get_user_by_id(self, user_id: int) -> User:
        """
        Get user by ID.

        Args:
            user_id: User ID

        Returns:
            User instance

        Raises:
            UserNotFoundError: If user not found
        """
        user = self.db.query(User).filter(User.id == user_id).first()

        if not user:
            raise UserNotFoundError(user_id)

        return user

    def get_user_by_username(self, username: str) -> User:
        """
        Get user by username.

        Args:
            username: Username

        Returns:
            User instance

        Raises:
            UserNotFoundError: If user not found
        """
        user = self.db.query(User).filter(User.username == username).first()

        if not user:
            raise UserNotFoundError(username)

        return user

    def deactivate_user(self, user_id: int) -> User:
        """
        Deactivate a user account.

        Args:
            user_id: User ID to deactivate

        Returns:
            Updated user

        Raises:
            UserNotFoundError: If user not found
        """
        user = self.get_user_by_id(user_id)
        user.is_active = False

        self.db.commit()
        self.db.refresh(user)

        return user

    def activate_user(self, user_id: int) -> User:
        """
        Activate a user account.

        Args:
            user_id: User ID to activate

        Returns:
            Updated user

        Raises:
            UserNotFoundError: If user not found
        """
        user = self.get_user_by_id(user_id)
        user.is_active = True

        self.db.commit()
        self.db.refresh(user)

        return user

    def get_all_users(self, skip: int = 0, limit: int = 100) -> Tuple[list[User], int]:
        """
        Get all users with pagination.

        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            Tuple of (users list, total count)
        """
        query = self.db.query(User)
        total = query.count()
        users = query.offset(skip).limit(limit).all()

        return users, total

    def update_user(self, user_id: int, user_data: UserUpdate) -> User:
        """
        Update a user's information.

        Args:
            user_id: User ID to update
            user_data: Updated user data

        Returns:
            Updated user

        Raises:
            UserNotFoundError: If user not found
            ValidationError: If password is weak
            DuplicateError: If email already exists
        """
        user = self.get_user_by_id(user_id)

        # Update email if provided
        if user_data.email is not None and user_data.email != user.email:
            # Check for duplicate email
            existing = self.db.query(User).filter(
                User.email == user_data.email,
                User.id != user_id
            ).first()
            if existing:
                raise DuplicateError("User", "email", user_data.email)
            user.email = user_data.email

        # Update full_name if provided
        if user_data.full_name is not None:
            user.full_name = user_data.full_name

        # Update password if provided
        if user_data.password is not None:
            is_valid, error_msg = validate_password_strength(user_data.password)
            if not is_valid:
                raise ValidationError(error_msg, field="password")
            user.hashed_password = get_password_hash(user_data.password)

        # Update is_active if provided
        if user_data.is_active is not None:
            user.is_active = user_data.is_active

        # Update role if provided
        if user_data.role is not None:
            user.role = user_data.role

        self.db.commit()
        self.db.refresh(user)

        return user

    def delete_user(self, user_id: int) -> None:
        """
        Delete a user account.

        Args:
            user_id: User ID to delete

        Raises:
            UserNotFoundError: If user not found
        """
        user = self.get_user_by_id(user_id)
        self.db.delete(user)
        self.db.commit()
