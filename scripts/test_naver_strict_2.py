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
        
        # Test cases for separators in message
        seps = ["_", ".", " ", ":", "-", "/", "|", ","]
        ts = str(int(time.time() * 1000))
        
        for sep in seps:
            msg = f"{cid}{sep}{ts}"
            sig = base64.b64encode(hmac.new(secret.encode("utf-8"), msg.encode("utf-8"), hashlib.sha256).digest()).decode("utf-8")
            data = {
                "grant_type": "client_credentials",
                "client_id": cid,
                "timestamp": ts,
                "client_secret_sign": sig,
                "type": "SELF"
            }
            r = requests.post("https://api.commerce.naver.com/external/v1/oauth2/token", data=data)
            if r.status_code == 200:
                print(f"SUCCESS with sep='{sep}'")
                return
            else:
                print(f"FAILED with sep='{sep}': {r.status_code}")
            time.sleep(0.5)

if __name__ == "__main__":
    test_auth()
