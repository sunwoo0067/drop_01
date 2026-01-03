import bcrypt
import base64
import time
import requests
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
        
        print(f"Testing with Bcrypt logic...")
        print(f"CID: {cid}")
        print(f"Secret Prefix: {secret[:10]}...")
        
        timestamp = str(int(time.time() * 1000))
        password = f"{cid}_{timestamp}"
        
        # BCrypt hashing
        hashed = bcrypt.hashpw(password.encode('utf-8'), secret.encode('utf-8'))
        # Base64 encoding
        sig = base64.b64encode(hashed).decode('utf-8')
        
        url = "https://api.commerce.naver.com/external/v1/oauth2/token"
        data = {
            "grant_type": "client_credentials",
            "client_id": cid,
            "timestamp": timestamp,
            "client_secret_sign": sig,
            "type": "SELF"
        }
        
        r = requests.post(url, data=data)
        print(f"Status: {r.status_code}")
        print(f"Response: {r.text}")

if __name__ == "__main__":
    test_auth()
