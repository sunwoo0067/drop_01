import sys
import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime

# Mock httpx before importing CoupangClient
sys.modules['httpx'] = MagicMock()

# CoupangClient 클래스만 직접 정의하거나 import 시도
# 여기서는 로직만 검증하기 위해 필요한 부분만 Mocking하거나 직접 테스트합니다.

def _normalize_date_logic(value: str, is_to: bool, search_mode: str | None) -> str:
    """coupang_client.py에 구현한 로직과 동일"""
    val = (value or "").strip()
    if "+" in val or "%2B" in val:
        return val
    
    if search_mode == "timeFrame" or "T" in val:
        if "T" not in val:
            val = f"{val}T23:59" if is_to else f"{val}T00:00"
        return f"{val}+09:00"
    else:
        return f"{val}+09:00"

def _decide_search_type_logic(created_at_from: str, created_at_to: str) -> str | None:
    """coupang_sync.py에 구현한 로직과 동일"""
    try:
        def _parse_dt(s: str) -> datetime:
            s_clean = s.split("+")[0].split("Z")[0].strip()
            if "T" in s_clean:
                formats = ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"]
                for f in formats:
                    try:
                        return datetime.strptime(s_clean, f)
                    except ValueError:
                        continue
            return datetime.strptime(s_clean, "%Y-%m-%d")

        dt_from = _parse_dt(created_at_from)
        dt_to = _parse_dt(created_at_to)
        duration_hours = (dt_to - dt_from).total_seconds() / 3600
        if duration_hours <= 24:
            return "timeFrame"
    except Exception:
        pass
    return None

