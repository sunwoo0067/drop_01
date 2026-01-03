import requests
import time
import bcrypt
import base64
from app.session_factory import session_factory
from app.models import MarketAccount
from sqlalchemy import select

def test():
    with session_factory() as session:
        accounts = session.execute(select(MarketAccount).where(MarketAccount.market_code == "SMARTSTORE")).scalars().all()
        for acc in accounts:
            print(f"--- Checking account: {acc.name} ---")
            cid = acc.credentials.get("client_id")
            secret = acc.credentials.get("client_secret")
            if not cid or not secret:
                print(f"Missing cid/secret for {acc.name}")
                continue
            
            try:
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
                res_json = r.json()
                if r.status_code != 200:
                    print(f"Token failed: {res_json}")
                    continue
                
                token = res_json.get("access_token")
                headers = {"Authorization": f"Bearer {token}"}
                
                # Try finding addresses
                endpoints = [
                    "/v1/seller/address-book",
                    "/v2/seller/address-book",
                    "/v1/seller/addresses",
                ]
                for ep in endpoints:
                    re = requests.get(f"https://api.commerce.naver.com/external{ep}", headers=headers)
                    print(f"Endpoint {ep} Status: {re.status_code}")
                    if re.status_code == 200:
                        print(f"Response: {re.json()}")
            except Exception as e:
                print(f"Error for {acc.name}: {e}")

if __name__ == "__main__":
    test()
