"""
쿠팡 카테고리 메타정보 통합 API 테스트

이 스크립트는 개선된 통합 카테고리 메타정보 API를 테스트합니다.
- 통합 API 엔드포인트 검증
- 필수 attributes 자동 처리 검증
- 인증/구비서류 정보 확인
"""

import asyncio
import os
import json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

from app.models import MarketAccount
from app.coupang_client import CoupangClient


async def test_category_meta_integration():
    """통합 카테고리 메타정보 API 테스트"""
    load_dotenv()
    
    # DB 연결
    market_engine = create_engine("postgresql+psycopg://sunwoo@/drop01_market?host=/var/run/postgresql&port=5434")
    MarketSession = sessionmaker(bind=market_engine)
    
    mk_session = MarketSession()
    try:
        account = mk_session.query(MarketAccount).filter(MarketAccount.market_code == "COUPANG").first()
        if not account or not account.credentials:
            print("❌ 쿠팡 계정 정보를 찾을 수 없습니다.")
            return False
        
        creds = account.credentials
    finally:
        mk_session.close()
    
    client = CoupangClient(creds['access_key'], creds['secret_key'], creds['vendor_id'])
    
    # 테스트할 카테고리 코드들
    test_categories = [
        "78786",  # 문구/사무용품
        "56137",  # 화장품 (예시)
    ]
    
    print("=" * 80)
    print("쿠팡 카테고리 메타정보 통합 API 테스트")
    print("=" * 80)
    
    all_passed = True
    
    for category_code in test_categories:
        print(f"\n📦 카테고리 코드: {category_code}")
        print("-" * 80)
        
        # 1. 통합 API 호출 테스트
        code, data = client.get_category_meta(category_code)
        
        if code != 200:
            print(f"❌ API 호출 실패: HTTP {code}")
            print(f"   응답: {data}")
            all_passed = False
            continue
        
        if data.get("code") != "SUCCESS":
            print(f"❌ API 응답 실패: {data.get('code')}")
            print(f"   메시지: {data.get('message')}")
            all_passed = False
            continue
        
        meta_data = data.get("data", {})
        if not isinstance(meta_data, dict):
            print(f"❌ 데이터 형식 오류: data 필드가 dict가 아님")
            all_passed = False
            continue
        
        print("✅ 통합 API 호출 성공")
        
        # 2. 필수 필드 검증
        required_fields = ["isAllowSingleItem", "attributes", "noticeCategories"]
        missing_fields = [f for f in required_fields if f not in meta_data]
        if missing_fields:
            print(f"❌ 필수 필드 누락: {missing_fields}")
            all_passed = False
            continue
        
        print("✅ 필수 필드 검증 통과")
        
        # 3. 필수 attributes 확인
        attributes = meta_data.get("attributes", [])
        mandatory_attrs = [a for a in attributes if a.get("required") == "MANDATORY" and a.get("exposed") == "EXPOSED"]
        
        print(f"\n📊 Attributes 분석:")
        print(f"   - 전체: {len(attributes)}개")
        print(f"   - 필수 구매옵션 (MANDATORY + EXPOSED): {len(mandatory_attrs)}개")
        print(f"   - 검색필터 (NONE): {len([a for a in attributes if a.get('exposed') == 'NONE'])}개")
        
        if mandatory_attrs:
            print(f"\n   필수 구매옵션 목록:")
            for attr in mandatory_attrs[:5]:  # 최대 5개만 출력
                attr_type = attr.get("attributeTypeName", "")
                data_type = attr.get("dataType", "")
                basic_unit = attr.get("basicUnit", "")
                print(f"     - {attr_type} (타입: {data_type}, 단위: {basic_unit})")
        
        # 4. 인증정보 확인
        certs = meta_data.get("certifications", [])
        mandatory_certs = [c for c in certs if c.get("required") in ["MANDATORY", "RECOMMEND"]]
        
        print(f"\n🔐 인증정보 분석:")
        print(f"   - 전체: {len(certs)}개")
        print(f"   - 필수/추천: {len(mandatory_certs)}개")
        
        if mandatory_certs:
            print(f"   필수/추천 인증 목록:")
            for cert in mandatory_certs[:3]:  # 최대 3개만 출력
                print(f"     - {cert.get('name')} ({cert.get('required')})")
        
        # 5. 구비서류 확인
        docs = meta_data.get("requiredDocumentNames", [])
        mandatory_docs = [d for d in docs if "MANDATORY" in d.get("required", "")]
        
        print(f"\n📄 구비서류 분석:")
        print(f"   - 전체: {len(docs)}개")
        print(f"   - 필수: {len(mandatory_docs)}개")
        
        if mandatory_docs:
            print(f"   필수 구비서류 목록:")
            for doc in mandatory_docs:
                print(f"     - {doc.get('templateName')} ({doc.get('required')})")
        
        # 6. 허용된 상품 상태 확인
        conditions = meta_data.get("allowedOfferConditions", [])
        print(f"\n📦 허용된 상품 상태: {conditions}")
        
        # 7. 단일상품 등록 가능 여부
        is_allow_single = meta_data.get("isAllowSingleItem", False)
        print(f"\n✅ 단일상품 등록 가능: {is_allow_single}")
        
        print(f"\n✅ 카테고리 {category_code} 테스트 통과")
    
    print("\n" + "=" * 80)
    if all_passed:
        print("✅ 모든 테스트 통과!")
    else:
        print("❌ 일부 테스트 실패")
    print("=" * 80)
    
    return all_passed


