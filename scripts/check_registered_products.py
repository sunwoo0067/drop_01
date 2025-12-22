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

async def check_registered_products_v2():
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
    
    print("Checking Registered Products to extract valid payload structure...")
    
    # 1. 최근 등록된 상품 목록 조회 (최대 10개)
    # v1 엔드포인트: GET /v2/providers/seller_api/apis/api/v1/marketplace/seller-products
    code, data = client.get_products(max_per_page=10)
    
    if code in [200, 201] and data.get("code") == "SUCCESS":
        products = data.get("data", [])
        if not products:
            print("No products registered in this account yet.")
        else:
            for p in products:
                sp_id = p.get("sellerProductId")
                print(f"\n--- Product ID: {sp_id} ---")
                # 2. 단건 정밀 조회하여 전체 페이로드 구조 파악
                code_p, data_p = client.get_product(str(sp_id))
                if code_p == 200:
                    # 마스킹 없이 전체 구조 출력 (로깅 목적)
                    print(json.dumps(data_p, indent=2, ensure_ascii=False))
                else:
                    print(f"Failed to fetch detail for {sp_id}: {code_p}")
    else:
        print(f"Failed to fetch products: {code} {data}")

if __name__ == "__main__":
    asyncio.run(check_registered_products_v2())
