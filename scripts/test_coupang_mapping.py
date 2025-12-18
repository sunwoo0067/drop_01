import sys
import os

# Add app to path
sys.path.append(os.getcwd())

from app.models import Product, MarketAccount
from app.coupang_sync import _map_product_to_coupang_payload

def test_payload_mapping():
    # Mock Product
    product = Product(
        name="테스트 상품",
        processed_name="가공된 테스트 상품",
        selling_price=10000,
        processed_image_urls=["http://img1.jpg", "http://img2.jpg", "http://img3.jpg"],
        brand="테스트브랜드"
    )
    
    # Mock Account
    account = MarketAccount(
        credentials={"vendor_id": "A0001", "vendor_user_id": "testuser"}
    )
    
    # Test mapping
    payload = _map_product_to_coupang_payload(
        product=product,
        account=account,
        return_center_code="R123",
        outbound_center_code="O123",
        predicted_category_code=77800,
        delivery_company_code="CJGLS" # 동적으로 조회된 상황 가정
    )
    
    # Assertions
    items = payload.get("items", [])
    assert len(items) == 1
    item = items[0]
    
    images = item.get("images", [])
    assert len(images) == 3
    
    # 1. Image Type Check
    rep_count = sum(1 for img in images if img.get("imageType") == "REPRESENTATION")
    det_count = sum(1 for img in images if img.get("imageType") == "DETAIL")
    
    print(f"REPRESENTATION images: {rep_count}")
    print(f"DETAIL images: {det_count}")
    
    assert rep_count == 1, "Should have exactly one REPRESENTATION image"
    assert det_count == 2, "Should have exactly two DETAIL images"
    assert images[0].get("imageType") == "REPRESENTATION", "First image should be REPRESENTATION"
    
    # 2. Delivery Company Check
    print(f"Delivery Company Code: {payload.get('deliveryCompanyCode')}")
    assert payload.get("deliveryCompanyCode") == "CJGLS", "Should use the passed delivery company code"
    
    print("Payload mapping test passed!")

if __name__ == "__main__":
    test_payload_mapping()
