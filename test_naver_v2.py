import requests
import time
import bcrypt
import base64
from app.session_factory import session_factory
from app.models import MarketAccount
from sqlalchemy import select

def test():
    with session_factory() as session:
        acc = session.execute(select(MarketAccount).where(MarketAccount.market_code == "SMARTSTORE")).scalars().first()
        cid = acc.credentials.get("client_id")
        secret = acc.credentials.get("client_secret")
        
        ts = str(int(time.time() * 1000))
        password = f"{cid}_{ts}"
        hashed = bcrypt.hashpw(password.encode('utf-8'), secret.encode('utf-8'))
        sig = base64.b64encode(hashed).decode('utf-8')
        
        r = requests.post("https://api.commerce.naver.com/external/v1/oauth2/token", data={
            "grant_type": "client_credentials",
            "client_id": cid,
            "timestamp": ts,
            "client_secret_sign": sig,
            "type": "SELF"
        })
        token = r.json().get("access_token")
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        
        # 1. Try V2 Registration (Simulated with minimal payload)
        payload = {
            "smartProduct": {
                "statusType": "SALE",
                "name": "API_TEST_PRODUCT",
                "salePrice": 10000,
                "stockQuantity": 100,
                "category": {"categoryId": "50000000"}
            }
        }
        
        r_v2 = requests.post("https://api.commerce.naver.com/external/v2/products", headers=headers, json=payload)
        print(f"V2 Reg Status: {r_v2.status_code}")
        print(f"V2 Reg Response: {r_v2.text[:300]}")

        # 2. Try searching products search (Wait, is it search?)
        # GET /external/v1/product-search/search
        r_search = requests.get("https://api.commerce.naver.com/external/v1/product-search/search", headers=headers)
        print(f"Search Status: {r_search.status_code}")
        print(f"Search Response: {r_search.text[:300]}")

if __name__ == "__main__":
    test()
