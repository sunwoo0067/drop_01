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

    # 통합 카테고리 메타정보 조회
    code, data = client.get_category_meta(str(category_code))
    print(f"Result: {code}")

    if code in [200, 201]:
        print("\n=== Success ===")
        if isinstance(data, dict) and isinstance(data.get("data"), dict):
            meta_data = data["data"]

            # 핵심 필드 요약
            print(f"isAllowSingleItem: {meta_data.get('isAllowSingleItem')}")

            # Attributes 요약
            attributes = meta_data.get("attributes", [])
            print(f"\nAttributes: {len(attributes)}")
            for attr in attributes[:5]:
                print(f"  - {attr.get('attributeTypeName')} (required: {attr.get('required')}, exposed: {attr.get('exposed')})")

            # Notice Categories 요약
            notices = meta_data.get("noticeCategories", [])
            print(f"\nNotice Categories: {len(notices)}")
            for notice in notices[:3]:
                print(f"  - {notice.get('noticeCategoryName')}")

            # Required Documents 요약
            docs = meta_data.get("requiredDocumentNames", [])
            print(f"\nRequired Documents: {len(docs)}")
            for doc in docs:
                print(f"  - {doc.get('templateName')} ({doc.get('required')})")

            # Certifications 요약
            certs = meta_data.get("certifications", [])
            print(f"\nCertifications: {len(certs)}")
            mandatory_certs = [c for c in certs if c.get('required') == 'MANDATORY']
            if mandatory_certs:
                print(f"  Mandatory: {[c.get('name') for c in mandatory_certs]}")

            # Allowed Offer Conditions
            conditions = meta_data.get("allowedOfferConditions", [])
            print(f"\nAllowed Offer Conditions: {conditions}")
        else:
            print(json.dumps(data, indent=2, ensure_ascii=False)[:2000])
    else:
        print(f"Error: {data}")

if __name__ == "__main__":
    asyncio.run(check_category_meta_v2())
