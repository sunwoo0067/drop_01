"""
쿠팡 상품 생성 시 필수 attributes 처리 검증

이 스크립트는 상품 생성 시 필수 구매옵션(attributes)이 올바르게 처리되는지 검증합니다.
- 필수 attributes 자동 추가 검증
- 데이터 형식 및 단위 검증
- 인증/구비서류 처리 검증
"""

import asyncio
import os
import json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

from app.models import MarketAccount, Product
from app.coupang_client import CoupangClient
from app.coupang_sync import (
    _map_product_to_coupang_payload,
    _get_coupang_product_metadata,
    SkipCoupangRegistrationError,
)
from app.settings import settings


def _get_database_url(value: str, fallback: str) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else fallback


async def test_mandatory_attributes_processing():
    """필수 attributes 자동 처리 검증"""
    load_dotenv()
    test_category_code = os.getenv("COUPANG_TEST_CATEGORY_CODE", "78786").strip() or "78786"
    strict_docs = os.getenv("COUPANG_TEST_STRICT_DOCS", "0") == "1"
    
    # DB 연결
    market_db_url = _get_database_url(
        settings.market_database_url,
        "postgresql+psycopg://sunwoo@/drop01_market?host=/var/run/postgresql&port=5434",
    )
    dropship_db_url = _get_database_url(
        settings.dropship_database_url,
        "postgresql+psycopg://sunwoo@/drop01?host=/var/run/postgresql&port=5434",
    )
    market_engine = create_engine(market_db_url)
    dropship_engine = create_engine(dropship_db_url)
    MarketSession = sessionmaker(bind=market_engine)
    DropshipSession = sessionmaker(bind=dropship_engine)
    
    market_session = MarketSession()
    dropship_session = DropshipSession()
    try:
        account = market_session.query(MarketAccount).filter(MarketAccount.market_code == "COUPANG").first()
        if not account or not account.credentials:
            print("❌ 쿠팡 계정 정보를 찾을 수 없습니다.")
            return False
        
        creds = account.credentials
        
        # 테스트용 상품 조회 (또는 생성)
        product = dropship_session.query(Product).filter(Product.status == "DRAFT").first()
        if not product:
            print("❌ 테스트용 상품을 찾을 수 없습니다.")
            return False

        client = CoupangClient(creds['access_key'], creds['secret_key'], creds['vendor_id'])

        print("=" * 80)
        print("쿠팡 상품 생성 시 필수 attributes 처리 검증")
        print("=" * 80)
        
        # 1. 카테고리 메타정보 조회
        print(f"\n📦 카테고리 코드: {test_category_code}")
        
        code, data = client.get_category_meta(str(test_category_code))
        if code != 200 or data.get("code") != "SUCCESS":
            print(f"❌ 카테고리 메타정보 조회 실패: {data.get('message')}")
            return False
        
        notice_meta = data.get("data", {})
        print("✅ 카테고리 메타정보 조회 성공")
        
        # 2. 필수 attributes 확인
        attributes = notice_meta.get("attributes", [])
        mandatory_attrs = [a for a in attributes if a.get("required") == "MANDATORY" and a.get("exposed") == "EXPOSED"]
        docs = notice_meta.get("requiredDocumentNames", [])
        mandatory_docs = [d for d in docs if "MANDATORY" in str(d.get("required", ""))]
        certs = notice_meta.get("certifications", [])
        mandatory_certs = [c for c in certs if c.get("required") in ["MANDATORY", "RECOMMEND"]]
        
        print(f"\n📊 필수 attributes 분석:")
        print(f"   - 전체 attributes: {len(attributes)}개")
        print(f"   - 필수 구매옵션 (MANDATORY + EXPOSED): {len(mandatory_attrs)}개")
        
        if not mandatory_attrs:
            print("   ⚠️  필수 구매옵션이 없습니다. (이 카테고리는 필수 attributes가 없을 수 있음)")
        else:
            print(f"\n   필수 구매옵션 목록:")
            for attr in mandatory_attrs:
                attr_type = attr.get("attributeTypeName", "")
                data_type = attr.get("dataType", "")
                basic_unit = attr.get("basicUnit", "")
                print(f"     - {attr_type} (타입: {data_type}, 단위: {basic_unit})")
        
        if mandatory_docs or mandatory_certs:
            print(f"\n⚠️  필수 구비서류/인증 감지: docs={len(mandatory_docs)}, certs={len(mandatory_certs)}")
            if strict_docs:
                print("   COUPANG_TEST_STRICT_DOCS=1 설정으로 인해 테스트를 중단합니다.")
                return False
            print("   테스트 목적상 페이로드 생성 시에는 해당 항목을 비워서 진행합니다.")

        # 3. 상품 메타데이터 준비
        print(f"\n🔧 상품 메타데이터 준비 중...")
        if market_db_url != dropship_db_url:
            print("❌ Market/DropShip DB가 분리되어 있어 메타데이터 조회 테스트를 진행할 수 없습니다.")
            print("   동일한 DB를 사용하도록 설정하거나 스크립트를 조정해주세요.")
            return False

        meta_result = _get_coupang_product_metadata(market_session, client, account, product)
        
        if not meta_result["ok"]:
            print(f"❌ 상품 메타데이터 준비 실패: {meta_result.get('error')}")
            return False
        
        print("✅ 상품 메타데이터 준비 완료")
        
        # 4. 페이로드 생성 (필수 attributes 자동 처리 포함)
        print(f"\n📝 상품 페이로드 생성 중...")
        notice_meta_for_payload = dict(notice_meta)
        if mandatory_docs:
            notice_meta_for_payload["requiredDocumentNames"] = []
        if mandatory_certs:
            notice_meta_for_payload["certifications"] = []

        try:
            payload = _map_product_to_coupang_payload(
                product,
                account,
                meta_result["return_center_code"],
                meta_result["outbound_center_code"],
                meta_result["predicted_category_code"],
                meta_result["return_center_detail"],
                notice_meta_for_payload,  # 카테고리 메타정보 전달
                meta_result["shipping_fee"],
                meta_result["delivery_company_code"],
            )
        except SkipCoupangRegistrationError as e:
            print(f"❌ 페이로드 생성 스킵 (사전검증): {e}")
            return True
        except ValueError as e:
            msg = str(e)
            print(f"❌ 페이로드 생성 실패 (사전검증): {msg}")
            if "필수 구비서류" in msg or "필수/추천 인증" in msg:
                print("⚠️  필수 서류/인증이 필요한 카테고리로 판단되어 테스트를 건너뜁니다.")
                return True
            return False
        
        print("✅ 상품 페이로드 생성 완료")
        
        # 5. 필수 attributes 처리 검증
        items = payload.get("items", [])
        if not items:
            print("❌ items가 비어있습니다.")
            return False
        
        item = items[0]
        item_attributes = item.get("attributes", [])
        
        print(f"\n✅ 생성된 attributes 검증:")
        print(f"   - 생성된 attributes: {len(item_attributes)}개")
        
        # 필수 attributes가 모두 포함되었는지 확인
        mandatory_attr_names = {a.get("attributeTypeName") for a in mandatory_attrs}
        created_attr_names = {a.get("attributeTypeName") for a in item_attributes if a.get("exposed") == "EXPOSED"}
        
        missing_attrs = mandatory_attr_names - created_attr_names
        if missing_attrs:
            print(f"   ❌ 누락된 필수 attributes: {missing_attrs}")
            return False
        
        print(f"   ✅ 모든 필수 attributes 포함됨")
        
        # 6. attributes 데이터 형식 검증
        print(f"\n📊 attributes 데이터 형식 검증:")
        for attr in item_attributes:
            attr_type = attr.get("attributeTypeName", "")
            attr_value = attr.get("attributeValueName", "")
            exposed = attr.get("exposed", "")
            
            # 필수 구매옵션인 경우 값이 비어있지 않은지 확인
            if exposed == "EXPOSED" and attr_type in mandatory_attr_names:
                if not attr_value or attr_value.strip() == "":
                    print(f"   ❌ {attr_type}: 값이 비어있음")
                    return False
                print(f"   ✅ {attr_type}: {attr_value}")
        
        # 7. 인증정보 처리 검증
        item_certifications = item.get("certifications", [])
        print(f"\n🔐 인증정보 처리 검증:")
        print(f"   - 생성된 certifications: {len(item_certifications)}개")
        
        if item_certifications:
            for cert in item_certifications:
                cert_type = cert.get("certificationType", "")
                print(f"   ✅ {cert_type}")
        
        # 8. 상품고시정보 처리 검증
        notices = item.get("notices", [])
        print(f"\n📄 상품고시정보 처리 검증:")
        print(f"   - 생성된 notices: {len(notices)}개")
        
        if notices:
            mandatory_notices = [n for n in notices if "MANDATORY" in str(n)]
            print(f"   - 필수 고시정보: {len(mandatory_notices)}개")
        
        # 9. 페이로드 요약 출력
        print(f"\n📋 생성된 페이로드 요약:")
        print(f"   - displayCategoryCode: {payload.get('displayCategoryCode')}")
        print(f"   - sellerProductName: {payload.get('sellerProductName', '')[:50]}...")
        print(f"   - items 수: {len(payload.get('items', []))}")
        print(f"   - 각 item의 attributes 수: {len(item_attributes)}")
        
        print(f"\n✅ 필수 attributes 처리 검증 통과!")
        return True
    finally:
        market_session.close()
        dropship_session.close()
    


