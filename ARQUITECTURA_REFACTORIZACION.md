# Arquitectura Backend Refactorizado - Odoo Sync

## 1. Esquema de Base de Datos (PostgreSQL)

### Tabla: `users`
```sql
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    full_name VARCHAR(100),
    role VARCHAR(20) NOT NULL CHECK (role IN ('cajero', 'bodeguero')),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_users_role ON users(role);
```

### Tabla: `odoo_connections` (Cache de conexiones)
```sql
CREATE TABLE odoo_connections (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL,  -- 'principal' o 'sucursal'
    url VARCHAR(255) NOT NULL,
    database VARCHAR(100) NOT NULL,
    port INTEGER DEFAULT 443,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Tabla: `audit_logs` (Opcional - para rastrear acciones)
```sql
CREATE TABLE audit_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    action VARCHAR(100) NOT NULL,
    resource VARCHAR(100),
    details JSONB,
    ip_address VARCHAR(45),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_audit_user ON audit_logs(user_id);
CREATE INDEX idx_audit_created ON audit_logs(created_at);
```

## 2. Arquitectura de Carpetas

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                      # FastAPI app initialization
│   │
│   ├── core/                        # Configuración central
│   │   ├── __init__.py
│   │   ├── config.py                # Settings con pydantic-settings
│   │   ├── security.py              # JWT utils, password hashing
│   │   ├── database.py              # SQLAlchemy setup
│   │   ├── exceptions.py            # Custom exceptions
│   │   └── constants.py             # IVA, margins, límites
│   │
│   ├── models/                      # SQLAlchemy ORM models
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── odoo_connection.py
│   │   └── audit_log.py
│   │
│   ├── schemas/                     # Pydantic schemas (DTOs)
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── auth.py
│   │   ├── product.py
│   │   ├── transfer.py
│   │   └── common.py
│   │
│   ├── features/                    # Feature-based modules
│   │   │
│   │   ├── auth/
│   │   │   ├── __init__.py
│   │   │   ├── router.py            # /auth/* endpoints
│   │   │   ├── service.py           # Business logic
│   │   │   ├── dependencies.py      # get_current_user, etc.
│   │   │   └── constants.py
│   │   │
│   │   ├── products/
│   │   │   ├── __init__.py
│   │   │   ├── router.py            # /products/* endpoints
│   │   │   ├── service.py           # Product sync logic
│   │   │   ├── dependencies.py      # Product-specific deps
│   │   │   └── xml_parser.py        # XML parsing (refactored)
│   │   │
│   │   ├── transfers/
│   │   │   ├── __init__.py
│   │   │   ├── router.py            # /transfers/* endpoints
│   │   │   ├── service.py           # Transfer logic
│   │   │   ├── dependencies.py
│   │   │   └── pdf_generator.py     # PDF generation
│   │   │
│   │   ├── sales/
│   │   │   ├── __init__.py
│   │   │   ├── router.py            # /sales/* endpoints
│   │   │   └── service.py
│   │   │
│   │   └── inconsistencies/
│   │       ├── __init__.py
│   │       ├── router.py
│   │       └── service.py
│   │
│   ├── infrastructure/              # Servicios externos
│   │   ├── __init__.py
│   │   ├── odoo/
│   │   │   ├── __init__.py
│   │   │   ├── client.py            # OdooClient refactorizado
│   │   │   ├── connection.py        # Connection manager
│   │   │   ├── exceptions.py        # Odoo-specific exceptions
│   │   │   └── models.py            # Odoo model wrappers
│   │   │
│   │   └── storage/
│   │       ├── __init__.py
│   │       └── file_storage.py      # PDF storage
│   │
│   ├── middleware/
│   │   ├── __init__.py
│   │   ├── auth.py                  # Auth middleware
│   │   ├── error_handler.py         # Global error handling
│   │   └── logging.py               # Request logging
│   │
│   └── utils/
│       ├── __init__.py
│       ├── formatters.py            # Number formatting
│       ├── validators.py            # Input validation
│       ├── timezone.py              # Ecuador timezone utils
│       └── pdf_utils.py             # Shared PDF utilities
│
├── alembic/                         # Database migrations
│   ├── versions/
│   └── env.py
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── unit/
│   │   ├── test_auth_service.py
│   │   ├── test_product_service.py
│   │   └── test_xml_parser.py
│   └── integration/
│       ├── test_auth_flow.py
│       └── test_product_sync.py
│
├── .env.example
├── .env
├── requirements.txt
├── pyproject.toml                   # Poetry config (opcional)
├── alembic.ini
└── README.md
```

