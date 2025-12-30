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

    # 통합 카테고리 메타정보 조회
    # 쿠팡 API: GET /v2/providers/seller_api/apis/api/v1/marketplace/meta/category-related-metas/display-category-codes/{displayCategoryCode}
    code, data = client.get_category_meta(str(category_code))

    if code in [200, 201]:
        print(f"\n=== Success (Status Code: {code}) ===")
        if isinstance(data, dict) and isinstance(data.get("data"), dict):
            meta_data = data["data"]

            # 전체 메타정보 출력
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(f"Failed to fetch category meta: {code}")
        print(json.dumps(data, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    asyncio.run(check_category_meta())
