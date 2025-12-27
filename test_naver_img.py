import requests
import time
import bcrypt
import base64
from app.session_factory import session_factory
from app.models import MarketAccount
from sqlalchemy import select

def test_upload():
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
        
        # Testing multiple field names
        url = "https://api.commerce.naver.com/external/v1/product-images/upload"
        img_res = requests.get("https://picsum.photos/600/600")
        content = img_res.content
        
        for field in ["imageFiles", "image", "file", "images"]:
            files = {field: ("test.jpg", content, "image/jpeg")}
            res = requests.post(url, headers=headers, files=files)
            print(f"Field '{field}' Test: {res.status_code} - {res.text}")

if __name__ == "__main__":
    test_upload()
