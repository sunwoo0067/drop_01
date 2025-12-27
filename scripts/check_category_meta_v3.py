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

    # 통합 API: 카테고리 메타정보 모두 한번에 조회
    # Coupang API: GET /v2/providers/seller_api/apis/api/v1/marketplace/meta/category-related-metas/display-category-codes/{code}
    code, data = client.get_category_meta(str(category_code))
    print(f"\n[Category Meta] Status Code: {code}")

    if code in [200, 201]:
        # 전체 응답 구조 파악
        print("\n=== Full Response Structure ===")
        print(json.dumps(data, indent=2, ensure_ascii=False)[:2000])

        # data 필드 확인
        if isinstance(data, dict) and isinstance(data.get("data"), dict):
            meta_data = data["data"]

            # isAllowSingleItem 확인
            print(f"\n=== isAllowSingleItem ===")
            print(meta_data.get("isAllowSingleItem"))

            # attributes (구매옵션/검색옵션) 확인
            print(f"\n=== Attributes Count ===")
            attributes = meta_data.get("attributes", [])
            print(f"Total attributes: {len(attributes)}")
            for i, attr in enumerate(attributes[:3]):  # 처음 3개만 출력
                print(f"  [{i}] {attr.get('attributeTypeName')} (required: {attr.get('required')}, exposed: {attr.get('exposed')})")

            # noticeCategories (상품고시정보) 확인
            print(f"\n=== Notice Categories ===")
            notices = meta_data.get("noticeCategories", [])
            print(f"Total notice categories: {len(notices)}")
            for notice in notices:
                print(f"  - {notice.get('noticeCategoryName')}")
                details = notice.get("noticeCategoryDetailNames", [])
                for detail in details[:3]:  # 처음 3개만 출력
                    print(f"    * {detail.get('noticeCategoryDetailName')} ({detail.get('required')})")

            # requiredDocumentNames (구비서류) 확인
            print(f"\n=== Required Documents ===")
            docs = meta_data.get("requiredDocumentNames", [])
            for doc in docs:
                print(f"  - {doc.get('templateName')} ({doc.get('required')})")

            # certifications (인증정보) 확인
            print(f"\n=== Certifications ===")
            certs = meta_data.get("certifications", [])
            print(f"Total certifications: {len(certs)}")
            for cert in certs[:5]:  # 처음 5개만 출력
                print(f"  - {cert.get('name')} ({cert.get('required')})")

            # allowedOfferConditions (허용된 상품 상태) 확인
            print(f"\n=== Allowed Offer Conditions ===")
            conditions = meta_data.get("allowedOfferConditions", [])
            print(conditions)
    else:
        print(f"Error: {data}")

if __name__ == "__main__":
    asyncio.run(check_category_meta_v3())
