import asyncio
import os
import json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

from app.models import MarketAccount
from app.coupang_client import CoupangClient

async def check_logistics_codes():
    load_dotenv()
    
    # Market DB 연결
    market_engine = create_engine("postgresql+psycopg://sunwoo@/drop01_market?host=/var/run/postgresql&port=5434")
    MarketSession = sessionmaker(bind=market_engine)
    
    mk_session = MarketSession()
    try:
        account = mk_session.query(MarketAccount).filter(MarketAccount.market_code == "COUPANG").first()
        creds = account.credentials
    finally:
        mk_session.close()

    if not creds:
        print("No Coupang credentials found.")
        return

    client = CoupangClient(creds['access_key'], creds['secret_key'], creds['vendor_id'])
    
    print(f"--- Checking Logistics for Vendor: {creds['vendor_id']} ---")
    
    # 1. 출고지 조회
    print("\n[Outbound Shipping Centers]")
    code, data = client.get_outbound_shipping_centers()
    if code in [200, 201]:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(f"Failed to fetch outbound centers: {code} {data}")

    # 2. 반품지 조회
    print("\n[Return Shipping Centers]")
    code, data = client.get_return_shipping_centers()
    if code in [200, 201]:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(f"Failed to fetch return centers: {code} {data}")

    # 3. 배송사 코드 확인 (필요 시)
    # 쿠팡은 주로 CJGLS, HANJIN, LOTTE, LOGEN, POST 등을 사용함

if __name__ == "__main__":
    asyncio.run(check_logistics_codes())
