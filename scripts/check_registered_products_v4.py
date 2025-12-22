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

async def check_registered_products_v4():
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
    
    # 기 등록 성공 상품 하나 (확인됨)
    sp_id = "15933031760"
    print(f"Deep diving into SUCCESS product: {sp_id}")
    
    code, data = client.get_product(sp_id)
    if code == 200:
        # 파일로 저장하여 정밀 분석
        target_path = "/home/sunwoo/project/drop/drop_01/drop_01_dev/scripts/success_product_full.json"
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"Success product data saved to {target_path}")
        
        # 주요 배송 정책 필드 검색 (키워드 매칭)
        def find_policy_keys(obj, parent_key=""):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    current_key = f"{parent_key}.{k}" if parent_key else k
                    if "policy" in k.lower() or "shipping" in k.lower() or "delivery" in k.lower():
                        print(f"FOUND KEY: {current_key} = {v}")
                    find_policy_keys(v, current_key)
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    find_policy_keys(item, f"{parent_key}[{i}]")

        find_policy_keys(data)
    else:
        print(f"Failed to fetch {sp_id}")

if __name__ == "__main__":
    asyncio.run(check_registered_products_v4())
