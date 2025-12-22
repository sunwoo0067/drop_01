import asyncio
import os
import json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

from app.models import MarketAccount
from app.coupang_client import CoupangClient

async def check_category_meta():
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
    
    # 분석 대상 카테고리 (이전 실패 묶음 중 하나)
    category_code = 78786 # 문구/사무용품 관련 추정
    
    print(f"--- Checking Category Metadata for: {category_code} ---")
    
    # 카테고리별 상품 고시정보 템플릿 조회
    # 쿠팡 API: GET /v2/providers/seller_api/apis/api/v1/marketplace/meta/category-notices?displayCategoryCode={displayCategoryCode}
    url = f"/v2/providers/seller_api/apis/api/v1/marketplace/meta/category-notices"
    params = {"displayCategoryCode": category_code}
    
    code, data = client.get(url, params)
    if code in [200, 201]:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(f"Failed to fetch category meta: {code} {data}")

if __name__ == "__main__":
    asyncio.run(check_category_meta())
