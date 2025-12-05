"""
Sales service for cash register closing and sales reports.
"""
from typing import List, Dict, Any
from datetime import datetime
from app.infrastructure.odoo import OdooClient
from app.schemas.sales import (
    CierreCajaResponse,
    SaleByEmployee,
    PaymentMethodSummary,
    POSSession
)
from app.core.constants import OdooModel, PAYMENT_METHODS
from app.core.exceptions import OdooOperationError
from app.utils.timezone import get_date_range_ecuador, format_datetime_ecuador


class SalesService:
    """Service for sales operations and reports."""

    def __init__(self, odoo_client: OdooClient):
        """
        Initialize sales service.

        Args:
            odoo_client: Authenticated Odoo client
        """
        self.client = odoo_client

    def get_cierre_caja(self, date: str) -> CierreCajaResponse:
        """
        Get cash register closing report for a specific date in Ecuador timezone.

        Process:
        1. Receives date in Ecuador timezone (YYYY-MM-DD)
        2. Converts to full day range in Ecuador timezone (00:00:00 - 23:59:59)
        3. Converts to UTC for Odoo queries (Odoo stores in UTC)
        4. Queries Odoo for orders in that UTC range
        5. Converts response times back to Ecuador timezone for display

        Args:
            date: Date in format YYYY-MM-DD (Ecuador timezone)

        Returns:
            Cash closing report with sales by employee and payment methods
            (all times in Ecuador timezone)

        Raises:
            OdooOperationError: If query fails
        """
        try:
            # Get date range in Ecuador timezone (00:00:00 - 23:59:59 ECT)
            # Returns converted to UTC for Odoo queries
            start_dt, end_dt = get_date_range_ecuador(date)

            # Format as strings for Odoo (UTC timezone)
            start_str = start_dt.strftime("%Y-%m-%d %H:%M:%S")
            end_str = end_dt.strftime("%Y-%m-%d %H:%M:%S")

            # Get POS orders for the date
            orders = self.client.search_read(
                OdooModel.POS_ORDER,
                domain=[
                    ['date_order', '>=', start_str],
                    ['date_order', '<=', end_str],
                    ['state', 'in', ['paid', 'done', 'invoiced']]
                ],
                fields=['id', 'name', 'date_order', 'amount_total',
                        'user_id', 'payment_ids'],
                order='date_order asc'
            )

            # Calculate totals
            total_sales = sum(order.get('amount_total', 0) for order in orders)

            # Group by employee and payment method
            sales_by_employee = self._group_by_employee(orders)

            # Group by payment method
            payment_methods = self._group_by_payment_method(orders)

            # Get POS sessions for the date
            pos_sessions = self._get_pos_sessions(start_str, end_str)

            # Get first and last sale times (convert from UTC to Ecuador timezone)
            first_sale_time = None
            last_sale_time = None

            if orders:
                # Parse Odoo datetime (UTC) and convert to Ecuador timezone (HH:MM:SS)
                first_sale_time = format_datetime_ecuador(
                    datetime.strptime(orders[0]['date_order'], "%Y-%m-%d %H:%M:%S"),
                    format="%H:%M:%S"
                )
                last_sale_time = format_datetime_ecuador(
                    datetime.strptime(orders[-1]['date_order'], "%Y-%m-%d %H:%M:%S"),
                    format="%H:%M:%S"
                )

            return CierreCajaResponse(
                date=date,
                total_sales=total_sales,
                sales_by_employee=sales_by_employee,
                payment_methods=payment_methods,
                first_sale_time=first_sale_time,
                last_sale_time=last_sale_time,
                pos_sessions=pos_sessions
            )

        except Exception as e:
            raise OdooOperationError(
                operation="get_cierre_caja",
                message=str(e)
            )

    def _group_by_employee(self, orders: List[Dict]) -> List[SaleByEmployee]:
        """Group sales by employee and payment method."""
        # Get all payment IDs from orders
        payment_ids = []
        for order in orders:
            if order.get('payment_ids'):
                payment_ids.extend(order['payment_ids'])

        if not payment_ids:
            return []

        # Get payment details
        payments = self.client.read(
            OdooModel.POS_PAYMENT,
            payment_ids,
            fields=['amount', 'payment_method_id', 'pos_order_id']
        )

        # Create mapping of payment_method_id to name
        payment_method_ids = list(set(
            p['payment_method_id'][0]
            for p in payments
            if p.get('payment_method_id')
        ))

        payment_methods_data = self.client.read(
            'pos.payment.method',
            payment_method_ids,
            fields=['name']
        ) if payment_method_ids else []

        method_names = {
            pm['id']: pm['name']
            for pm in payment_methods_data
        }

        # Group by employee and NORMALIZED payment method
        grouped = {}

        for order in orders:
            user_name = order.get('user_id', [False, 'Unknown'])[1]

            # Get payments for this order
            order_payments = [
                p for p in payments
                if p.get('pos_order_id') and p['pos_order_id'][0] == order['id']
            ]

            for payment in order_payments:
                method_id = payment.get('payment_method_id', [False, 'Unknown'])[0]
                odoo_method_name = method_names.get(method_id, 'Unknown')

                # Normalize the payment method name
                normalized_name = self._normalize_payment_method_name(odoo_method_name)

                key = (user_name, normalized_name)

                if key not in grouped:
                    grouped[key] = {
                        'employee_name': user_name,
                        'payment_method': normalized_name,
                        'total_amount': 0,
                        'transaction_count': 0,
                        'first_sale_time': order.get('date_order')
                    }

                grouped[key]['total_amount'] += payment.get('amount', 0)
                grouped[key]['transaction_count'] += 1

        # Convert to list and format times in Ecuador timezone
        result = []
        for data in grouped.values():
            first_time = None
            if data['first_sale_time']:
                # Convert first sale time from UTC to Ecuador timezone (HH:MM:SS)
                first_time = format_datetime_ecuador(
                    datetime.strptime(data['first_sale_time'], "%Y-%m-%d %H:%M:%S"),
                    format="%H:%M:%S"
                )

            result.append(SaleByEmployee(
                employee_name=data['employee_name'],
                payment_method=data['payment_method'],
                total_amount=data['total_amount'],
                transaction_count=data['transaction_count'],
                first_sale_time=first_time
            ))

        return result

    def _normalize_payment_method_name(self, odoo_name: str) -> str:
        """
        Normalize Odoo payment method names to match frontend expectations.

        Maps:
        - "Banco" → "Transferencia"
        - "Efectivo", "Efectivo 2", etc. → "Efectivo"
        - Everything else → Keep as is
        """
        # Convert to lowercase for case-insensitive matching
        name_lower = odoo_name.lower()

        # Map bank transfers
        if 'banco' in name_lower or 'bank' in name_lower or 'transfer' in name_lower:
            return 'Transferencia'

        # Map cash variants to single "Efectivo"
        if 'efectivo' in name_lower or 'cash' in name_lower:
            return 'Efectivo'

        # Keep everything else as is (Datafast, etc.)
        return odoo_name

    def _group_by_payment_method(self, orders: List[Dict]) -> List[PaymentMethodSummary]:
        """Group sales by payment method."""
        # Get all payment IDs
        payment_ids = []
        for order in orders:
            if order.get('payment_ids'):
                payment_ids.extend(order['payment_ids'])

        if not payment_ids:
            return []

        # Get payments
        payments = self.client.read(
            OdooModel.POS_PAYMENT,
            payment_ids,
            fields=['amount', 'payment_method_id']
        )

        # Get method names
        payment_method_ids = list(set(
            p['payment_method_id'][0]
            for p in payments
            if p.get('payment_method_id')
        ))

        methods_data = self.client.read(
            'pos.payment.method',
            payment_method_ids,
            fields=['name']
        ) if payment_method_ids else []

        method_names = {pm['id']: pm['name'] for pm in methods_data}

        # Log payment methods for debugging
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Payment methods from Odoo: {method_names}")

        # Group by NORMALIZED method name
        grouped = {}
        for payment in payments:
            method_id = payment.get('payment_method_id', [False, 'Unknown'])[0]
            odoo_method_name = method_names.get(method_id, 'Unknown')

            # Normalize the payment method name
            normalized_name = self._normalize_payment_method_name(odoo_method_name)

            logger.info(f"Processing payment - method_id: {method_id}, odoo_name: {odoo_method_name}, normalized: {normalized_name}, amount: {payment.get('amount', 0)}")

            if normalized_name not in grouped:
                grouped[normalized_name] = {
                    'total': 0,
                    'count': 0
                }

            grouped[normalized_name]['total'] += payment.get('amount', 0)
            grouped[normalized_name]['count'] += 1

        # Convert to list
        result = [
            PaymentMethodSummary(
                method=method,
                total=data['total'],
                count=data['count']
            )
            for method, data in grouped.items()
        ]
        logger.info(f"Final payment methods summary: {[(r.method, r.total) for r in result]}")
        return result

    def _get_pos_sessions(self, start_str: str, end_str: str) -> List[POSSession]:
        """
        Get POS sessions for date range.

        Args:
            start_str: Start datetime in UTC format (YYYY-MM-DD HH:MM:SS)
            end_str: End datetime in UTC format (YYYY-MM-DD HH:MM:SS)

        Returns:
            List of POS sessions (start_at and stop_at remain in UTC,
            frontend will convert to Ecuador timezone for display)
        """
        try:
            sessions = self.client.search_read(
                OdooModel.POS_SESSION,
                domain=[
                    ['start_at', '>=', start_str],
                    ['start_at', '<=', end_str]
                ],
                fields=['id', 'name', 'state', 'user_id', 'start_at', 'stop_at',
                        'config_id', 'cash_register_balance_start',
                        'cash_register_balance_end_real']
            )

            result = []
            for session in sessions:
                # Convert UTC datetime strings from Odoo to ISO format with timezone
                # This ensures frontend correctly interprets the timezone
                start_at = session.get('start_at')
                stop_at = session.get('stop_at')

                # Convert to ISO format with UTC indicator if datetime exists
                if start_at and start_at is not False:
                    # Parse Odoo UTC datetime and convert to ISO with 'Z' indicator
                    dt = datetime.strptime(start_at, "%Y-%m-%d %H:%M:%S")
                    start_at = dt.strftime("%Y-%m-%dT%H:%M:%SZ")

                if stop_at and stop_at is not False:
                    dt = datetime.strptime(stop_at, "%Y-%m-%d %H:%M:%S")
                    stop_at = dt.strftime("%Y-%m-%dT%H:%M:%SZ")

                result.append(POSSession(
                    id=session['id'],
                    name=session['name'],
                    state=session.get('state', 'unknown'),
                    user_id=session.get('user_id', [0, 'Unknown'])[0],
                    user_name=session.get('user_id', [0, 'Unknown'])[1],
                    start_at=start_at,
                    stop_at=stop_at,
                    config_id=session.get('config_id', [0, 'Unknown'])[0],
                    config_name=session.get('config_id', [0, 'Unknown'])[1],
                    cash_register_balance_start=session.get('cash_register_balance_start', 0),
                    cash_register_balance_end_real=session.get('cash_register_balance_end_real')
                ))

            return result

        except Exception:
            return []
