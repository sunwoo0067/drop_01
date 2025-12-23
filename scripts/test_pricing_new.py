from app.services.pricing import calculate_selling_price

def test_pricing():
    # Test case 1: 계획서 예제
    cost = 10000
    margin = 0.15
    ship = 3000
    fee = 0.13
    price = calculate_selling_price(cost, margin, ship, fee)
    print(f"Case 1 (Plan Example): {price}")
    assert price == 16700

    # Test case 2: 소액 상품
    cost = 1000
    margin = 0.2
    ship = 3000
    fee = 0.13
    price = calculate_selling_price(cost, margin, ship, fee)
    # (1000 + 200 + 3000) / 0.87 = 4827.58... -> 4900
    print(f"Case 2 (Small Item): {price}")
    assert price == 4900

    # Test case 3: 고액 상품
    cost = 500000
    margin = 0.1
    ship = 0
    fee = 0.13
    price = calculate_selling_price(cost, margin, ship, fee)
    # (500000 + 50000 + 0) / 0.87 = 632183.9... -> 632200
    print(f"Case 3 (Large Item): {price}")
    assert price == 632200

    print("All tests passed!")

if __name__ == "__main__":
    test_pricing()
