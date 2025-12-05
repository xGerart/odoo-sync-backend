"""
Application configuration using Pydantic Settings.
Loads configuration from environment variables.
"""
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # App
    APP_NAME: str = "Odoo Sync API"
    APP_VERSION: str = "2.0.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # Database (SQLite for development, PostgreSQL for production)
    DATABASE_URL: str = "sqlite:///./odoo_sync.db"

    # Security
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours

    # CORS
    ALLOWED_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://odoo-sync-frontend.vercel.app",
        "https://odoo-sync-frontend-git-main-gerarts-projects.vercel.app"
    ]

    # Odoo Principal
    ODOO_PRINCIPAL_URL: str = ""
    ODOO_PRINCIPAL_DB: str = ""
    ODOO_PRINCIPAL_PORT: int = 443

    # Odoo Sucursal
    ODOO_SUCURSAL_URL: str = ""
    ODOO_SUCURSAL_DB: str = ""
    ODOO_SUCURSAL_PORT: int = 443

    # Odoo Sucursal Sacha
    ODOO_SUCURSAL_SACHA_URL: str = ""
    ODOO_SUCURSAL_SACHA_DB: str = ""
    ODOO_SUCURSAL_SACHA_PORT: int = 443

    # Business Rules
    IVA_RATE: float = 0.15
    DEFAULT_PROFIT_MARGIN: float = 0.50
    MAX_TRANSFER_PERCENTAGE: float = 0.50
    ECUADOR_TIMEZONE: str = "America/Guayaquil"

    # File Storage
    UPLOAD_DIR: str = "./uploads"
    PDF_DIR: str = "./pdfs"
    MAX_FILE_SIZE_MB: int = 10

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "logs/app.log"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        """Parse CORS origins from string or list."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v


# Global settings instance
settings = Settings()
