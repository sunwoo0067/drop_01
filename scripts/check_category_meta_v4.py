import asyncio
import os
import json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

from app.models import MarketAccount
from app.coupang_client import CoupangClient

async def check_category_meta_v4():
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
    
    # 78786
    category_code = "78786" 
    
    print(f"--- Checking Category Meta (Internal Path) for {category_code} ---")
    
    # CoupangClient.get_category_meta() 사용
    # 내부 경로: /v2/providers/seller_api/apis/api/v1/marketplace/meta/category-related-metas/display-category-codes/{category_code}
    code, data = client.get_category_meta(category_code)
    print(f"Result: {code}")
    if code in [200, 201]:
        # 너무 길 수 있으므로 핵심 구조만 파악
        print(json.dumps(data, indent=2, ensure_ascii=False)[:3000])
    else:
        print(f"Error: {data}")

if __name__ == "__main__":
    asyncio.run(check_category_meta_v4())