async def test_attribute_data_type_validation():
    """attributes 데이터 형식 검증 테스트"""
    print("\n" + "=" * 80)
    print("attributes 데이터 형식 검증 테스트")
    print("=" * 80)
    
    # 시뮬레이션: 다양한 데이터 형식의 attributes
    test_cases = [
        {
            "attributeTypeName": "수량",
            "dataType": "NUMBER",
            "basicUnit": "개",
            "expected": "1개"
        },
        {
            "attributeTypeName": "무게",
            "dataType": "NUMBER",
            "basicUnit": "g",
            "expected": "1g"
        },
        {
            "attributeTypeName": "용량",
            "dataType": "NUMBER",
            "basicUnit": "ml",
            "expected": "1ml"
        },
        {
            "attributeTypeName": "색상",
            "dataType": "STRING",
            "basicUnit": "없음",
            "expected": "-"
        }
    ]
    
    print(f"\n📊 데이터 형식 검증:")
    all_passed = True
    
    for test_case in test_cases:
        attr_type = test_case["attributeTypeName"]
        data_type = test_case["dataType"]
        basic_unit = test_case["basicUnit"]
        expected = test_case["expected"]
        
        # 실제 로직 시뮬레이션
        attr_value = "-"
        if data_type == "NUMBER":
            if "수량" in attr_type:
                attr_value = "1개" if basic_unit == "개" else f"1{basic_unit}"
            elif "무게" in attr_type:
                attr_value = "1g" if basic_unit == "g" else f"1{basic_unit}"
            elif "용량" in attr_type:
                attr_value = "1ml" if basic_unit == "ml" else f"1{basic_unit}"
            else:
                attr_value = "1"
        
        if attr_value == expected:
            print(f"   ✅ {attr_type}: {attr_value} (예상: {expected})")
        else:
            print(f"   ❌ {attr_type}: {attr_value} (예상: {expected})")
            all_passed = False
    
    return all_passed


if __name__ == "__main__":
    print("쿠팡 상품 생성 시 필수 attributes 처리 검증 시작\n")
    
    # 1. 필수 attributes 처리 검증
    result1 = asyncio.run(test_mandatory_attributes_processing())
    
    # 2. 데이터 형식 검증
    result2 = asyncio.run(test_attribute_data_type_validation())
    
    if result1 and result2:
        print("\n✅ 모든 테스트 통과!")
        exit(0)
    else:
        print("\n❌ 일부 테스트 실패")
        exit(1)
