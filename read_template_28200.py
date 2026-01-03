"""
Script simple para leer el template 28200 directamente
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.infrastructure.odoo.client import OdooClient
from app.core.config import settings
from app.core.constants import OdooModel
from app.schemas.common import OdooCredentials

credentials = OdooCredentials(
    url=settings.ODOO_PRINCIPAL_URL,
    database=settings.ODOO_PRINCIPAL_DB,
    port=settings.ODOO_PRINCIPAL_PORT,
    username=settings.ODOO_PRINCIPAL_USERNAME,
    password=settings.ODOO_PRINCIPAL_PASSWORD,
    verify_ssl=True
)

client = OdooClient(credentials)
client.authenticate()

print("\n" + "=" * 80)
print("LECTURA DIRECTA DEL TEMPLATE 28200")
print("=" * 80)

# Leer el template
template_data = client.read(
    OdooModel.PRODUCT_TEMPLATE,
    [28200],
    fields=['id', 'name', 'display_name', 'write_date']
)

if template_data:
    print(f"\nTemplate ID: {template_data[0]['id']}")
    print(f"Name: '{template_data[0]['name']}'")
    print(f"Display Name: '{template_data[0]['display_name']}'")
    print(f"Last Update: {template_data[0].get('__last_update', 'N/A')}")
    print(f"Write Date: {template_data[0].get('write_date', 'N/A')}")

    # Contar caracteres para ver si hay espacios ocultos
    print(f"\nLongitud del nombre: {len(template_data[0]['name'])} caracteres")
    print(f"Nombre en bytes: {template_data[0]['name'].encode('utf-8')}")

print("=" * 80)