## 3. Sistema de Autenticación Híbrido

### Flujo de Login

```mermaid
graph TD
    A[POST /auth/login] --> B{¿username tiene @ ?}
    B -->|Sí - Email| C[Buscar en BD local]
    B -->|No - Odoo user| D[Intentar auth con Odoo]

    C --> E{¿Usuario existe?}
    E -->|Sí| F[Verificar password]
    E -->|No| G[Return 401]

    F --> H{¿Password correcto?}
    H -->|Sí| I[Generar JWT]
    H -->|No| G

    D --> J{¿Auth exitoso en Odoo?}
    J -->|Sí| K[Verificar rol admin en Odoo]
    J -->|No| G

    K --> L{¿Es admin en Odoo?}
    L -->|Sí| I
    L -->|No| G

    I --> M[Return JWT + user info]
```

### Estructura del JWT Token

```json
{
  "sub": "user_id or odoo_username",
  "username": "john_doe",
  "role": "cajero | bodeguero | admin",
  "auth_source": "database | odoo",
  "exp": 1234567890,
  "iat": 1234567890
}
```

### Decoradores de Autorización

```python
from app.features.auth.dependencies import require_role

@router.post("/sync-products")
@require_role(["admin", "bodeguero"])
async def sync_products(...):
    ...

@router.get("/cierre-caja/{date}")
@require_role(["admin", "cajero"])
async def get_sales_report(...):
    ...

@router.post("/confirm-transfer")
@require_role(["admin"])  # Solo administradores
async def confirm_transfer(...):
    ...
```

## 4. Definición de Roles y Permisos

### Admin (Autenticado con Odoo)
- ✅ Configurar conexiones Odoo
- ✅ Sincronizar productos (XML upload)
- ✅ Crear/editar productos manualmente
- ✅ Preparar transferencias
- ✅ Confirmar transferencias
- ✅ Ver reportes de ventas
- ✅ Detectar y corregir inconsistencias
- ✅ Gestionar usuarios (cajeros/bodegueros)

### Bodeguero (Base de datos local)
- ✅ Sincronizar productos (XML upload)
- ✅ Ver inventario
- ✅ Preparar transferencias
- ❌ NO puede confirmar transferencias
- ✅ Ver productos
- ❌ NO puede ver reportes de ventas
- ❌ NO puede gestionar usuarios

### Cajero (Base de datos local)
- ✅ Ver reportes de ventas (cierre de caja)
- ✅ Buscar productos
- ✅ Ver inventario (solo lectura)
- ❌ NO puede sincronizar productos
- ❌ NO puede hacer transferencias
- ❌ NO puede gestionar usuarios

## 5. Endpoints Refactorizados

### Auth
```
POST   /auth/login                   # Login (híbrido)
POST   /auth/logout                  # Logout (invalidar token)
GET    /auth/me                      # Get current user
POST   /auth/register                # Registrar cajero/bodeguero (admin only)
```

### Products
```
POST   /products/upload-xml          # Upload XML (admin, bodeguero)
POST   /products/sync                # Sync products (admin, bodeguero)
POST   /products                     # Create product (admin)
GET    /products/search/{barcode}    # Search product (all)
PATCH  /products/{id}                # Update product (admin)
DELETE /products/{id}                # Delete product (admin)
```

### Transfers
```
POST   /transfers/prepare            # Prepare transfer (admin, bodeguero)
POST   /transfers/confirm            # Confirm transfer (admin only)
GET    /transfers                    # List transfers (admin, bodeguero)
GET    /transfers/{id}/pdf           # Download PDF (admin, bodeguero)
```

### Sales
```
GET    /sales/cierre-caja/{date}     # Cash closing (admin, cajero)
GET    /sales/summary                # Sales summary (admin)
```

### Inconsistencies
```
GET    /inconsistencies/detect       # Detect issues (admin)
POST   /inconsistencies/fix          # Fix issues (admin)
```

### Health
```
GET    /health                       # Health check (public)
GET    /                             # API info (public)
```

## 6. Configuración de Ambiente (.env)

