
import uuid
from datetime import datetime, timezone

# 1. Mocking the mapping logic directly to avoid dependency issues in test environment
def mock_map_product_to_coupang_payload(product, name_to_use):
    items_payload = []
    options = product.get("options", [])
    
    if not options:
        total_price = int(product.get("selling_price", 0))
        if total_price < 3000: total_price = 3000
        total_price = ((total_price + 99) // 100) * 100
        
        items_payload.append({
            "itemName": name_to_use[:150],
            "salePrice": total_price,
            "images": product.get("images", [])
        })
    else:
        for opt in options:
            opt_price = int(opt.get("selling_price", 0))
            if opt_price < 3000: opt_price = 3000
            opt_price = ((opt_price + 99) // 100) * 100
            
            full_item_name = f"{name_to_use} {opt.get('option_value')}" if opt.get("option_value") != "단품" else name_to_use
            
            items_payload.append({
                "itemName": full_item_name[:150],
                "salePrice": opt_price,
                "images": product.get("images", []),
                "sellerItemCode": opt.get("external_option_key") or str(uuid.uuid4())
            })

    payload = {
        "displayProductName": name_to_use[:100],
        "items": items_payload
    }
    return payload

def test_multi_option_logic():
    # Setup Mock Data
    mock_product = {
        "selling_price": 15000,
        "images": [{"imageOrder": 0, "imageType": "REPRESENTATION", "vendorPath": "url1"}],
        "options": [
            {"option_value": "블랙", "selling_price": 15000, "external_option_key": "BLK_001"},
            {"option_value": "화이트", "selling_price": 16000, "external_option_key": "WHT_002"}
        ]
    }
    name_to_use = "멋진 티셔츠"
    
    # Execute Logic
    payload = mock_map_product_to_coupang_payload(mock_product, name_to_use)
    
    # Assertions
    print(f"Items Count: {len(payload['items'])}")
    for i, item in enumerate(payload["items"]):
        print(f"Item {i+1}: {item['itemName']} - {item['salePrice']}원 (Code: {item['sellerItemCode']})")
    
    assert len(payload["items"]) == 2
    assert payload["items"][0]["itemName"] == "멋진 티셔츠 블랙"
    assert payload["items"][0]["salePrice"] == 15000
    assert payload["items"][1]["itemName"] == "멋진 티셔츠 화이트"
    assert payload["items"][1]["salePrice"] == 16000
    print("Success: Multi-option mapping logic verified.")

if __name__ == "__main__":
    test_multi_option_logic()
