import sys
import os
import unittest
from unittest.mock import MagicMock
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.coupang_client import CoupangClient

class TestCoupangReturnAPIs(unittest.TestCase):
    def setUp(self):
        self.client = CoupangClient(
            access_key="test_access_key",
            secret_key="test_secret_key",
            vendor_id="A00012345"
        )
        self.client._request = MagicMock(return_value=(200, {"code": "SUCCESS", "data": []}))

    def test_get_return_requests(self):
        self.client.get_return_requests(
            created_at_from="2025-01-01T00:00",
            created_at_to="2025-01-02T00:00",
            status="UC"
        )
        args, kwargs = self.client._request.call_args
        self.assertEqual(args[0], "GET")
        self.assertEqual(args[1], "/v2/providers/openapi/apis/api/v6/vendors/A00012345/returnRequests")
        params = kwargs.get("params")
        self.assertEqual(params["createdAtFrom"], "2025-01-01T00:00")
        self.assertEqual(params["status"], "UC")
        self.assertEqual(params["searchType"], "timeFrame")

    def test_get_return_request(self):
        self.client.get_return_request(receipt_id=123456)
        args, kwargs = self.client._request.call_args
        self.assertEqual(args[0], "GET")
        self.assertEqual(args[1], "/v2/providers/openapi/apis/api/v6/vendors/A00012345/returnRequests/123456")

    def test_confirm_return_receipt(self):
        self.client.confirm_return_receipt(receipt_id=123456)
        args, kwargs = self.client._request.call_args
        self.assertEqual(args[0], "PUT")
        self.assertEqual(args[1], "/v2/providers/openapi/apis/api/v4/vendors/A00012345/returnRequests/123456/receiveConfirmation")
        payload = kwargs.get("payload")
        self.assertEqual(payload["receiptId"], 123456)

    def test_approve_return_request(self):
        self.client.approve_return_request(receipt_id=123456, cancel_count=1)
        args, kwargs = self.client._request.call_args
        self.assertEqual(args[0], "PUT")
        self.assertEqual(args[1], "/v2/providers/openapi/apis/api/v4/vendors/A00012345/returnRequests/123456/approval")
        payload = kwargs.get("payload")
        self.assertEqual(payload["cancelCount"], 1)

    def test_get_return_withdraw_requests(self):
        self.client.get_return_withdraw_requests(date_from="2025-01-01", date_to="2025-01-07")
        args, kwargs = self.client._request.call_args
        self.assertEqual(args[0], "GET")
        self.assertEqual(args[1], "/v2/providers/openapi/apis/api/v4/vendors/A00012345/returnWithdrawRequests")
        params = kwargs.get("params")
        self.assertEqual(params["dateFrom"], "2025-01-01")

    def test_get_return_withdraw_list(self):
        self.client.get_return_withdraw_list(cancel_ids=[123, 456])
        args, kwargs = self.client._request.call_args
        self.assertEqual(args[0], "POST")
        self.assertEqual(args[1], "/v2/providers/openapi/apis/api/v4/vendors/A00012345/returnWithdrawList")
        payload = kwargs.get("payload")
        self.assertEqual(payload["cancelIds"], [123, 456])

    def test_create_manual_return_invoice(self):
        self.client.create_manual_return_invoice(
            receipt_id=123456,
            return_exchange_delivery_type="RETURN",
            delivery_company_code="CJGLS",
            invoice_number="12345678"
        )
        args, kwargs = self.client._request.call_args
        self.assertEqual(args[0], "POST")
        self.assertEqual(args[1], "/v2/providers/openapi/apis/api/v4/vendors/A00012345/return-exchange-invoices/manual")
        payload = kwargs.get("payload")
        self.assertEqual(payload["deliveryCompanyCode"], "CJGLS")

if __name__ == "__main__":
    unittest.main()
