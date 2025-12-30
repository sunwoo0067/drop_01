# 쿠팡 API 사용 가이드

이 문서는 쿠팡 상품 관련 API의 사용 방법과 개선 사항을 설명합니다.

## 목차

1. [카테고리 메타정보 API](#카테고리-메타정보-api)
2. [상품 생성 API](#상품-생성-api)
3. [상품 조회 API](#상품-조회-api)
4. [상품 수정 API](#상품-수정-api)
5. [상품 삭제 API](#상품-삭제-api)
6. [상품 아이템별 API](#상품-아이템별-api)
7. [에러 처리](#에러-처리)

---

## 카테고리 메타정보 API

### 개선 사항

**이전 방식 (2개 API 호출):**
```python
# 분리된 API 사용
code1, data1 = client.get_category_attributes(category_code)
code2, data2 = client.get_category_notices(category_code)
```

**개선된 방식 (1개 API 호출):**
```python
# 통합 API 사용
code, data = client.get_category_meta(category_code)
```

### 사용 예시

```python
from app.coupang_client import CoupangClient

client = CoupangClient(access_key, secret_key, vendor_id)

# 카테고리 메타정보 조회
code, data = client.get_category_meta("78786")

if code == 200 and data.get("code") == "SUCCESS":
    meta = data["data"]
    
    # 필수 attributes 확인
    attrs = meta.get("attributes", [])
    mandatory_attrs = [
        a for a in attrs 
        if a.get("required") == "MANDATORY" and a.get("exposed") == "EXPOSED"
    ]
    
    # 인증정보 확인
    certs = meta.get("certifications", [])
    mandatory_certs = [
        c for c in certs 
        if c.get("required") in ["MANDATORY", "RECOMMEND"]
    ]
    
    # 구비서류 확인
    docs = meta.get("requiredDocumentNames", [])
    mandatory_docs = [
        d for d in docs 
        if "MANDATORY" in d.get("required", "")
    ]
```

### 반환 데이터 구조

```json
{
  "code": "SUCCESS",
  "data": {
    "isAllowSingleItem": true,
    "attributes": [
      {
        "attributeTypeName": "수량",
        "dataType": "NUMBER",
        "basicUnit": "개",
        "required": "MANDATORY",
        "exposed": "EXPOSED"
      }
    ],
    "noticeCategories": [...],
    "requiredDocumentNames": [...],
    "certifications": [...],
    "allowedOfferConditions": ["NEW", "REFURBISHED"]
  }
}
```

---

## 상품 생성 API

### 필수 attributes 자동 처리

상품 생성 시 필수 구매옵션(attributes)이 자동으로 처리됩니다.

**자동 처리 로직:**
- `MANDATORY` + `EXPOSED` 옵션 자동 추가
- 데이터 형식에 맞는 기본값 설정:
  - `NUMBER` 타입: `수량` → `1개`, `무게` → `1g`, `용량` → `1ml`
  - `STRING` 타입: `-`

**사용 예시:**
```python
from app.coupang_sync import register_product

# 상품 등록 (필수 attributes 자동 처리됨)
success, error = register_product(session, account_id, product_id)

if success:
    print("상품 등록 성공")
else:
    print(f"등록 실패: {error}")
```

### 2024년 10월 10일 규정 준수

- 필수 구매옵션 데이터 형식 엄격 적용
- 자유 구매옵션 구성 제한 카테고리 대응
- 인증/구비서류 자동 처리

---

## 상품 조회 API

### 1. 상품 등록 현황 조회

```python
code, data = client.get_inflow_status()

if code == 200:
    inflow = data["data"]
    restricted = inflow.get("restricted", False)
    registered = inflow.get("registeredCount", 0)
    permitted = inflow.get("permittedCount")
    
    if restricted:
        print("상품 등록이 제한됨")
    else:
        print(f"등록 가능: {registered}/{permitted}")
```

### 2. 상품 목록 페이징 조회

```python
code, data = client.get_products(
    vendor_id=vendor_id,
    status="APPROVED",
    max_per_page=20,
    next_token="2"
)

if code == 200:
    products = data.get("data", [])
    next_token = data.get("nextToken", "")
```

### 3. 상품 목록 구간 조회 (최대 10분)

```python
from datetime import datetime, timedelta, timezone

now = datetime.now(timezone.utc)
from_time = (now - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%S")
to_time = now.strftime("%Y-%m-%dT%H:%M:%S")

code, data = client.get_products_by_time_frame(from_time, to_time)
```

### 4. 상품 상태 변경 이력 조회

```python
code, data = client.get_product_status_history(
    seller_product_id,
    max_per_page=10
)

if code == 200:
    histories = data.get("data", [])
    for history in histories:
        print(f"{history.get('createdAt')}: {history.get('status')} - {history.get('comment')}")
```

### 5. 외부 SKU로 상품 조회

```python
code, data = client.get_products_by_external_sku(external_sku_code)

if code == 200:
    products = data.get("data", [])
    if products:
        seller_product_id = products[0].get("sellerProductId")
```

---

## 상품 수정 API

### 1. 상품 수정 (승인 필요)

```python
from app.coupang_sync import update_product_on_coupang

# 전체 상품 정보 수정 (승인 필요)
success, error = update_product_on_coupang(session, account_id, product_id)
```

**주의사항:**
- `sellerProductId`와 `sellerProductItemId` 필수
- 승인 완료 후 가격/재고 수정은 별도 API 사용

### 2. 배송/반품지 정보 수정 (승인 불필요)

```python
from app.coupang_sync import update_product_delivery_info

# 배송비만 수정 (즉시 반영)
success, error = update_product_delivery_info(
    session,
    account_id,
    product_id,
    delivery_charge=3000,
    delivery_charge_type="CONDITIONAL_FREE",
    free_ship_over_amount=10000
)
```

**수정 가능 항목:**
- `deliveryMethod`: 배송방법
- `deliveryCompanyCode`: 택배사 코드
- `deliveryChargeType`: 배송비종류
- `deliveryCharge`: 기본배송비
- `returnCenterCode`: 반품지 센터 코드
- 기타 배송/반품지 관련 정보

**제한사항:**
- `임시저장중`, `승인대기중` 상태는 수정 불가
- 승인 완료 상태만 수정 가능

---

## 상품 삭제 API

### 사용 예시

```python
from app.coupang_sync import delete_product_from_coupang

# 상품 삭제 (모든 옵션 판매중지 후 삭제)
success, error = delete_product_from_coupang(
    session,
    account_id,
    seller_product_id
)
```

**삭제 조건:**
- 상품이 `승인대기중` 상태가 아니어야 함
- 모든 옵션이 판매중지되어야 함

**삭제 순서:**
1. 모든 옵션 판매중지 처리
2. 상품 삭제 API 호출
3. DB에서 MarketListing 삭제

---

## 상품 아이템별 API

### 1. 재고/가격/판매상태 조회

```python
code, data = client.get_vendor_item_inventory(vendor_item_id)

if code == 200:
    inv = data["data"]
    stock = inv.get("amountInStock", 0)
    price = inv.get("salePrice", 0)
    is_on_sale = inv.get("onSale", False)
```

### 2. 수량 변경

```python
code, data = client.update_stock(vendor_item_id, quantity=100)

if code == 200:
    print("재고 변경 성공")
```

### 3. 가격 변경

```python
# 일반 가격 변경 (50% 증가/100% 감소 제한)
code, data = client.update_price(vendor_item_id, price=15000)

# 제한 없이 가격 변경
code, data = client.update_price(vendor_item_id, price=20000, force=True)
```

**가격 변경 제한:**
- 기본: 변경 전 판매가의 최대 50% 증가, 최대 100% 감소
- `force=True`: 제한 없이 변경 가능

### 4. 할인율 기준가격 변경

```python
code, data = client.update_original_price(vendor_item_id, original_price=20000)

if code == 200:
    print("할인율 기준가격 변경 성공")
```

**할인율 기준가 vs 판매가:**
- `originalPrice > salePrice`: 할인율 표시
- `originalPrice == salePrice`: '쿠팡가' 노출

### 5. 판매 상태 변경

```python
# 판매 중지
code, data = client.stop_sales(vendor_item_id)

# 판매 재개
code, data = client.resume_sales(vendor_item_id)
```

---

## 자동생성옵션 API

### 개별 옵션 제어

```python
# 활성화
code, data = client.activate_auto_generated_option(vendor_item_id)

# 비활성화
code, data = client.deactivate_auto_generated_option(vendor_item_id)
```

### 전체 옵션 제어

```python
# 전체 활성화
code, data = client.activate_auto_generated_options_all()

# 전체 비활성화
code, data = client.deactivate_auto_generated_options_all()
```

**주의사항:**
- 승인 완료된 상품에서만 사용 가능
- 이미 자동 생성된 옵션은 삭제되지 않음
- 더 이상 옵션이 생성되지 않도록 설정

---

## 에러 처리

### 에러 메시지 정규화

쿠팡 API 에러 메시지가 자동으로 정규화됩니다.

```python
code, data = client.get_product(seller_product_id)

if code != 200:
    # 정규화된 에러 메시지 확인
    normalized_msg = data.get("_normalized_message", data.get("message"))
    print(f"에러: {normalized_msg}")
```

### HTTP 상태 코드별 처리

- **400**: 요청 파라미터 오류
- **401**: 인증 오류
- **404**: 리소스를 찾을 수 없음
- **429**: 요청 한도 초과 (재시도 필요)
- **500**: 서버 오류 (재시도 필요)

### 재시도 로직

429 에러의 경우 자동으로 재시도됩니다:
- 지수 백오프 (2초 → 4초 → 8초)
- 최대 3회 재시도

---

## 테스트 스크립트

### 카테고리 메타정보 테스트

```bash
python scripts/test_coupang_category_meta.py
```

### 상품 생성 테스트

```bash
python scripts/test_coupang_product_creation.py
```

### 상품 관리 통합 테스트

```bash
python scripts/test_coupang_product_management.py
```

---

## 참고 자료

- [쿠팡 API 공식 문서](https://developers.coupang.com/)
- [카테고리 메타정보 API 문서](docs/api_docs/coupang/category_api.md)
- [상품 API 문서](docs/api_docs/coupang/product_api.md)

---

## 업데이트 이력

- **2024-12-27**: 쿠팡 상품 관련 API 점검 및 개선 완료
  - 카테고리 메타정보 통합 API로 변경
  - 필수 attributes 자동 처리 추가
  - 상품 조회 관련 API 4개 추가
  - 상품 아이템별 API 2개 추가
  - 자동생성옵션 API 4개 추가
  - 에러 처리 개선
