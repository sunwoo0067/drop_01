import asyncio
import os
import json
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

from app.models import MarketAccount
from app.coupang_client import CoupangClient

logging.basicConfig(level=logging.INFO)

async def check_shipping_policies_v2():
    load_dotenv()
    market_engine = create_engine("postgresql+psycopg://sunwoo@/drop01_market?host=/var/run/postgresql&port=5434")
    MarketSession = sessionmaker(bind=market_engine)
    
    mk_session = MarketSession()
    try:
        account = mk_session.query(MarketAccount).filter(MarketAccount.market_code == "COUPANG").first()
        creds = account.credentials
    finally:
        mk_session.close()

    client = CoupangClient(creds['access_key'], creds['secret_key'], creds['vendor_id'])
    
    print("Checking Shipping Policies with CORRECT ENDPOINTS...")
    
    # 1. 배송지/출고지 정보 (이건 이미 성공함)
    # 2. 배송비 정책 (Delivery Charge Policies)
    # 엔드포인트: GET /v2/providers/marketplace_openapi/apis/api/v1/vendors/{vendorId}/shipping-policies
    # (v25 시도 시 404였던 것 재확인 - URL 구조 정밀 수동 구성)
    
    vendor_id = creds['vendor_id']
    # 윙 가이드상 엔드포인트 확인: /v2/providers/marketplace_openapi/apis/api/v1/vendors/{vendorId}/shipping-policies
    path = f"/v2/providers/marketplace_openapi/apis/api/v1/vendors/{vendor_id}/shipping-policies"
    print(f"\nRequesting: {path}")
    code, data = client.get(path)
    print(f"Result {code}: {json.dumps(data, indent=2, ensure_ascii=False)}")

    # 만약 실패할 경우, 다른 리스트 형태의 API 시도
    # GET /v2/providers/marketplace_openapi/apis/api/v1/vendors/{vendorId}/outbound-shipping-centers
    path2 = f"/v2/providers/marketplace_openapi/apis/api/v1/vendors/{vendor_id}/outbound-shipping-centers"
    print(f"\nRequesting 2: {path2}")
    code2, data2 = client.get(path2)
    print(f"Result 2 {code2}: {json.dumps(data2, indent=2, ensure_ascii=False)}")

if __name__ == "__main__":
    asyncio.run(check_shipping_policies_v2())