```env
# App
APP_NAME="Odoo Sync API"
APP_VERSION="2.0.0"
ENVIRONMENT="development"  # development, staging, production

# Database
DATABASE_URL="postgresql://user:password@localhost:5432/odoo_sync"

# Security
SECRET_KEY="your-secret-key-here-change-in-production"
ALGORITHM="HS256"
ACCESS_TOKEN_EXPIRE_MINUTES=1440  # 24 horas

# CORS
ALLOWED_ORIGINS=["http://localhost:3000", "https://odoo-sync-frontend.vercel.app"]

# Odoo Principal (Default)
ODOO_PRINCIPAL_URL="https://principal.odoo.com"
ODOO_PRINCIPAL_DB="principal_db"
ODOO_PRINCIPAL_PORT=443

# Odoo Sucursal (Default)
ODOO_SUCURSAL_URL="https://sucursal.odoo.com"
ODOO_SUCURSAL_DB="sucursal_db"
ODOO_SUCURSAL_PORT=443

# Business Rules
IVA_RATE=0.15
DEFAULT_PROFIT_MARGIN=0.50
MAX_TRANSFER_PERCENTAGE=0.50
ECUADOR_TIMEZONE="America/Guayaquil"

# File Storage
UPLOAD_DIR="./uploads"
PDF_DIR="./pdfs"
MAX_FILE_SIZE_MB=10

# Logging
LOG_LEVEL="INFO"
LOG_FILE="logs/app.log"
```

## 7. Dependencias Actualizadas (requirements.txt)

```txt
# Web Framework
fastapi>=0.110.0
uvicorn[standard]>=0.27.0
gunicorn>=21.2.0
python-multipart>=0.0.9

# Database
sqlalchemy>=2.0.0
asyncpg>=0.29.0              # Async PostgreSQL driver
alembic>=1.13.0              # Database migrations
psycopg2-binary>=2.9.9       # PostgreSQL adapter

# Security
python-jose[cryptography]>=3.3.0  # JWT tokens
passlib[bcrypt]>=1.7.4            # Password hashing
python-dotenv>=1.0.0              # Environment variables

# Validation & Serialization
pydantic>=2.9.0
pydantic-settings>=2.0.0
email-validator>=2.1.0

# External APIs
requests>=2.31.0
xmltodict>=0.13.0

# PDF Generation
reportlab>=4.0.4

# Utilities
python-dateutil>=2.8.2
pytz>=2024.1

# Testing
pytest>=7.4.0
pytest-asyncio>=0.21.0
pytest-cov>=4.1.0
httpx>=0.25.0                # For testing FastAPI

# Code Quality
black>=23.0.0                # Code formatter
ruff>=0.1.0                  # Linter
mypy>=1.7.0                  # Type checking
```

## 8. Migración Gradual

### Paso 1: Setup inicial
1. Crear estructura de carpetas
2. Configurar PostgreSQL en Render
3. Configurar Alembic y crear migraciones
4. Implementar modelos SQLAlchemy

### Paso 2: Sistema de autenticación
1. Implementar auth service (login híbrido)
2. Crear JWT utils
3. Implementar middleware de autenticación
4. Crear dependencies para roles

### Paso 3: Refactorizar features
1. Migrar products (más simple)
2. Migrar transfers (más complejo)
3. Migrar sales
4. Migrar inconsistencies

### Paso 4: Testing y documentación
1. Crear tests unitarios
2. Crear tests de integración
3. Documentar API con OpenAPI
4. Actualizar README

## 9. Mejoras de Seguridad

1. **Rate Limiting**: Implementar con `slowapi`
2. **HTTPS Only**: Forzar HTTPS en producción
3. **SQL Injection**: Prevenido con SQLAlchemy ORM
4. **CORS**: Configuración estricta
5. **Input Validation**: Pydantic schemas
6. **Password Policy**: Mínimo 8 caracteres, complejidad
7. **Audit Logs**: Registrar acciones críticas
8. **Token Refresh**: Implementar refresh tokens
9. **Session Management**: Invalidar tokens en logout

## 10. Métricas de Mejora Esperadas

| Métrica | Antes | Después | Mejora |
|---------|-------|---------|--------|
| Archivos principales | 4 | ~40 | Modularidad |
| Líneas por archivo (avg) | 1,625 | ~150 | -90% |
| Cobertura de tests | 0% | >80% | +80% |
| Seguridad endpoints | 0/20 | 20/20 | 100% |
| Código duplicado | Alto | Bajo | -70% |
| Type safety | Parcial | Total | 100% |
| Documentación API | Auto | Auto + Manual | +100% |

---

**Próximos pasos**: Comenzar implementación con configuración de base de datos y modelos.
