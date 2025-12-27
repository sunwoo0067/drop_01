
import os
import sys
import json
import uuid
from sqlalchemy import select

# 프로젝트 루트를 sys.path에 추가
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.session_factory import session_factory
from app.models import MarketAccount
from app.coupang_client import CoupangClient

def debug_centers():
    with session_factory() as session:
        acct = session.scalars(
            select(MarketAccount)
            .where(MarketAccount.market_code == "COUPANG")
            .where(MarketAccount.is_active == True)
        ).first()
        if not acct:
            print("No active Coupang account found.")
            return

        print(f"Account: {acct.name}")
        client = CoupangClient(
            vendor_id=acct.credentials.get("vendor_id"),
            access_key=acct.credentials.get("access_key"),
            secret_key=acct.credentials.get("secret_key"),
        )

        print("\n--- Outbound Shipping Centers ---")
        outbound_rc, outbound_data = client.get_outbound_shipping_centers(page_size=10)
        print(f"Raw response (HTTP {outbound_rc}):")
        print(json.dumps(outbound_data, indent=2, ensure_ascii=False))

        print("\n--- Return Shipping Centers ---")
        return_rc, return_data = client.get_return_shipping_centers(page_size=10)
        print(f"Raw response (HTTP {return_rc}):")
        # print(json.dumps(return_data, indent=2, ensure_ascii=False)) # 상세 내용은 생략

if __name__ == "__main__":
    debug_centers()
