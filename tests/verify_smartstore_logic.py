
import uuid

# Mocking the SmartStore payload builder logic
def mock_build_smartstore_payload(name, sale_price, options):
    origin_product = {
        "name": name,
        "salePrice": sale_price,
        "stockQuantity": 999
    }

    if options:
        first_opt_name = options[0].get("option_name", "옵션")
        group_names = [gn.strip() for gn in first_opt_name.split("/") if gn.strip()]
        
        combinations = []
        for idx, opt in enumerate(options):
            opt_val = opt.get("option_value", "단품")
            opt_vals = [v.strip() for v in opt_val.split("/") if v.strip()]
            while len(opt_vals) < len(group_names):
                opt_vals.append("-")
            opt_vals = opt_vals[:len(group_names)]
            
            combinations.append({
                "optionName1": opt_vals[0],
                "optionName2": opt_vals[1] if len(opt_vals) > 1 else None,
                "stockQuantity": opt.get("stock_quantity", 0),
                "price": opt.get("selling_price", 0) - sale_price,
                "sellerManagerCode": opt.get("external_option_key") or str(idx)
            })

        origin_product["optionInfo"] = {
            "optionCombinationGroupNames": {
                "optionGroupName1": group_names[0],
                "optionGroupName2": group_names[1] if len(group_names) > 1 else None,
            },
            "optionCombinations": combinations
        }
        origin_product["stockQuantity"] = 0

    return {"originProduct": origin_product}

def test_smartstore_option_logic():
    # Mock Data
    name = "기능성 티셔츠"
    sale_price = 15000 # 기준가
    options = [
        {"option_name": "색상/사이즈", "option_value": "블랙/L", "selling_price": 15000, "stock_quantity": 10, "external_option_key": "B-L"},
        {"option_name": "색상/사이즈", "option_value": "블랙/XL", "selling_price": 16000, "stock_quantity": 5, "external_option_key": "B-XL"},
        {"option_name": "색상/사이즈", "option_value": "화이트/L", "selling_price": 15000, "stock_quantity": 20, "external_option_key": "W-L"}
    ]

    # Execute
    payload = mock_build_smartstore_payload(name, sale_price, options)
    origin = payload["originProduct"]
    opt_info = origin["optionInfo"]

    # Assertions
    print(f"Base Price: {origin['salePrice']}")
    print(f"Base Stock: {origin['stockQuantity']} (Should be 0 if options exist)")
    print(f"Option Groups: {opt_info['optionCombinationGroupNames']}")
    
    for i, comb in enumerate(opt_info["optionCombinations"]):
        print(f"Comb {i+1}: {comb['optionName1']}/{comb['optionName2']} - Price Offset: {comb['price']}원 (Total: {sale_price + comb['price']})")

    assert origin["stockQuantity"] == 0
    assert opt_info["optionCombinationGroupNames"]["optionGroupName1"] == "색상"
    assert opt_info["optionCombinationGroupNames"]["optionGroupName2"] == "사이즈"
    assert len(opt_info["optionCombinations"]) == 3
    assert opt_info["optionCombinations"][1]["price"] == 1000 # 16000 - 15000
    
    print("Success: SmartStore multi-option logic verified.")

if __name__ == "__main__":
    test_smartstore_option_logic()
