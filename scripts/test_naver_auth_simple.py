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
        sig = base64.urlsafe_b64encode(hmac.new(secret.encode("utf-8"), msg.encode("utf-8"), hashlib.sha256).digest()).decode("utf-8")
        
        url = "https://api.commerce.naver.com/external/v1/oauth2/token"
        data = {
            "grant_type": "client_credentials",
            "client_id": cid,
            "timestamp": timestamp,
            "client_secret_sign": sig,
            "type": "SELF"
        }
        print(f"Testing with URL-safe base64...")
        r = requests.post(url, data=data)
        print(f"Result: {r.status_code}, {r.text}")

if __name__ == "__main__":
    test_auth()
