"""
Script para buscar productos por nombre en Odoo
Busca en múltiples modelos y campos para encontrar dónde está el nombre
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.infrastructure.odoo.client import OdooClient
from app.core.config import settings
from app.core.constants import OdooModel
from app.schemas.common import OdooCredentials

def search_by_name(search_name: str):
    """Busca productos por nombre en diferentes modelos"""

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

    print(f"\n🔍 Buscando: '{search_name}'")
    print("=" * 80)

    # 1. Buscar en product.product por nombre
    print(f"\n📦 BÚSQUEDA EN PRODUCT.PRODUCT")
    print("=" * 80)

    product_ids = client.search(
        OdooModel.PRODUCT_PRODUCT,
        [['name', 'ilike', search_name]]
    )

    print(f"Productos encontrados: {len(product_ids)}")
    if product_ids:
        products_data = client.read(
            OdooModel.PRODUCT_PRODUCT,
            product_ids,
            fields=['id', 'name', 'display_name', 'barcode', 'product_tmpl_id', 'partner_ref']
        )
        for product in products_data:
            print(f"\n  ID: {product['id']}")
            print(f"  Barcode: {product.get('barcode', 'N/A')}")
            print(f"  Name: {product.get('name')}")
            print(f"  Display Name: {product.get('display_name')}")
            print(f"  Partner Ref: {product.get('partner_ref')}")
            print(f"  Template ID: {product.get('product_tmpl_id')}")

    # 2. Buscar en product.template por nombre
    print(f"\n📋 BÚSQUEDA EN PRODUCT.TEMPLATE")
    print("=" * 80)

    template_ids = client.search(
        OdooModel.PRODUCT_TEMPLATE,
        [['name', 'ilike', search_name]]
    )

    print(f"Templates encontrados: {len(template_ids)}")
    if template_ids:
        templates_data = client.read(
            OdooModel.PRODUCT_TEMPLATE,
            template_ids,
            fields=['id', 'name', 'display_name', 'default_code']
        )
        for template in templates_data:
            print(f"\n  ID: {template['id']}")
            print(f"  Name: {template.get('name')}")
            print(f"  Display Name: {template.get('display_name')}")
            print(f"  Default Code: {template.get('default_code')}")

    # 3. Buscar por display_name
    print(f"\n🔍 BÚSQUEDA EN PRODUCT.PRODUCT POR DISPLAY_NAME")
    print("=" * 80)

    product_ids_display = client.search(
        OdooModel.PRODUCT_PRODUCT,
        [['display_name', 'ilike', search_name]]
    )

    print(f"Productos encontrados: {len(product_ids_display)}")
    if product_ids_display:
        products_data_display = client.read(
            OdooModel.PRODUCT_PRODUCT,
            product_ids_display,
            fields=['id', 'name', 'display_name', 'barcode']
        )
        for product in products_data_display:
            print(f"\n  ID: {product['id']}")
            print(f"  Barcode: {product.get('barcode', 'N/A')}")
            print(f"  Name: {product.get('name')}")
            print(f"  Display Name: {product.get('display_name')}")

    # 4. Buscar por default_code (código interno)
    print(f"\n🔍 BÚSQUEDA EN PRODUCT.TEMPLATE POR DEFAULT_CODE")
    print("=" * 80)

    try:
        template_ids_code = client.search(
            OdooModel.PRODUCT_TEMPLATE,
            [['default_code', 'ilike', search_name]]
        )

        print(f"Templates encontrados: {len(template_ids_code)}")
        if template_ids_code:
            templates_data_code = client.read(
                OdooModel.PRODUCT_TEMPLATE,
                template_ids_code,
                fields=['id', 'name', 'display_name', 'default_code']
            )
            for template in templates_data_code:
                print(f"\n  ID: {template['id']}")
                print(f"  Name: {template.get('name')}")
                print(f"  Default Code: {template.get('default_code')}")
    except Exception as e:
        print(f"  Error buscando por default_code: {e}")

    # 5. Buscar el nombre antiguo específicamente
    print(f"\n🔍 COMPARACIÓN: ¿Dónde está el nombre ANTIGUO vs NUEVO?")
    print("=" * 80)

    old_name = "500 GRAMOS"
    new_name = "500G"

    # Buscar productos con "500 GRAMOS" en el nombre
    old_products = client.search(
        OdooModel.PRODUCT_PRODUCT,
        [['name', 'ilike', old_name], ['barcode', '=', '7861171202142']]
    )

    # Buscar productos con "500G" en el nombre
    new_products = client.search(
        OdooModel.PRODUCT_PRODUCT,
        [['name', 'ilike', new_name], ['barcode', '=', '7861171202142']]
    )

    print(f"Productos con '{old_name}' y barcode 7861171202142: {len(old_products)} - IDs: {old_products}")
    print(f"Productos con '{new_name}' y barcode 7861171202142: {len(new_products)} - IDs: {new_products}")

    if old_products:
        print(f"\n⚠️  ENCONTRADO producto con nombre ANTIGUO:")
        old_data = client.read(OdooModel.PRODUCT_PRODUCT, old_products, fields=['id', 'name', 'barcode', 'product_tmpl_id'])
        for prod in old_data:
            print(f"  ID: {prod['id']}, Name: {prod['name']}, Template: {prod.get('product_tmpl_id')}")

    if new_products:
        print(f"\n✅ ENCONTRADO producto con nombre NUEVO:")
        new_data = client.read(OdooModel.PRODUCT_PRODUCT, new_products, fields=['id', 'name', 'barcode', 'product_tmpl_id'])
        for prod in new_data:
            print(f"  ID: {prod['id']}, Name: {prod['name']}, Template: {prod.get('product_tmpl_id')}")

if __name__ == "__main__":
    # Buscar el nombre que aparece en el UI de Odoo
    search_name = "CREMA EXFOLIANTE PIES MOLLIE 500 GRAMOS"

    if len(sys.argv) > 1:
        search_name = " ".join(sys.argv[1:])

    search_by_name(search_name)
