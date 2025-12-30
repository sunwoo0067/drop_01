import sys
import os
import unittest
from unittest.mock import MagicMock
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.coupang_client import CoupangClient

class TestCoupangExchangeAPIs(unittest.TestCase):
    def setUp(self):
        self.client = CoupangClient(
            access_key="test_access_key",
            secret_key="test_secret_key",
            vendor_id="A00012345"
        )
        self.client._request = MagicMock(return_value=(200, {"code": "SUCCESS", "data": []}))

    def test_get_exchange_requests(self):
        self.client.get_exchange_requests(
            created_at_from="2025-01-01T00:00:00",
            created_at_to="2025-01-02T00:00:00",
            status="PROGRESS"
        )
        args, kwargs = self.client._request.call_args
        self.assertEqual(args[0], "GET")
        self.assertEqual(args[1], "/v2/providers/openapi/apis/api/v4/vendors/A00012345/exchangeRequests")
        params = kwargs.get("params")
        self.assertEqual(params["createdAtFrom"], "2025-01-01T00:00:00")
        self.assertEqual(params["status"], "PROGRESS")

    def test_confirm_exchange_receipt(self):
        self.client.confirm_exchange_receipt(exchange_id=12345)
        args, kwargs = self.client._request.call_args
        self.assertEqual(args[0], "PUT")
        self.assertEqual(args[1], "/v2/providers/openapi/apis/api/v4/vendors/A00012345/exchangeRequests/12345/receiveConfirmation")
        payload = kwargs.get("payload")
        self.assertEqual(payload["exchangeId"], 12345)

    def test_reject_exchange_request(self):
        self.client.reject_exchange_request(exchange_id=12345, reject_code="SOLDOUT")
        args, kwargs = self.client._request.call_args
        self.assertEqual(args[0], "PUT")
        self.assertEqual(args[1], "/v2/providers/openapi/apis/api/v4/vendors/A00012345/exchangeRequests/12345/rejection")
        payload = kwargs.get("payload")
        self.assertEqual(payload["exchangeRejectCode"], "SOLDOUT")

    def test_upload_exchange_invoice(self):
        self.client.upload_exchange_invoice(
            exchange_id=12345,
            shipment_box_id=67890,
            delivery_company_code="CJGLS",
            invoice_number="12345678"
        )
        args, kwargs = self.client._request.call_args
        self.assertEqual(args[0], "POST")
        self.assertEqual(args[1], "/v2/providers/openapi/apis/api/v4/vendors/A00012345/exchangeRequests/12345/invoices")
        payload = kwargs.get("payload")
        self.assertIsInstance(payload, list)
        self.assertEqual(payload[0]["exchangeId"], "12345")
        self.assertEqual(payload[0]["goodsDeliveryCode"], "CJGLS")

if __name__ == "__main__":
    unittest.main()
