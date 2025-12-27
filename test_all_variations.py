import requests
import time
import hmac
import hashlib
import base64
from app.session_factory import session_factory
from app.models import MarketAccount
from sqlalchemy import select

def test():
    with session_factory() as session:
        acc = session.execute(select(MarketAccount).where(MarketAccount.market_code == "SMARTSTORE")).scalars().first()
        cid = acc.credentials.get("client_id")
        secret = acc.credentials.get("client_secret")
        
        print(f"Using CID: {cid}")
        print(f"Using Secret: {secret}")
        
        ts = str(int(time.time() * 1000))
        
        variations = [
            (f"{cid}_{ts}", "CID_TS"),
            (f"{ts}_{cid}", "TS_CID"),
            (f"{cid}.{ts}", "CID.TS"),
            (f"{ts}.{cid}", "TS.CID"),
            (f"{cid}{ts}", "CIDTS"),
            (f"{ts}{cid}", "TSCID"),
            (f"{cid}\n{ts}", "CID\nTS"),
            (f"{ts}\n{cid}", "TS\nCID"),
        ]
        
        for msg, name in variations:
            # Type 1: HMAC-SHA256 -> Base64
            sig1 = base64.b64encode(hmac.new(secret.encode("utf-8"), msg.encode("utf-8"), hashlib.sha256).digest()).decode("utf-8")
            # Type 2: HMAC-SHA256 -> Hex
            sig2 = hmac.new(secret.encode("utf-8"), msg.encode("utf-8"), hashlib.sha256).hexdigest()
            # Type 3: HMAC-SHA256 URL Safe Base64
            sig3 = base64.urlsafe_b64encode(hmac.new(secret.encode("utf-8"), msg.encode("utf-8"), hashlib.sha256).digest()).decode("utf-8")
            
            for sig, sname in [(sig1, "B64"), (sig2, "HEX"), (sig3, "URLB64")]:
                data = {
                    "grant_type": "client_credentials",
                    "client_id": cid,
                    "timestamp": ts,
                    "client_secret_sign": sig,
                    "type": "SELF"
                }
                r = requests.post("https://api.commerce.naver.com/external/v1/oauth2/token", data=data)
                print(f"MSG={name}, SIG={sname} -> {r.status_code} {r.text[:50]}")
                if r.status_code == 200:
                    print("!!! SUCCESS !!!")
                    print(f"Format: MSG={name}, SIG={sname}")
                    return
                time.sleep(0.3)

if __name__ == "__main__":
    test()
