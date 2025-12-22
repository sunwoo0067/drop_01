import asyncio
import os
import json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

from app.models import MarketAccount
from app.coupang_client import CoupangClient

async def check_category_meta_v2():
    load_dotenv()
    
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
    
    # 78786 (사무용품/필기구 관련)
    category_code = 78786
    
    print(f"--- Checking Category Meta for {category_code} ---")
    
    # URL 후보 1 (V2 providers / seller_api / v1 marketplace / meta / category-notices) - 이미 실패함
    # URL 후보 2 (V2 providers / marketplace_openapi / v2 / category / ...) - 다른 계열 문서 참고
    
    # 가장 가능성 높은 Marketplace OpenAPI V2 경로 탐색
    url = f"/v2/providers/marketplace_openapi/apis/api/v2/category-notices"
    params = {"displayCategoryCode": category_code}
    
    code, data = client.get(url, params)
    print(f"Result (V2 Category Notices): {code} {data}")

    # 또한 등록 실패의 핵심인 '배송방법' 검증을 위해 현재 계정의 배송 정책 조회 시도
    # GET /v2/providers/marketplace_openapi/apis/api/v1/vendor/shipping-place/outbound (이전 scripts/check_logistics.py에서 성공한 구조 참고)
    
if __name__ == "__main__":
    asyncio.run(check_category_meta_v2())
