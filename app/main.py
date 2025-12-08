"""
Odoo Sync API - Main application entry point.
FastAPI backend for syncing products and managing transfers between Odoo locations.
"""
import logging
import sys
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from contextlib import asynccontextmanager

from app.core.config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
from app.core.database import init_db, close_db
from app.core.exceptions import AppException
from app.middleware.error_handler import (
    app_exception_handler,
    http_exception_handler,
    validation_exception_handler,
    generic_exception_handler
)

# Import routers
from app.features.auth.router import router as auth_router
from app.features.products.router import router as products_router
from app.features.transfers.router import router as transfers_router
from app.features.adjustments.router import router as adjustments_router
from app.features.sales.router import router as sales_router
from app.features.inconsistencies.router import router as inconsistencies_router
from app.features.facturas.router import router as facturas_router

# Import Odoo connection
from app.infrastructure.odoo import odoo_manager
from app.schemas.common import HealthResponse, OdooCredentials


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown events.

    Args:
        app: FastAPI application instance
    """
    # Startup
    print(f"🚀 Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    print(f"📝 Environment: {settings.ENVIRONMENT}")

    # Initialize database
    try:
        init_db()
        print("✅ Database initialized")
    except Exception as e:
        print(f"⚠️  Database initialization warning: {e}")

    # Store config in app state for error handler
    app.state.config = settings

    # Auto-login to Principal Odoo
    if settings.ODOO_PRINCIPAL_URL and settings.ODOO_PRINCIPAL_USERNAME and settings.ODOO_PRINCIPAL_PASSWORD:
        try:
            print("🔐 Auto-connecting to Principal Odoo...")
            credentials = OdooCredentials(
                url=settings.ODOO_PRINCIPAL_URL,
                database=settings.ODOO_PRINCIPAL_DB,
                port=settings.ODOO_PRINCIPAL_PORT,
                username=settings.ODOO_PRINCIPAL_USERNAME,
                password=settings.ODOO_PRINCIPAL_PASSWORD,
                verify_ssl=True
            )
            odoo_manager.connect_principal(credentials)
            print(f"✅ Connected to Principal Odoo: {settings.ODOO_PRINCIPAL_URL}")
        except Exception as e:
            print(f"⚠️  Could not auto-connect to Principal Odoo: {e}")
            print(f"   Admin will need to login manually via /auth/login/odoo")
    else:
        print("⚠️  Principal Odoo credentials not configured")
        print("   Admin will need to login manually via /auth/login/odoo")

    yield

    # Shutdown
    print("🛑 Shutting down application")
    close_db()
    odoo_manager.disconnect_all()
    print("✅ Cleanup completed")


# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="API for syncing products and managing transfers between Odoo locations",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# Configure CORS with regex support for Vercel previews
import re

def is_allowed_origin(origin: str) -> bool:
    """Check if origin is allowed (supports Vercel preview URLs)."""
    allowed_patterns = [
        r"^http://localhost:3000$",
        r"^http://127\.0\.0\.1:3000$",
        r"^https://odoo-sync-frontend.*\.vercel\.app$",
    ]
    return any(re.match(pattern, origin) for pattern in allowed_patterns)

# Use allow_origin_regex for Vercel preview URLs
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https://odoo-sync-frontend.*\.vercel\.app",
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register exception handlers
app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)

# Register routers
app.include_router(auth_router, prefix="/api")
app.include_router(products_router, prefix="/api")
app.include_router(transfers_router, prefix="/api")
app.include_router(adjustments_router, prefix="/api")
app.include_router(sales_router, prefix="/api")
app.include_router(inconsistencies_router, prefix="/api")
app.include_router(facturas_router, prefix="/api")


@app.get("/", tags=["Root"])
async def root():
    """
    Root endpoint with API information.
    """
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "docs": "/docs",
        "health": "/health",
        "api_prefix": "/api"
    }


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """
    Health check endpoint.

    Returns API status and connection information.
    """
    # Check database connection
    database_connected = True
    try:
        from app.core.database import engine
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Database health check failed: {str(e)}")
        database_connected = False

    # Check Odoo connections
    connection_status = odoo_manager.get_connection_status()

    return HealthResponse(
        status="healthy" if database_connected else "degraded",
        version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT,
        database_connected=database_connected,
        odoo_principal_status="connected" if connection_status['principal']['connected'] else "disconnected",
        odoo_sucursal_status="connected" if connection_status['branch']['connected'] else "disconnected"
    )


@app.post("/api/odoo/connect/principal", tags=["Odoo Connection"])
async def connect_principal(credentials: dict):
    """
    Connect to principal Odoo instance.

    **Note:** Typically done via `/api/auth/login/odoo` for admin login.
    This endpoint is for testing connections.
    """
    from app.schemas.common import OdooCredentials

    try:
        creds = OdooCredentials(**credentials)
        result = odoo_manager.connect_principal(creds)

        return {
            "success": True,
            "message": "Connected to principal Odoo",
            "data": result
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": f"Connection failed: {str(e)}"
            }
        )


@app.post("/api/odoo/connect/branch", tags=["Odoo Connection"])
async def connect_branch(request: dict):
    """
    Connect to branch Odoo instance using location selector.

    Required for transfer and inconsistency operations.
    """
    from app.schemas.common import BranchConnectionRequest, OdooCredentials
    from app.core.locations import LocationService

    try:
        # Parse request
        branch_request = BranchConnectionRequest(**request)

        # Get location configuration
        location = LocationService.get_location_by_id(branch_request.location_id)
        if not location:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "message": f"Invalid location ID: {branch_request.location_id}"
                }
            )

        # Create credentials using location configuration
        creds = OdooCredentials(
            url=location.url,
            database=location.database,
            port=location.port,
            username=branch_request.username,
            password=branch_request.password,
            verify_ssl=branch_request.verify_ssl
        )

        result = odoo_manager.connect_branch(creds)

        return {
            "success": True,
            "message": f"Connected to {location.name}",
            "data": result
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": f"Connection failed: {str(e)}"
            }
        )


@app.get("/api/odoo/status", tags=["Odoo Connection"])
async def get_odoo_status():
    """
    Get Odoo connection status for both locations.
    """
    return odoo_manager.get_connection_status()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.ENVIRONMENT == "development"
    )
