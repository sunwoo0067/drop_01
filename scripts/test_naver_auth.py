import requests
import time
import hmac
import hashlib
import base64
from app.session_factory import session_factory
from app.models import MarketAccount
from sqlalchemy import select

def test_auth():
    with session_factory() as session:
        acc = session.execute(
            select(MarketAccount).where(MarketAccount.market_code == "SMARTSTORE")
        ).scalars().first()
        
        cid = acc.credentials.get("client_id")
        secret = acc.credentials.get("client_secret")
        
        timestamp = str(int(time.time() * 1000))
        msg = f"{cid}_{timestamp}"
        sig = base64.b64encode(hmac.new(secret.encode("utf-8"), msg.encode("utf-8"), hashlib.sha256).digest()).decode("utf-8")
        
        url = "https://api.commerce.naver.com/external/v1/oauth2/token"
        
        # 1. Standard POST form data
        data = {
            "grant_type": "client_credentials",
            "client_id": cid,
            "timestamp": timestamp,
            "client_secret_sign": sig,
            "type": "SELF"
        }
        print("Testing form data...")
        r1 = requests.post(url, data=data)
        print(f"R1: {r1.status_code}, {r1.text}")
        
        # 2. Add client_secret even if it seems redundant
        data2 = data.copy()
        data2["client_secret"] = secret
        print("Testing form data with secret...")
        r2 = requests.post(url, data=data2)
        print(f"R2: {r2.status_code}, {r2.text}")
        
        # 3. JSON payload? (Some APIs prefer it)
        print("Testing JSON...")
        r3 = requests.post(url, json=data)
        print(f"R3: {r3.status_code}, {r3.text}")

if __name__ == "__main__":
    test_auth()
