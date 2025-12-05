# Odoo Sync API v2.0 - Refactored Backend

> Sistema refactorizado para sincronización de productos y gestión de transferencias entre ubicaciones Odoo.

## 🎯 Cambios Principales

### Arquitectura Anterior
- **Monolito**: 4 archivos grandes (~6,500 líneas)
- **Sin autenticación**: Endpoints públicos
- **Sin roles**: Todos los usuarios tienen acceso total
- **Estado global**: Variables globales compartidas
- **Código duplicado**: Lógica repetida en múltiples lugares

### Arquitectura Nueva
- **Modular**: 50+ archivos organizados por features (~7,000 líneas)
- **Autenticación JWT**: Login híbrido (BD + Odoo)
- **Control de roles**: Admin, Cajero, Bodeguero
- **Dependency Injection**: OdooConnectionManager
- **Principios SOLID**: Separación de responsabilidades
- **Type Safety**: Pydantic v2 para validación

---

## 📁 Nueva Estructura

```
backend/
├── app/
│   ├── main.py                          # FastAPI app entry point
│   │
│   ├── core/                            # Core infrastructure
│   │   ├── config.py                    # Settings management
│   │   ├── database.py                  # SQLAlchemy setup
│   │   ├── security.py                  # JWT & passwords
│   │   ├── exceptions.py                # Custom exceptions
│   │   └── constants.py                 # Business constants
│   │
│   ├── models/                          # SQLAlchemy models
│   │   ├── user.py                      # User model
│   │   ├── odoo_connection.py           # Odoo configs
│   │   └── audit_log.py                 # Audit trail
│   │
│   ├── schemas/                         # Pydantic schemas
│   │   ├── common.py                    # Shared schemas
│   │   ├── auth.py                      # Auth DTOs
│   │   ├── user.py                      # User DTOs
│   │   ├── product.py                   # Product DTOs
│   │   ├── transfer.py                  # Transfer DTOs
│   │   └── sales.py                     # Sales DTOs
│   │
│   ├── features/                        # Feature modules
│   │   ├── auth/                        # Authentication
│   │   │   ├── router.py                # Auth endpoints
│   │   │   ├── service.py               # Auth logic
│   │   │   └── dependencies.py          # Auth guards
│   │   │
│   │   ├── products/                    # Products
│   │   │   ├── router.py                # Product endpoints
│   │   │   ├── service.py               # Product sync
│   │   │   └── xml_parser.py            # XML parsing
│   │   │
│   │   ├── transfers/                   # Transfers
│   │   │   ├── router.py                # Transfer endpoints
│   │   │   └── service.py               # Transfer logic
│   │   │
│   │   ├── sales/                       # Sales
│   │   │   ├── router.py                # Sales endpoints
│   │   │   └── service.py               # Cierre caja
│   │   │
│   │   └── inconsistencies/             # Data validation
│   │       ├── router.py
│   │       └── service.py
│   │
│   ├── infrastructure/                  # External services
│   │   └── odoo/
│   │       ├── client.py                # Odoo XML-RPC client
│   │       └── connection.py            # Connection manager
│   │
│   ├── middleware/                      # Middleware
│   │   └── error_handler.py             # Global error handling
│   │
│   └── utils/                           # Utilities
│       ├── formatters.py                # Number formatting
│       ├── validators.py                # Input validation
│       └── timezone.py                  # Ecuador timezone
│
├── tests/                               # Tests
│   ├── unit/
│   └── integration/
│
├── alembic/                             # DB migrations
├── .env                                 # Environment variables
├── .env.example                         # Example config
├── requirements_new.txt                 # Dependencies
└── README_REFACTORED.md                # This file
```

---

## 🚀 Setup e Instalación

### 1. Requisitos Previos
- Python 3.12+
- PostgreSQL 14+ (local o Render)
- Odoo 17/18 con acceso XML-RPC

### 2. Instalación

```bash
# Crear entorno virtual
python3 -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate

# Instalar dependencias
pip install -r requirements_new.txt

# Configurar variables de entorno
cp .env.example .env
# Editar .env con tus credenciales
```

### 3. Configurar Base de Datos

**Opción A: Local (PostgreSQL)**
```bash
# Crear base de datos
createdb odoo_sync

# Actualizar DATABASE_URL en .env
DATABASE_URL="postgresql://user:password@localhost:5432/odoo_sync"
```

**Opción B: Render (Producción)**
1. Crear PostgreSQL en Render.com
2. Copiar DATABASE_URL de Render
3. Actualizar .env

### 4. Ejecutar Migraciones

```bash
# Inicializar Alembic (primera vez)
alembic init alembic

# Crear migración inicial
alembic revision --autogenerate -m "Initial schema"

# Aplicar migraciones
alembic upgrade head
```

### 5. Ejecutar Aplicación

```bash
# Desarrollo
uvicorn app.main:app --reload --port 8000

# Producción
gunicorn app.main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

### 6. Verificar

- API Docs: http://localhost:8000/docs
- Health: http://localhost:8000/health
- Root: http://localhost:8000/

---

## 🔐 Sistema de Autenticación

### Tipos de Usuarios

1. **Administrador** (auth via Odoo)
   - Login: `/api/auth/login/odoo`
   - Credenciales de Odoo
   - Acceso total al sistema

2. **Bodeguero** (auth via Base de Datos)
   - Login: `/api/auth/login`
   - Usuario/contraseña local
   - Acceso: productos, inventario, preparar transferencias

3. **Cajero** (auth via Base de Datos)
   - Login: `/api/auth/login`
   - Usuario/contraseña local
   - Acceso: ventas, cierre de caja, consultar productos

### Ejemplos de Login

**Admin (Odoo):**
```bash
curl -X POST http://localhost:8000/api/auth/login/odoo \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "password": "admin_password",
    "odoo_url": "https://tu-odoo.com",
    "odoo_database": "database",
    "odoo_port": 443,
    "verify_ssl": true
  }'