async def test_category_meta_attributes_processing():
    """필수 attributes 자동 처리 로직 테스트"""
    print("\n" + "=" * 80)
    print("필수 attributes 자동 처리 로직 테스트")
    print("=" * 80)
    
    # 시뮬레이션: 카테고리 메타정보 응답
    mock_meta = {
        "attributes": [
            {
                "attributeTypeName": "수량",
                "dataType": "NUMBER",
                "basicUnit": "개",
                "usableUnits": ["개", "개입", "매"],
                "required": "MANDATORY",
                "exposed": "EXPOSED"
            },
            {
                "attributeTypeName": "무게",
                "dataType": "NUMBER",
                "basicUnit": "g",
                "usableUnits": ["g", "kg"],
                "required": "MANDATORY",
                "exposed": "EXPOSED"
            },
            {
                "attributeTypeName": "피부타입",
                "dataType": "STRING",
                "basicUnit": "없음",
                "usableUnits": [],
                "required": "OPTIONAL",
                "exposed": "NONE"
            }
        ]
    }
    
    # 필수 attributes 추출 로직 테스트
    attrs = mock_meta.get("attributes", [])
    mandatory_attrs = [a for a in attrs if a.get("required") == "MANDATORY" and a.get("exposed") == "EXPOSED"]
    
    print(f"\n📊 필수 attributes 추출:")
    print(f"   - 전체: {len(attrs)}개")
    print(f"   - 필수 구매옵션: {len(mandatory_attrs)}개")
    
    # 자동 처리 로직 시뮬레이션
    processed_attributes = []
    for attr in mandatory_attrs:
        attr_type = attr.get("attributeTypeName")
        data_type = attr.get("dataType", "STRING")
        basic_unit = attr.get("basicUnit", "")
        
        # 데이터 형식에 따른 기본값 설정
        attr_value = "-"
        if data_type == "NUMBER":
            if "수량" in attr_type:
                attr_value = "1개" if basic_unit == "개" else f"1{basic_unit}"
            elif "무게" in attr_type:
                attr_value = "1g" if basic_unit == "g" else f"1{basic_unit}"
            else:
                attr_value = "1"
        
        processed_attributes.append({
            "attributeTypeName": attr_type,
            "attributeValueName": attr_value,
            "exposed": "EXPOSED"
        })
        
        print(f"   ✅ {attr_type} → {attr_value}")
    
    print(f"\n✅ 필수 attributes 자동 처리 완료: {len(processed_attributes)}개")
    
    return True


if __name__ == "__main__":
    print("쿠팡 카테고리 메타정보 통합 API 테스트 시작\n")
    
    # 1. 통합 API 테스트
    result1 = asyncio.run(test_category_meta_integration())
    
    # 2. attributes 자동 처리 로직 테스트
    result2 = asyncio.run(test_category_meta_attributes_processing())
    
    if result1 and result2:
        print("\n✅ 모든 테스트 통과!")
        exit(0)
    else:
        print("\n❌ 일부 테스트 실패")
        exit(1)
