import sys
import os
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

# 프로젝트 루트 경로 추가
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.models import Product, ProductOption, Order, OrderItem, MarketOrderRaw, MarketListing
from app.smartstore_sync import SmartStoreSync, _extract_smartstore_order_items, _extract_smartstore_order_id, _extract_smartstore_product_id, _extract_smartstore_option_key

def test_smartstore_extraction_logic():
    print("--- Testing SmartStore Extraction Logic ---")
    
    # 1. Order Items Extraction
    raw_v1 = {"productOrderList": [{"productOrderId": "item1"}, {"productOrderId": "item2"}]}
    items = _extract_smartstore_order_items(raw_v1)
    assert len(items) == 2
    assert items[0]["productOrderId"] == "item1"
    
    raw_v2 = {"data": {"productOrders": [{"orderId": "o1"}]}}
    items = _extract_smartstore_order_items(raw_v2)
    assert len(items) == 1
    assert items[0]["orderId"] == "o1"
    print("✓ _extract_smartstore_order_items success!")

    # 2. Order ID Extraction
    assert _extract_smartstore_order_id({"orderId": "ORDER123"}) == "ORDER123"
    assert _extract_smartstore_order_id({}, {"productOrderId": "PORDER456"}) == "PORDER456"
    print("✓ _extract_smartstore_order_id success!")

    # 3. Product ID Extraction
    item = {"productId": "PROD999"}
    assert _extract_smartstore_product_id({}, item) == "PROD999"
    print("✓ _extract_smartstore_product_id success!")

    # 4. Option Key Extraction
    item_opt = {"optionManagementCode": "OPT_BLUE_L"}
    assert _extract_smartstore_option_key(item_opt) == "OPT_BLUE_L"
    print("✓ _extract_smartstore_option_key success!")

def test_smartstore_sync_orders():
    print("\n--- Testing SmartStoreSync.sync_orders ---")
    mock_session = MagicMock()
    sync = SmartStoreSync(mock_session)
    
    account_id = uuid.uuid4()
    row_id = uuid.uuid4()
    
    # Mock MarketOrderRaw
    mock_raw_row = MarketOrderRaw(
        id=row_id,
        market_code="SMARTSTORE",
        account_id=account_id,
        order_id="TEST_ORDER_001",
        raw={
            "orderId": "TEST_ORDER_001",
            "productOrderList": [
                {
                    "productOrderId": "ITEM_AAA",
                    "productId": "SS_PROD_1",
                    "optionManagementCode": "OPT_KEY_1",
                    "quantity": 2,
                    "unitPrice": 5000,
                    "totalPaymentAmount": 10000,
                    "productName": "Awesome Product"
                }
            ],
            "receiverName": "홍길동",
            "receiverAddress1": "서울시 강남구",
            "receiverZipCode": "12345"
        }
    )
    
    # Mock query for MarketOrderRaw
    mock_session.query.return_value.filter.return_value.filter.return_value.order_by.return_value.all.return_value = [mock_raw_row]
    
    # Mock existing order check (None)
    mock_session.query.return_value.filter.return_value.one_or_none.side_effect = [
        None, # existing_order
        MagicMock(id=uuid.uuid4(), product_id=uuid.uuid4()), # listing
        MagicMock(id=uuid.uuid4(), cost_price=3000, option_name="Size", option_value="L") # option_match
    ]
    
    # Run sync
    result = sync.sync_orders("SMARTSTORE", account_id)
    
    print(f"Sync Result: {result}")
    assert result["created"] == 1
    
    # Verify DB calls
    # 1. Order added
    added_objects = [call.args[0] for call in mock_session.add.call_args_list]
    order = next(obj for obj in added_objects if isinstance(obj, Order))
    print(f"Actual Order Number: {order.order_number}")
    assert order.order_number == "SS-TEST_ORDER_001"
    assert order.recipient_name == "홍길동"
    
    # 2. OrderItem added
    order_item = next(obj for obj in added_objects if isinstance(obj, OrderItem))
    assert order_item.product_name == "Awesome Product"
    assert order_item.quantity == 2
    assert order_item.total_price == 10000
    
    print("✓ SmartStoreSync.sync_orders success!")

if __name__ == "__main__":
    try:
        test_smartstore_extraction_logic()
        test_smartstore_sync_orders()
        print("\nALL TESTS PASSED!")
    except Exception as e:
        print(f"\nTEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