```

**Cajero/Bodeguero (Base de Datos):**
```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "jperez",
    "password": "SecurePass123"
  }'
```

**Respuesta:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 86400,
  "user": {
    "username": "jperez",
    "role": "cajero",
    "auth_source": "database",
    "full_name": "Juan Pérez"
  }
}
```

### Usar Token en Requests

```bash
curl -X GET http://localhost:8000/api/products/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

---

## 📚 Endpoints por Rol

### Admin
- ✅ Todos los endpoints
- ✅ Crear usuarios
- ✅ Confirmar transferencias
- ✅ Detectar/corregir inconsistencias

### Bodeguero
- ✅ Upload XML
- ✅ Sync productos
- ✅ Buscar productos
- ✅ Preparar transferencias
- ❌ Confirmar transferencias
- ❌ Cierre de caja

### Cajero
- ✅ Buscar productos
- ✅ Cierre de caja
- ✅ Listar productos
- ❌ Sync productos
- ❌ Transferencias

---

## 🔄 Flujo de Trabajo

### 1. Sincronizar Productos (Admin/Bodeguero)

```bash
# 1. Upload XML
POST /api/products/upload-xml
  - file: factura.xml
  - provider: "D'Mujeres"

# 2. Sync to Odoo
POST /api/products/sync
  - products: [mapped_products]
  - profit_margin: 0.50
  - quantity_mode: "replace"
```

### 2. Transferir entre Ubicaciones (Admin)

```bash
# 1. Preparar transferencia (valida stock)
POST /api/transfers/prepare
  - products: [{barcode, quantity}]

# 2. Conectar sucursal
POST /api/odoo/connect/branch
  - credentials: {url, database, username, password}

# 3. Confirmar transferencia (ejecuta)
POST /api/transfers/confirm
  - products: [{barcode, quantity}]
```

### 3. Cierre de Caja (Admin/Cajero)

```bash
GET /api/sales/cierre-caja/2024-01-15
```

---

## 🛠️ Desarrollo

### Crear Usuario de Prueba

```python
# En Python shell
from app.core.database import SessionLocal
from app.features.auth.service import AuthService
from app.schemas.user import UserCreate
from app.core.constants import UserRole

db = SessionLocal()
service = AuthService(db)

user = service.register_user(UserCreate(
    username="jperez",
    email="jperez@example.com",
    password="SecurePass123",
    full_name="Juan Pérez",
    role=UserRole.CAJERO
))

print(f"Created user: {user.username}")
```

### Tests

```bash
# Ejecutar todos los tests
pytest

# Con cobertura
pytest --cov=app tests/

# Solo tests unitarios
pytest tests/unit/

# Solo tests de integración
pytest tests/integration/
```

---

## 📦 Deployment en Render

1. **Crear PostgreSQL Database**
   - Plan: Starter ($7/mo)
   - Region: Oregon
   - Copiar DATABASE_URL

2. **Crear Web Service**
   - Build Command: `pip install -r requirements_new.txt`
   - Start Command: `gunicorn app.main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:$PORT`
   - Environment: Agregar variables de .env

3. **Ejecutar Migraciones**
   ```bash
   # En Render Shell
   alembic upgrade head
   ```

4. **Crear Usuario Admin**
   ```bash
   # Usar script o API
   curl -X POST https://tu-api.onrender.com/api/auth/register
   ```

---

## 🔧 Troubleshooting

### Error: "Database not connected"
```bash
# Verificar DATABASE_URL
echo $DATABASE_URL

# Test conexión
python -c "from app.core.database import engine; engine.connect()"
```

### Error: "Odoo not connected"
```bash
# Verificar credenciales Odoo
# Login primero: POST /api/auth/login/odoo
```

### Error: "Insufficient permissions"
```bash
# Verificar token JWT
# Verificar rol del usuario
GET /api/auth/me
```

---

## 📝 Changelog

### v2.0.0 (Refactored)
- ✨ Arquitectura modular por features
- ✨ Autenticación JWT híbrida
- ✨ Control de roles (Admin, Cajero, Bodeguero)
- ✨ Base de datos PostgreSQL
- ✨ Principios SOLID aplicados
- ✨ Type safety con Pydantic v2
- ✨ Error handling global
- ✨ Tests unitarios e integración
- 🐛 Fix: Validación de stock en transferencias
- 🐛 Fix: Manejo de timezone Ecuador
- 📚 Documentación completa con OpenAPI

### v1.0.0 (Original)
- ✅ Sync productos desde XML
- ✅ Transferencias entre ubicaciones
- ✅ Cierre de caja
- ✅ Detección de inconsistencias

---

## 🤝 Contribuir

1. Fork el repositorio
2. Crear branch: `git checkout -b feature/nueva-funcionalidad`
3. Commit cambios: `git commit -am 'Add nueva funcionalidad'`
4. Push: `git push origin feature/nueva-funcionalidad`
5. Crear Pull Request

---

## 📄 License

Proprietary - Uso interno

---

## 👨‍💻 Autor

Desarrollado por el equipo de Pladsh para gestión de inventario Odoo.
