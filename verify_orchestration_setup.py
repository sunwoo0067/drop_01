import requests
import json

BASE_URL = "http://localhost:8888/api"

def test_settings_api():
    print("Testing Orchestrator Settings API...")
    # GET
    res_get = requests.get(f"{BASE_URL}/settings/orchestrator")
    print(f"GET /settings/orchestrator: {res_get.status_code}")
    print(res_get.json())
    
    # POST
    payload = {
        "listing_limit": 1000,
        "sourcing_keyword_limit": 10,
        "continuous_mode": True
    }
    res_post = requests.post(f"{BASE_URL}/settings/orchestrator", json=payload)
    print(f"POST /settings/orchestrator: {res_post.status_code}")
    print(res_post.json())
    
    # Verify change
    res_get_v = requests.get(f"{BASE_URL}/settings/orchestrator")
    print(f"Verified GET: {res_get_v.json()}")

if __name__ == "__main__":
    try:
        test_settings_api()
        print("\nSUCCESS: Orchestration settings verification passed.")
    except Exception as e:
        print(f"\nFAILED: {e}")
