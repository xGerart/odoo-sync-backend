"""
Script de diagnóstico para identificar todos los campos de un producto en Odoo
Busca por barcode y muestra todos los campos del producto y template
"""
import sys
import os

# Agregar el directorio padre al path para imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.infrastructure.odoo.client import OdooClient
from app.core.config import settings
from app.core.constants import OdooModel
from app.schemas.common import OdooCredentials

def debug_product_fields(barcode: str):
    """Muestra todos los campos de un producto y su template"""

    # Crear credenciales para Odoo Principal
    credentials = OdooCredentials(
        url=settings.ODOO_PRINCIPAL_URL,
        database=settings.ODOO_PRINCIPAL_DB,
        port=settings.ODOO_PRINCIPAL_PORT,
        username=settings.ODOO_PRINCIPAL_USERNAME,
        password=settings.ODOO_PRINCIPAL_PASSWORD,
        verify_ssl=True
    )

    # Crear cliente Odoo
    client = OdooClient(credentials)

    if not client.authenticate():
        print("❌ Error: No se pudo autenticar con Odoo")
        return

    print(f"\n🔍 Buscando producto con barcode: {barcode}")
    print("=" * 80)

    # Buscar producto por barcode
    product_ids = client.search(
        OdooModel.PRODUCT_PRODUCT,
        [['barcode', '=', barcode]]
    )

    if not product_ids:
        print(f"❌ No se encontró producto con barcode: {barcode}")
        return

    product_id = product_ids[0]
    print(f"\n✅ Producto encontrado - ID: {product_id}")

    # Leer TODOS los campos del producto
    print("\n" + "=" * 80)
    print("📦 PRODUCT.PRODUCT - TODOS LOS CAMPOS:")
    print("=" * 80)

    product_data = client.read(
        OdooModel.PRODUCT_PRODUCT,
        [product_id],
        fields=[]  # Lista vacía = todos los campos
    )

    if product_data:
        for key, value in sorted(product_data[0].items()):
            # Resaltar campos que contienen el texto del nombre
            if isinstance(value, str) and ('MOLLIE' in value.upper() or 'GRAMOS' in value.upper()):
                print(f"  🔴 {key}: {value}")
            elif 'name' in key.lower() or 'display' in key.lower():
                print(f"  🟡 {key}: {value}")
            else:
                # Solo mostrar campos relevantes para no saturar
                if key in ['id', 'barcode', 'product_tmpl_id', 'default_code', 'description',
                          'description_sale', 'description_purchase']:
                    print(f"  ⚪ {key}: {value}")

    # Obtener template_id
    template_id = product_data[0].get('product_tmpl_id')
    if isinstance(template_id, (list, tuple)):
        template_id = template_id[0]

    if not template_id:
        print("\n❌ No se pudo obtener el template_id")
        return

    # Leer TODOS los campos del template
    print("\n" + "=" * 80)
    print(f"📋 PRODUCT.TEMPLATE (ID: {template_id}) - TODOS LOS CAMPOS:")
    print("=" * 80)

    template_data = client.read(
        OdooModel.PRODUCT_TEMPLATE,
        [template_id],
        fields=[]  # Lista vacía = todos los campos
    )

    if template_data:
        for key, value in sorted(template_data[0].items()):
            # Resaltar campos que contienen el texto del nombre
            if isinstance(value, str) and ('MOLLIE' in value.upper() or 'GRAMOS' in value.upper()):
                print(f"  🔴 {key}: {value}")
            elif 'name' in key.lower() or 'display' in key.lower():
                print(f"  🟡 {key}: {value}")
            else:
                # Solo mostrar campos relevantes
                if key in ['id', 'default_code', 'description', 'description_sale',
                          'description_purchase', 'sale_description', 'purchase_description']:
                    print(f"  ⚪ {key}: {value}")

    print("\n" + "=" * 80)
    print("LEYENDA:")
    print("  🔴 = Campos que contienen 'MOLLIE' o 'GRAMOS' (el nombre del producto)")
    print("  🟡 = Campos con 'name' o 'display' en el nombre")
    print("  ⚪ = Otros campos relevantes")
    print("=" * 80)

if __name__ == "__main__":
    # Barcode del producto que estamos investigando
    barcode = "7861171202142"

    if len(sys.argv) > 1:
        barcode = sys.argv[1]

    debug_product_fields(barcode)
