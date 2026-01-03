"""
Script para verificar información sobre el campo 'name' en product.template
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.infrastructure.odoo.client import OdooClient
from app.core.config import settings
from app.core.constants import OdooModel
from app.schemas.common import OdooCredentials

def check_field_properties():
    """Verifica las propiedades del campo name en product.template"""

    credentials = OdooCredentials(
        url=settings.ODOO_PRINCIPAL_URL,
        database=settings.ODOO_PRINCIPAL_DB,
        port=settings.ODOO_PRINCIPAL_PORT,
        username=settings.ODOO_PRINCIPAL_USERNAME,
        password=settings.ODOO_PRINCIPAL_PASSWORD,
        verify_ssl=True
    )

    client = OdooClient(credentials)

    if not client.authenticate():
        print("❌ Error: No se pudo autenticar con Odoo")
        return

    print(f"\n🔍 Verificando propiedades del modelo product.template")
    print("=" * 80)

    try:
        # Get field information using fields_get
        fields_info = client.execute_kw(
            OdooModel.PRODUCT_TEMPLATE,
            'fields_get',
            [],
            {'attributes': ['string', 'help', 'type', 'readonly', 'required', 'store', 'compute']}
        )

        if 'name' in fields_info:
            print("\n📋 Información del campo 'name':")
            print("=" * 80)
            for key, value in fields_info['name'].items():
                print(f"  {key}: {value}")

        if 'display_name' in fields_info:
            print("\n📋 Información del campo 'display_name':")
            print("=" * 80)
            for key, value in fields_info['display_name'].items():
                print(f"  {key}: {value}")

        # Check product.product as well
        print(f"\n🔍 Verificando propiedades del modelo product.product")
        print("=" * 80)

        fields_info_product = client.execute_kw(
            OdooModel.PRODUCT_PRODUCT,
            'fields_get',
            [],
            {'attributes': ['string', 'help', 'type', 'readonly', 'required', 'store', 'compute', 'related']}
        )

        if 'name' in fields_info_product:
            print("\n📋 Información del campo 'name':")
            print("=" * 80)
            for key, value in fields_info_product['name'].items():
                print(f"  {key}: {value}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_field_properties()
