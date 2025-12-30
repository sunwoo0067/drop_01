import uuid
from sqlalchemy.orm import Session
from app.models import Product, ProductOption, SupplierItemRaw
from app.coupang_sync import _map_product_to_coupang_payload
from app.models import MarketAccount

def test_map_product_with_multiple_options():
    # 1. Setup Mock Account
    account = MarketAccount(
        market_code="coupang",
        name="Test Account",
        credentials={"vendor_id": "A00123456", "vendor_user_id": "test_user"},
        is_active=True
    )
    
    # 2. Setup Mock Product with Options
    product = Product(
        id=uuid.uuid4(),
        name="테스트 상품",
        processed_name="가공된 테스트 상품",
        brand="테스트브랜드",
        selling_price=15000
    )
    
    opt1 = ProductOption(
        id=uuid.uuid4(),
        option_name="색상",
        option_value="블랙",
        selling_price=15000,
        external_option_key="OPT_BLK"
    )
    opt2 = ProductOption(
        id=uuid.uuid4(),
        option_name="색상",
        option_value="화이트",
        selling_price=16000,
        external_option_key="OPT_WHT"
    )
    product.options = [opt1, opt2]
    
    # 3. Call Mapping Function
    # We need to mock some dependencies or provide enough data
    metadata = {
        "predicted_category_code": "123456",
        "delivery_company_code": "CJGLS",
        "return_center_code": "RET_01",
        "outbound_center_code": "OUT_01",
        "return_name": "반품지",
        "return_phone": "010-1234-5678",
        "return_zip": "12345",
        "return_addr": "서울시",
        "return_addr_detail": "강남구",
        "item_attributes": [],
        "item_certifications": [],
        "notices": [],
        "required_documents": []
    }
    
    payload = _map_product_to_coupang_payload(
        product, 
        account, 
        metadata["predicted_category_code"],
        metadata["item_attributes"],
        metadata["item_certifications"],
        metadata["notices"],
        metadata["required_documents"],
        metadata["delivery_company_code"],
        metadata["return_center_code"],
        metadata["outbound_center_code"],
        metadata["return_name"],
        metadata["return_phone"],
        metadata["return_zip"],
        metadata["return_addr"],
        metadata["return_addr_detail"]
    )
    
    # 4. Assertions
    assert len(payload["items"]) == 2
    assert payload["items"][0]["itemName"] == "가공된 테스트 상품 블랙"
    assert payload["items"][0]["salePrice"] == 15000
    assert payload["items"][1]["itemName"] == "가공된 테스트 상품 화이트"
    assert payload["items"][1]["salePrice"] == 16000
    assert payload["items"][0]["sellerItemCode"] == "OPT_BLK"
    assert payload["items"][1]["sellerItemCode"] == "OPT_WHT"
    print("Test passed: Multiple options correctly mapped to Coupang payload.")

if __name__ == "__main__":
    test_map_product_with_multiple_options()
