import requests
import time
import bcrypt
import base64
from app.session_factory import session_factory
from app.models import MarketAccount
from sqlalchemy import select

def get_info():
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
        headers = {"Authorization": f"Bearer {token}"}
        
        # Try seller info
        endpoints = [
            "/external/v1/seller/info",
            "/external/v1/seller/channels"
        ]
        for ep in endpoints:
            res = requests.get(f"https://api.commerce.naver.com{ep}", headers=headers)
            print(f"Endpoint {ep} Status: {res.status_code}")
            if res.status_code == 200:
                print(f"Response: {res.json()}")
            else:
                print(f"Error: {res.text}")

if __name__ == "__main__":
    get_info()
