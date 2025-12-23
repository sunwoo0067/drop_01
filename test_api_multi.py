
import json
from fastapi.testclient import TestClient
from app.main import app
from app.api.endpoints.settings import CoupangAccountIn
import uuid

client = TestClient(app)

def test_api_multi_active():
    print("--- Testing API Multi-Account Activation ---")
    
    # 1. Create Account A
    name_a = f"API_TEST_A_{uuid.uuid4().hex[:4]}"
    resp_a = client.post("/api/settings/markets/coupang/accounts", json={
        "name": name_a,
        "vendor_id": "V_A",
        "vendor_user_id": "VU_A",
        "access_key": "AK_A",
        "secret_key": "SK_A",
        "is_active": True
    })
    if resp_a.status_code != 200:
        print(f"Error creating A: {resp_a.status_code} {resp_a.text}")
        return
    id_a = resp_a.json()["id"]
    print(f"Created A: {name_a} (ID: {id_a}, isActive: {resp_a.json()['isActive']})")

    # 2. Create Account B
    name_b = f"API_TEST_B_{uuid.uuid4().hex[:4]}"
    resp_b = client.post("/api/settings/markets/coupang/accounts", json={
        "name": name_b,
        "vendor_id": "V_B",
        "vendor_user_id": "VU_B",
        "access_key": "AK_B",
        "secret_key": "SK_B",
        "is_active": True
    })
    if resp_b.status_code != 200:
        print(f"Error creating B: {resp_b.status_code} {resp_b.text}")
        return
    id_b = resp_b.json()["id"]
    print(f"Created B: {name_b} (ID: {id_b}, isActive: {resp_b.json()['isActive']})")

    # 3. List and check statuses
    resp_list = client.get("/api/settings/markets/coupang/accounts")
    accounts = resp_list.json()
    
    status_a = next(a["isActive"] for a in accounts if a["id"] == id_a)
    status_b = next(a["isActive"] for a in accounts if a["id"] == id_b)
    
    print(f"Status after both created active: A={status_a}, B={status_b}")
    
    if status_a and status_b:
        print("SUCCESS: Both active after creation.")
    else:
        print("FAILURE: One deactivated during creation.")

    # 4. Sequential Activation Test
    print("\n--- Sequential Activation via /activate ---")
    # Deactivate both first via PATCH
    client.patch(f"/api/settings/markets/coupang/accounts/{id_a}", json={"is_active": False})
    client.patch(f"/api/settings/markets/coupang/accounts/{id_b}", json={"is_active": False})
    
    # Activate A
    client.post(f"/api/settings/markets/coupang/accounts/{id_a}/activate")
    # Activate B
    client.post(f"/api/settings/markets/coupang/accounts/{id_b}/activate")
    
    resp_list = client.get("/api/settings/markets/coupang/accounts")
    accounts = resp_list.json()
    status_a = next(a["isActive"] for a in accounts if a["id"] == id_a)
    status_b = next(a["isActive"] for a in accounts if a["id"] == id_b)
    
    print(f"Status after sequential activation: A={status_a}, B={status_b}")
    
    if status_a and status_b:
        print("SUCCESS: Multi-account activation works via API.")
    else:
        print("FAILURE: API activation still deactivates others.")

if __name__ == "__main__":
    test_api_multi_active()
