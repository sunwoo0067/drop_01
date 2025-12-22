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

async def check_registered_products_v3():
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
    
    print("Extracting deliveryChargePolicyNo from existing products...")
    
    code, data = client.get_products(max_per_page=5)
    if code in [200, 201] and data.get("code") == "SUCCESS":
        for p in data.get("data", []):
            sp_id = p.get("sellerProductId")
            code_p, data_p = client.get_product(str(sp_id))
            if code_p == 200:
                print(f"\n--- Product ID: {sp_id} ---")
                # 배송 정책 관련 필드를 집중적으로 탐색
                # v2 엔드포인트 응답에서 deliveryChargePolicyNo 또는 유사 필드 탐색
                print(f"deliveryChargePolicyNo: {data_p.get('deliveryChargePolicyNo')}")
                print(f"deliveryMethod: {data_p.get('deliveryMethod')}")
                print(f"deliveryCompanyCode: {data_p.get('deliveryCompanyCode')}")
                # 아이템 하위 배송 정보
                for item in data_p.get('items', []):
                    print(f"Item OutboundShippingDay: {item.get('outboundShippingDay')}")
                    # 고시정보 카테고리 명칭 확인
                    for notice in item.get('notices', []):
                        print(f"Notice Category: {notice.get('noticeCategoryName')}")
            else:
                print(f"Failed {sp_id}")
    else:
        print(f"List Error: {code}")

if __name__ == "__main__":
    asyncio.run(check_registered_products_v3())
