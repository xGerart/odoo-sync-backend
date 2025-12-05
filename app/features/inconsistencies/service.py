"""
Inconsistencies detection service for finding and fixing data mismatches
between principal and branch locations.
"""
from typing import List
from app.infrastructure.odoo import OdooClient
from app.schemas.product import InconsistencyItem, InconsistencyResponse, FixInconsistencyItem
from app.core.constants import OdooModel, PRICE_TOLERANCE
from app.core.exceptions import OdooOperationError
from app.utils.formatters import format_decimal_for_odoo


class InconsistencyService:
    """Service for detecting and fixing data inconsistencies."""

    def __init__(self, principal_client: OdooClient, branch_client: OdooClient):
        """
        Initialize inconsistency service.

        Args:
            principal_client: Authenticated principal Odoo client
            branch_client: Authenticated branch Odoo client
        """
        self.principal_client = principal_client
        self.branch_client = branch_client

    def detect_inconsistencies(self) -> InconsistencyResponse:
        """
        Detect price and name inconsistencies between principal and branch.

        Returns:
            Inconsistency response with detected issues
        """
        try:
            # Get all products from principal
            principal_products = self.principal_client.search_read(
                OdooModel.PRODUCT_PRODUCT,
                domain=[['available_in_pos', '=', True], ['barcode', '!=', False]],
                fields=['id', 'name', 'barcode', 'list_price', 'standard_price', 'qty_available']
            )

            # Get all products from branch
            branch_products = self.branch_client.search_read(
                OdooModel.PRODUCT_PRODUCT,
                domain=[['available_in_pos', '=', True], ['barcode', '!=', False]],
                fields=['id', 'name', 'barcode', 'list_price', 'standard_price', 'qty_available']
            )

            # Create barcode mapping for branch products
            branch_map = {
                p['barcode']: p
                for p in branch_products
                if p.get('barcode')
            }

            # Find inconsistencies
            inconsistencies = []

            for principal_product in principal_products:
                barcode = principal_product.get('barcode')
                if not barcode:
                    continue

                branch_product = branch_map.get(barcode)
                if not branch_product:
                    continue  # Product doesn't exist in branch

                # Get prices and stock
                principal_list_price = principal_product.get('list_price', 0)
                sucursal_list_price = branch_product.get('list_price', 0)
                list_price_diff = abs(principal_list_price - sucursal_list_price)

                principal_standard_price = principal_product.get('standard_price', 0)
                sucursal_standard_price = branch_product.get('standard_price', 0)
                standard_price_diff = abs(principal_standard_price - sucursal_standard_price)

                principal_stock = principal_product.get('qty_available', 0)
                sucursal_stock = branch_product.get('qty_available', 0)

                # Check for name differences
                principal_name = principal_product.get('name', '')
                branch_name = branch_product.get('name', '')
                name_mismatch = principal_name != branch_name

                # Record if there's any inconsistency
                if list_price_diff > PRICE_TOLERANCE or standard_price_diff > PRICE_TOLERANCE or name_mismatch:
                    inconsistencies.append(InconsistencyItem(
                        barcode=barcode,
                        product_name=principal_name,
                        sucursal_id=branch_product['id'],
                        principal_list_price=principal_list_price,
                        sucursal_list_price=sucursal_list_price,
                        list_price_difference=list_price_diff,
                        principal_standard_price=principal_standard_price,
                        sucursal_standard_price=sucursal_standard_price,
                        standard_price_difference=standard_price_diff,
                        principal_stock=principal_stock,
                        sucursal_stock=sucursal_stock
                    ))

            return InconsistencyResponse(
                success=True,
                inconsistencies=inconsistencies,
                total_inconsistencies=len(inconsistencies)
            )

        except Exception as e:
            raise OdooOperationError(
                operation="detect_inconsistencies",
                message=str(e)
            )

    def fix_inconsistencies(self, items_to_fix: List[FixInconsistencyItem]) -> dict:
        """
        Fix detected inconsistencies by updating branch products.

        Args:
            items_to_fix: List of items to fix with new values

        Returns:
            Dictionary with fix results
        """
        fixed_count = 0
        errors = []

        for item in items_to_fix:
            try:
                # Build update data from provided fields
                update_data = {}

                if item.new_name is not None:
                    update_data['name'] = item.new_name

                if item.new_list_price is not None:
                    update_data['list_price'] = format_decimal_for_odoo(item.new_list_price)

                if item.new_standard_price is not None:
                    update_data['standard_price'] = format_decimal_for_odoo(item.new_standard_price)

                # Only update if there's something to update
                if update_data:
                    self.branch_client.write(
                        OdooModel.PRODUCT_PRODUCT,
                        [item.sucursal_id],
                        update_data
                    )
                    fixed_count += 1

            except Exception as e:
                errors.append(f"Failed to fix {item.barcode}: {str(e)}")

        return {
            'total_processed': len(items_to_fix),
            'fixed_count': fixed_count,
            'errors_count': len(errors),
            'errors': errors,
            'success': fixed_count > 0
        }
