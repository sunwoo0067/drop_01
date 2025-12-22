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

async def check_shipping_policies():
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
    
    print("Checking Shipping Policies / Shipping Places...")
    
    # 1. 출고지/배송 정책 관련 API (다양한 버전 시도)
    paths = [
        "/v2/providers/openapi/apis/api/v4/vendors/{vendor_id}/shipping-policies",
        "/v2/providers/marketplace_openapi/apis/api/v1/vendor/shipping-place/outbound",
        "/v2/providers/marketplace_openapi/apis/api/v1/vendors/{vendor_id}/shipping-policies"
    ]
    
    for path in paths:
        target_path = path.replace("{vendor_id}", creds['vendor_id'])
        print(f"\nTrying Path: {target_path}")
        code, data = client.get(target_path)
        print(f"Result {code}: {str(data)[:500]}")

if __name__ == "__main__":
    asyncio.run(check_shipping_policies())
