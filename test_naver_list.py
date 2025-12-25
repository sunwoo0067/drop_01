import requests
import time
import bcrypt
import base64
from app.session_factory import session_factory
from app.models import MarketAccount
from sqlalchemy import select

def test_list():
    with session_factory() as session:
        acc = session.execute(select(MarketAccount).where(MarketAccount.market_code == "SMARTSTORE")).scalars().first()
        cid = acc.credentials.get("client_id")
        secret = acc.credentials.get("client_secret")
        
        ts = str(int(time.time() * 1000))
        password = f"{cid}_{ts}"
        hashed = bcrypt.hashpw(password.encode('utf-8'), secret.encode('utf-8'))
        sig = base64.b64encode(hashed).decode('utf-8')
        
        # 1. Get Token
        r = requests.post("https://api.commerce.naver.com/external/v1/oauth2/token", data={
            "grant_type": "client_credentials",
            "client_id": cid,
            "timestamp": ts,
            "client_secret_sign": sig,
            "type": "SELF"
        })
        token = r.json().get("access_token")
        headers = {"Authorization": f"Bearer {token}"}
        
        # 2. Try V1 List
        r1 = requests.get("https://api.commerce.naver.com/external/v1/products", headers=headers, params={"page": 1, "size": 10})
        print(f"V1 List Status: {r1.status_code}")
        print(f"V1 List Response: {r1.text[:200]}")
        
        # 3. Try V2 List
        r2 = requests.get("https://api.commerce.naver.com/external/v2/products", headers=headers, params={"page": 1, "size": 10})
        print(f"V2 List Status: {r2.status_code}")
        print(f"V2 List Response: {r2.text[:200]}")

if __name__ == "__main__":
    test_list()
