import requests
import time
import bcrypt
import base64
from app.session_factory import session_factory
from app.models import MarketAccount
from sqlalchemy import select

def test():
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
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        
        # V2 Registration with BOTH originProduct and smartstoreChannelProduct
        payload = {
            "originProduct": {
                "statusType": "SALE",
                "name": "API_TEST_PRODUCT_V2_FINAL",
                "salePrice": 10000,
                "stockQuantity": 100,
                "category": {"categoryId": "50000000"},
                "detailContent": "<html><body>Test Content</body></html>",
                "images": {
                    "representativeImage": {"url": "https://avatars.githubusercontent.com/u/1?v=4"}
                },
                "deliveryInfo": {
                    "deliveryType": "DELIVERY",
                    "deliveryAttributeType": "NORMAL",
                    "deliveryCompany": "CJGLS",
                    "deliveryBundleGroupPriority": 1,
                    "deliveryFee": {
                        "deliveryFeeType": "FREE"
                    }
                }
            },
            "smartstoreChannelProduct": {
                "naverShoppingRegistration": True,
                "channelProductDisplayStatusType": "ON_SALE"
            }
        }
        
        r_v2 = requests.post("https://api.commerce.naver.com/external/v2/products", headers=headers, json=payload)
        print(f"V2 Reg Status: {r_v2.status_code}")
        print(f"V2 Reg Response: {r_v2.text[:500]}")

if __name__ == "__main__":
    test()
