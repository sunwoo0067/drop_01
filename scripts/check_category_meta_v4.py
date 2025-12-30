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
        # data 필드 확인
        if isinstance(data, dict) and isinstance(data.get("data"), dict):
            meta_data = data["data"]

            # 핵심 정보 출력
            print(f"\nisAllowSingleItem: {meta_data.get('isAllowSingleItem')}")

            # attributes 요약
            attributes = meta_data.get("attributes", [])
            print(f"\n=== Attributes Summary ===")
            print(f"Total: {len(attributes)}")
            print(f"구매옵션 (EXPOSED): {len([a for a in attributes if a.get('exposed') == 'EXPOSED'])}")
            print(f"검색옵션 (NONE): {len([a for a in attributes if a.get('exposed') == 'NONE'])}")
            print(f"필수 (MANDATORY): {len([a for a in attributes if a.get('required') == 'MANDATORY'])}")

            # noticeCategories 요약
            notices = meta_data.get("noticeCategories", [])
            print(f"\n=== Notice Categories Summary ===")
            for notice in notices:
                name = notice.get('noticeCategoryName')
                details = notice.get('noticeCategoryDetailNames', [])
                mandatory_count = len([d for d in details if d.get('required') == 'MANDATORY'])
                print(f"- {name}: {len(details)} items ({mandatory_count} mandatory)")

            # requiredDocumentNames 요약
            docs = meta_data.get("requiredDocumentNames", [])
            print(f"\n=== Required Documents Summary ===")
            for doc in docs:
                print(f"- {doc.get('templateName')} ({doc.get('required')})")

            # certifications 요약
            certs = meta_data.get("certifications", [])
            print(f"\n=== Certifications Summary ===")
            print(f"Total: {len(certs)}")
            mandatory_certs = [c for c in certs if c.get('required') == 'MANDATORY']
            if mandatory_certs:
                print(f"필수 인증: {[c.get('name') for c in mandatory_certs]}")

            # allowedOfferConditions 요약
            conditions = meta_data.get("allowedOfferConditions", [])
            print(f"\n=== Allowed Offer Conditions ===")
            print(f"상태: {conditions}")

            # full data (길이 제한)
            print(f"\n=== Full Data (truncated) ===")
            print(json.dumps(data, indent=2, ensure_ascii=False)[:3000])
        else:
            print(json.dumps(data, indent=2, ensure_ascii=False)[:3000])
    else:
        print(f"Error: {data}")

if __name__ == "__main__":
    asyncio.run(check_category_meta_v4())
