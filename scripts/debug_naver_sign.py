import hmac
import hashlib
import base64
import time
import requests
from app.session_factory import session_factory
from app.models import MarketAccount
from sqlalchemy import select

def test_formats():
    with session_factory() as session:
        acc = session.execute(
            select(MarketAccount).where(MarketAccount.market_code == "SMARTSTORE")
        ).scalars().first()
        
        if not acc:
            print("No SmartStore account found.")
            return
            
        client_id = acc.credentials.get("client_id")
        client_secret = acc.credentials.get("client_secret")
        
        formats = [
            lambda cid, ts: f"{cid}_{ts}",
            lambda cid, ts: f"{cid}{ts}",
            lambda cid, ts: f"{cid}.{ts}",
            lambda cid, ts: f"{ts}_{cid}",
            lambda cid, ts: f"{ts}.{cid}",
            lambda cid, ts: f"{ts}"
        ]
        
        labels = ["cid_ts", "cidts", "cid.ts", "ts_cid", "ts.cid", "ts_only"]
        
        url = "https://api.commerce.naver.com/external/v1/oauth2/token"
        
        for i, fmt_fn in enumerate(formats):
            timestamp = str(int(time.time() * 1000))
            
            # 1. 정상 순서 테스트
            message = fmt_fn(client_id, timestamp)
            signature = base64.b64encode(
                hmac.new(
                    client_secret.encode("utf-8"),
                    message.encode("utf-8"),
                    hashlib.sha256
                ).digest()
            ).decode("utf-8")
            
            data = {
                "grant_type": "client_credentials",
                "client_id": client_id,
                "timestamp": timestamp,
                "client_secret_sign": signature,
                "type": "SELF"
            }
            
            print(f"Testing format: {labels[i]} (NORMAL)...")
            res = requests.post(url, data=data)
            if res.status_code == 200:
                print(f"  SUCCESS! Format is: {labels[i]} (NORMAL)")
                return
            
            # 2. 스왑 테스트 (client_id와 client_secret이 바뀌어 있을 경우)
            message_swap = fmt_fn(client_secret, timestamp)
            signature_swap = base64.b64encode(
                hmac.new(
                    client_id.encode("utf-8"),
                    message_swap.encode("utf-8"),
                    hashlib.sha256
                ).digest()
            ).decode("utf-8")
            
            data_swap = {
                "grant_type": "client_credentials",
                "client_id": client_secret,
                "timestamp": timestamp,
                "client_secret_sign": signature_swap,
                "type": "SELF"
            }
            
            print(f"Testing format: {labels[i]} (SWAPPED)...")
            res = requests.post(url, data=data_swap)
            if res.status_code == 200:
                print(f"  SUCCESS! Format is: {labels[i]} (SWAPPED)")
                return
            
            time.sleep(1)

if __name__ == "__main__":
    test_formats()
