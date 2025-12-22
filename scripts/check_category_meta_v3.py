import asyncio
import os
import json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

from app.models import MarketAccount
from app.coupang_client import CoupangClient

async def check_category_meta_v3():
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
    
    # 문구류/필기구 관련 카테고리 예시
    category_code = 78786 
    
    print(f"--- Checking Category Meta for {category_code} ---")
    
    # 1. 고시정보 규격 조회 (Notice Meta)
    # Coupang API: GET /v2/providers/seller_api/apis/api/v1/marketplace/meta/category-notices?displayCategoryCode={code}
    url_notice = f"/v2/providers/seller_api/apis/api/v1/marketplace/meta/category-notices"
    code, data_notice = client.get(url_notice, {"displayCategoryCode": category_code})
    print(f"\n[Category Notices] {code}")
    if code in [200, 201]:
        print(json.dumps(data_notice, indent=2, ensure_ascii=False))
    else:
        print(f"Error: {data_notice}")

    # 2. 필수 속성 조회 (Attribute Meta)
    # Coupang API: GET /v2/providers/seller_api/apis/api/v1/marketplace/meta/category-attributes?displayCategoryCode={code}
    url_attr = f"/v2/providers/seller_api/apis/api/v1/marketplace/meta/category-attributes"
    code, data_attr = client.get(url_attr, {"displayCategoryCode": category_code})
    print(f"\n[Category Attributes] {code}")
    if code in [200, 201]:
        print(json.dumps(data_attr, indent=2, ensure_ascii=False))
    else:
        print(f"Error: {data_attr}")

if __name__ == "__main__":
    asyncio.run(check_category_meta_v3())
