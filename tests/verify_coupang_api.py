import sys
import os
from datetime import datetime, timezone
import unittest
from unittest.mock import MagicMock, patch

# 프로젝트 루트 경로 추가
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# 가짜 의존성 주입 (import 에러 방지)
sys.modules['bs4'] = MagicMock()
sys.modules['httpx'] = MagicMock()
sys.modules['sqlalchemy'] = MagicMock()
sys.modules['sqlalchemy.dialects.postgresql'] = MagicMock()
sys.modules['sqlalchemy.orm'] = MagicMock()
sys.modules['sqlalchemy.sql'] = MagicMock()

from app.coupang_client import CoupangClient
from app.coupang_sync import sync_coupang_orders_raw

class TestCoupangOrderSync(unittest.TestCase):
    def setUp(self):
        self.access_key = "test_access"
        self.secret_key = "test_secret"
        self.vendor_id = "A00012345"
        self.client = CoupangClient(self.access_key, self.secret_key, self.vendor_id)

    def test_date_normalization_daily(self):
        """일 단위 페이징 조회 시 날짜 형식 확인"""
        with patch.object(self.client, "get") as mock_get:
            mock_get.return_value = (200, {"code": "SUCCESS", "data": []})
            
            # search_type=None (기본 Daily)
            self.client.get_order_sheets("2025-07-15", "2025-07-25", status="ACCEPT")
            
            args, kwargs = mock_get.call_args
            params = kwargs.get("params", {})
            self.assertEqual(params["createdAtFrom"], "2025-07-15+09:00")
            self.assertEqual(params["createdAtTo"], "2025-07-25+09:00")
            self.assertNotIn("searchType", params)

    def test_date_normalization_timeframe(self):
        """분 단위(timeFrame) 조회 시 날짜 형식 확인"""
        with patch.object(self.client, "get") as mock_get:
            mock_get.return_value = (200, {"code": "SUCCESS", "data": []})
            
            # search_type="timeFrame"
            self.client.get_order_sheets("2025-07-29T10:00", "2025-07-29T11:00", status="DEPARTURE", search_type="timeFrame")
            
            args, kwargs = mock_get.call_args
            params = kwargs.get("params", {})
            self.assertEqual(params["createdAtFrom"], "2025-07-29T10:00+09:00")
            self.assertEqual(params["createdAtTo"], "2025-07-29T11:00+09:00")
            self.assertEqual(params["searchType"], "timeFrame")

    def test_sync_auto_search_type(self):
        """sync_coupang_orders_raw에서 기간에 따라 search_type이 자동 선택되는지 확인"""
        mock_session = MagicMock()
        mock_account = MagicMock()
        mock_account.id = "test-uuid"
        mock_account.market_code = "COUPANG"
        mock_account.is_active = True
        mock_account.credentials = {
            "access_key": "ak",
            "secret_key": "sk",
            "vendor_id": "v"
        }
        mock_session.get.return_value = mock_account

        with patch("app.coupang_sync._get_client_for_account") as mock_get_client:
            mock_client = MagicMock()
            mock_get_client.return_value = mock_client
            mock_client.get_order_sheets.return_value = (200, {"code": "SUCCESS", "data": []})

            # 1. 24시간 이내 (timeFrame 기대)
            sync_coupang_orders_raw(mock_session, mock_account.id, "2025-07-29T00:00", "2025-07-29T12:00")
            call_args = mock_client.get_order_sheets.call_args_list[0]
            self.assertEqual(call_args.kwargs["search_type"], "timeFrame")

            mock_client.get_order_sheets.reset_mock()

            # 2. 24시간 초과 (Daily paging 기대)
            sync_coupang_orders_raw(mock_session, mock_account.id, "2025-07-01", "2025-07-10")
            call_args = mock_client.get_order_sheets.call_args_list[0]
            self.assertIsNone(call_args.kwargs["search_type"])

    def test_response_parsing_robustness(self):
        """다양한 응답 구조(v5 list vs v4/v5 content) 파싱 확인"""
        mock_session = MagicMock()
        mock_account = MagicMock()
        mock_account.market_code = "COUPANG"
        mock_account.is_active = True
        mock_account.credentials = {"access_key": "ak", "secret_key": "sk", "vendor_id": "v"}
        mock_session.get.return_value = mock_account

        with patch("app.coupang_sync._get_client_for_account") as mock_get_client:
            mock_client = MagicMock()
            mock_get_client.return_value = mock_client
            
            # v5 스타일 (data가 직접 리스트인 경우)
            mock_client.get_order_sheets.return_value = (200, {
                "code": "SUCCESS",
                "data": [{"orderId": 123, "status": "ACCEPT"}],
                "nextToken": "next123"
            })
            
            count = sync_coupang_orders_raw(mock_session, mock_account.id, "2025-07-01", "2025-07-01")
            self.assertEqual(count, 1)

if __name__ == "__main__":
    unittest.main()
