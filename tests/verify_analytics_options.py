import sys
import os
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

# 프로젝트 루트 경로 추가
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.models import Product, ProductOption, Order, OrderItem
from app.services.sales_analytics_service import SalesAnalyticsService

def test_option_analytics():
    # 1. Mock DB Session
    mock_session = MagicMock()
    service = SalesAnalyticsService(mock_session)
    
    # 2. Mock Data
    product_id = uuid.uuid4()
    option_a_id = uuid.uuid4()
    option_b_id = uuid.uuid4()
    
    mock_product = Product(
        id=product_id,
        name="Test Product",
        cost_price=1500  # 기본 원가 (백업용)
    )
    
    option_a = ProductOption(
        id=option_a_id,
        product_id=product_id,
        option_name="Color",
        option_value="Red",
        cost_price=1000,  # 옵션 A 원가
        selling_price=5000
    )
    
    option_b = ProductOption(
        id=option_b_id,
        product_id=product_id,
        option_name="Color",
        option_value="Blue",
        cost_price=2000,  # 옵션 B 원가
        selling_price=6000
    )
    
    # Order & OrderItems
    order_id = uuid.uuid4()
    order = Order(id=order_id, created_at=datetime.now(timezone.utc))
    
    item_a = OrderItem(
        order_id=order_id,
        product_id=product_id,
        product_option_id=option_a_id,
        quantity=2,
        total_price=10000
    )
    
    item_b = OrderItem(
        order_id=order_id,
        product_id=product_id,
        product_option_id=option_b_id,
        quantity=1,
        total_price=6000
    )
    
    # Session side effects
    mock_session.get.side_effect = lambda model, oid: {
        Product: mock_product,
    }.get(model)
    
    # query execution simulation
    def make_result(items):
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = items
        mock_result.scalars.return_value = mock_scalars
        return mock_result
    
    # 3. Verify _collect_order_stats
    print("--- Testing _collect_order_stats ---")
    mock_session.execute.side_effect = [
        make_result([item_a, item_b]),  # OrderItem query
        make_result([option_a, option_b])  # ProductOption query
    ]
    stats = service._collect_order_stats(product_id, datetime.now(timezone.utc), datetime.now(timezone.utc))
    
    expected_revenue = 10000 + 6000 # 16000
    expected_cost = (1000 * 2) + (2000 * 1) # 4000
    expected_profit = expected_revenue - expected_cost # 12000
    
    print(f"Revenue: {stats['total_revenue']} (Expected: {expected_revenue})")
    print(f"Cost: {expected_cost} (Calculated internally)")
    print(f"Profit: {stats['total_profit']} (Expected: {expected_profit})")
    
    assert stats['total_revenue'] == expected_revenue
    assert stats['total_profit'] == expected_profit
    print("✓ _collect_order_stats success!")

    # 4. Verify get_option_performance
    print("\n--- Testing get_option_performance ---")
    mock_session.execute.side_effect = [
        make_result([item_a, item_b]),  # OrderItem query
        make_result([option_a, option_b])  # ProductOption query
    ]
    perf = service.get_option_performance(product_id)
    
    for p in perf:
        print(f"Option: {p['option_value']}, Qty: {p['total_quantity']}, Revenue: {p['total_revenue']}, Profit: {p['total_profit']}")
        if p['option_value'] == "Red":
            assert p['total_quantity'] == 2
            assert p['total_profit'] == 8000 # 10000 - (1000*2)
        if p['option_value'] == "Blue":
            assert p['total_quantity'] == 1
            assert p['total_profit'] == 4000 # 6000 - (2000*1)
            
    print("✓ get_option_performance success!")

if __name__ == "__main__":
    try:
        test_option_analytics()
        print("\nALL TESTS PASSED!")
    except Exception as e:
        print(f"\nTEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