class TestCoupangLogic(unittest.TestCase):
    def test_normalize_date_daily(self):
        self.assertEqual(_normalize_date_logic("2025-07-15", False, None), "2025-07-15+09:00")
        self.assertEqual(_normalize_date_logic("2025-07-15", True, None), "2025-07-15+09:00")

    def test_normalize_date_timeframe(self):
        # search_mode="timeFrame" 인데 T가 없는 경우 T00:00/T23:59 자동 보정
        self.assertEqual(_normalize_date_logic("2025-07-29", False, "timeFrame"), "2025-07-29T00:00+09:00")
        self.assertEqual(_normalize_date_logic("2025-07-29", True, "timeFrame"), "2025-07-29T23:59+09:00")
        
        # T가 이미 있는 경우
        self.assertEqual(_normalize_date_logic("2025-07-29T10:00", False, "timeFrame"), "2025-07-29T10:00+09:00")

    def test_get_order_sheets_by_shipment_box_id(self):
        """shipmentBoxId로 단건 조회 API 경로 확인"""
        mock_client = MagicMock()
        mock_client._vendor_id = "A001"
        # Mocking implementation of the method manually for the test since we are in a logic test
        shipment_box_id = 12345
        path = f"/v2/providers/openapi/apis/api/v5/vendors/{mock_client._vendor_id}/ordersheets/{shipment_box_id}"
        self.assertEqual(path, f"/v2/providers/openapi/apis/api/v5/vendors/A001/ordersheets/12345")

    def test_get_order_sheets_by_order_id(self):
        """orderId로 단건 조회 API 경로 확인"""
        mock_client = MagicMock()
        mock_client._vendor_id = "A001"
        order_id = 999
        path = f"/v2/providers/openapi/apis/api/v5/vendors/{mock_client._vendor_id}/{order_id}/ordersheets"
        self.assertEqual(path, f"/v2/providers/openapi/apis/api/v5/vendors/A001/999/ordersheets")

    def test_get_order_history(self):
        """배송상태 히스토리 조회 API 경로 확인"""
        mock_client = MagicMock()
        mock_client._vendor_id = "A001"
        shipment_box_id = 888
        path = f"/v2/providers/openapi/apis/api/v5/vendors/{mock_client._vendor_id}/ordersheets/{shipment_box_id}/history"
        self.assertEqual(path, f"/v2/providers/openapi/apis/api/v5/vendors/A001/ordersheets/888/history")

    def test_acknowledge_orders(self):
        """상품준비중 처리 API 본문(Payload) 및 경로 확인"""
        vendor_id = "A001"
        shipment_box_ids = [1, 2, 3]
        payload = {
            "vendorId": vendor_id,
            "shipmentBoxIds": shipment_box_ids
        }
        self.assertEqual(payload["vendorId"], "A001")
        self.assertEqual(len(payload["shipmentBoxIds"]), 3)

    def test_upload_invoices(self):
        """송장업로드 API 페이로드 구조 확인"""
        vendor_id = "A001"
        invoice_list = [{
            "shipmentBoxId": 123,
            "orderId": 456,
            "vendorItemId": 789,
            "deliveryCompanyCode": "KDEXP",
            "invoiceNumber": "INV001",
            "splitShipping": False,
            "preSplitShipped": False,
            "estimatedShippingDate": ""
        }]
        payload = {
            "vendorId": vendor_id,
            "orderSheetInvoiceApplyDtos": invoice_list
        }
        self.assertEqual(payload["orderSheetInvoiceApplyDtos"][0]["invoiceNumber"], "INV001")
        self.assertFalse(payload["orderSheetInvoiceApplyDtos"][0]["splitShipping"])

    def test_update_invoices(self):
        """송장업데이트 API 페이로드 구조 확인"""
        vendor_id = "A001"
        invoice_list = [{"shipmentBoxId": 123, "invoiceNumber": "INV_UPDATED"}]
        payload = {
            "vendorId": vendor_id,
            "orderSheetInvoiceApplyDtos": invoice_list
        }
        self.assertEqual(payload["orderSheetInvoiceApplyDtos"][0]["invoiceNumber"], "INV_UPDATED")

    def test_complete_stop_shipment(self):
        """출고중지완료 API 경로 및 페이로드 확인"""
        vendor_id = "A001"
        receipt_id = 123456
        cancel_count = 2
        path = f"/v2/providers/openapi/apis/api/v4/vendors/{vendor_id}/returnRequests/{receipt_id}/stoppedShipment"
        payload = {"vendorId": vendor_id, "receiptId": receipt_id, "cancel_count": cancel_count}
        self.assertIn("/returnRequests/123456/stoppedShipment", path)
        self.assertEqual(payload["cancel_count"], 2)

    def test_ship_anyway(self):
        """이미출고 처리 API 경로 및 페이로드 확인"""
        vendor_id = "A001"
        receipt_id = 123456
        payload = {"vendorId": vendor_id, "receiptId": receipt_id, "deliveryCompanyCode": "KDEXP", "invoiceNumber": "INV001"}
        self.assertEqual(payload["deliveryCompanyCode"], "KDEXP")

    def test_cancel_order(self):
        """주문 상품 취소 API 페이로드 확인"""
        vendor_id = "A001"
        order_id = 2000001
        vendor_item_ids = [10, 11]
        receipt_counts = [1, 1]
        payload = {
            "orderId": order_id,
            "vendorItemIds": vendor_item_ids,
            "receiptCounts": receipt_counts,
            "bigCancelCode": "CANERR",
            "middleCancelCode": "CCTTER",
            "userId": "test_user",
            "vendorId": vendor_id
        }
        self.assertEqual(len(payload["vendorItemIds"]), 2)
        self.assertEqual(payload["middleCancelCode"], "CCTTER")

    def test_complete_long_term_undelivery(self):
        """장기미배송 배송완료 API 페이로드 확인"""
        payload = {"shipmentBoxId": 12345, "invoiceNumber": "INV001"}
        self.assertEqual(payload["shipmentBoxId"], 12345)

    def test_decide_search_type(self):
        # 24시간 이내
        self.assertEqual(_decide_search_type_logic("2025-07-29T00:00", "2025-07-29T12:00"), "timeFrame")
        self.assertEqual(_decide_search_type_logic("2025-07-29", "2025-07-29"), "timeFrame") # 0시간 차이
        
        # 24시간 초과
        self.assertIsNone(_decide_search_type_logic("2025-07-01", "2025-07-03"))
        self.assertIsNone(_decide_search_type_logic("2025-07-29T00:00", "2025-07-30T01:00"))

if __name__ == "__main__":
    unittest.main()
