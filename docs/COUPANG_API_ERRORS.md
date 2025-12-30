# 쿠팡 API 에러 처리 가이드

이 문서는 쿠팡 API에서 발생할 수 있는 에러와 해결 방법을 설명합니다.

## 목차

1. [HTTP 상태 코드별 에러](#http-상태-코드별-에러)
2. [상품 생성 에러](#상품-생성-에러)
3. [상품 수정 에러](#상품-수정-에러)
4. [상품 삭제 에러](#상품-삭제-에러)
5. [상품 아이템별 에러](#상품-아이템별-에러)
6. [에러 처리 모범 사례](#에러-처리-모범-사례)

---

## HTTP 상태 코드별 에러

### 400 (Bad Request) - 요청 파라미터 오류

**원인:**
- 필수 파라미터 누락
- 잘못된 파라미터 형식
- 유효하지 않은 값

**해결 방법:**
```python
code, data = client.create_product(payload)

if code == 400:
    error_msg = data.get("message", "")
    
    # 필수 attributes 누락
    if "필수 구매 옵션이 존재하지 않습니다" in error_msg:
        # 카테고리 메타정보 조회하여 필수 attributes 확인
        code, meta = client.get_category_meta(category_code)
        # 필수 attributes 추가 후 재시도
    
    # 유효하지 않은 구매 옵션
    if "유효하지 않은 구매 옵션이 존재합니다" in error_msg:
        # 자유 구매 옵션 구성이 제한된 카테고리
        # 필수 구매 옵션만 입력
```

### 401 (Unauthorized) - 인증 오류

**원인:**
- 잘못된 access_key 또는 secret_key
- 서명 오류
- 만료된 인증 정보

**해결 방법:**
```python
# 인증 정보 확인
if code == 401:
    error_msg = data.get("message", "")
    
    if "Invalid signature" in error_msg:
        # 서명 오류 - 자동으로 1회 재시도됨
        pass
    else:
        # 인증 정보 재확인 필요
        print("인증 정보를 확인하세요")
```

### 404 (Not Found) - 리소스를 찾을 수 없음

**원인:**
- 존재하지 않는 상품 ID
- 삭제된 상품
- 잘못된 vendorItemId

**해결 방법:**
```python
if code == 404:
    error_msg = data.get("message", "")
    
    if "상품" in error_msg and "없습니다" in error_msg:
        # 상품이 삭제되었거나 존재하지 않음
        print("상품을 찾을 수 없습니다")
```

### 429 (Too Many Requests) - 요청 한도 초과

**원인:**
- API 호출 빈도 제한 초과
- 초당 10건 이상 호출

**해결 방법:**
```python
# 자동 재시도 로직 (이미 구현됨)
# 지수 백오프: 2초 → 4초 → 8초
# 최대 3회 재시도

if code == 429:
    # 자동으로 재시도됨
    # 수동 재시도 시:
    import time
    time.sleep(2)  # 2초 대기 후 재시도
```

### 500 (Internal Server Error) - 서버 오류

**원인:**
- 쿠팡 서버 일시적 오류
- 시스템 점검 중

**해결 방법:**
```python
if code >= 500:
    # 일정 시간 후 재시도
    import time
    time.sleep(1)
    # 재시도 로직
```

---

## 상품 생성 에러

### 필수 구매 옵션이 존재하지 않습니다

**에러 메시지:**
```
필수 구매 옵션이 존재하지 않습니다. Missing Attribute(s)
```

**해결 방법:**
```python
# 1. 카테고리 메타정보 조회
code, meta = client.get_category_meta(category_code)

# 2. 필수 attributes 확인
attrs = meta["data"].get("attributes", [])
mandatory_attrs = [
    a for a in attrs 
    if a.get("required") == "MANDATORY" and a.get("exposed") == "EXPOSED"
]

# 3. 필수 attributes 추가
# _map_product_to_coupang_payload()에서 자동 처리됨
```

### 유효하지 않은 구매 옵션이 존재합니다

**에러 메시지:**
```
유효하지 않은 구매 옵션이 존재합니다. Attribute(s) Not Allowed
```

**해결 방법:**
```python
# 자유 구매 옵션 구성이 제한된 카테고리
# 필수 구매 옵션만 입력
# _map_product_to_coupang_payload()에서 자동 처리됨
```

### 유효하지 않은 구매 옵션 값 혹은 단위가 존재합니다

**에러 메시지:**
```
유효하지 않은 구매 옵션 값 혹은 단위가 존재합니다. Invalid Attribute Value(s)
```

**해결 방법:**
```python
# 데이터 형식 및 단위 확인
# 카테고리 메타정보의 dataType, basicUnit, usableUnits 확인
# _map_product_to_coupang_payload()에서 자동 처리됨
```

### 입력된 상품필수 고지정보가 카테고리에서 제공하는 것과 다릅니다

**에러 메시지:**
```
입력된 상품필수 고지정보[예) 제조자 및 제조판매업자]가 카테고리[예)화장품]에서 제공하는 것과 다릅니다.
```

**해결 방법:**
```python
# 카테고리 메타정보의 noticeCategories 확인
# 필수 고시정보만 입력
# _map_product_to_coupang_payload()에서 자동 처리됨
```

---

## 상품 수정 에러

### 카테고리의 필수 속성이 존재하지 않습니다

**에러 메시지:**
```
카테고리의 필수 속성이 존재하지 않습니다.
```

**해결 방법:**
```python
# 상품 수정 시에도 필수 attributes 필요
# 카테고리 메타정보 조회하여 필수 attributes 확인
# update_product_on_coupang()에서 자동 처리됨
```

### 상품 정보가 등록 또는 수정되고 있습니다

**에러 메시지:**
```
상품 정보가 등록 또는 수정되고 있습니다. 잠시 후 다시 조회해 주시기 바랍니다.
```

**해결 방법:**
```python
# 최소 10분 이후에 다시 시도
import time
time.sleep(600)  # 10분 대기
```

---

## 상품 삭제 에러

### 업체상품이 없거나 삭제가 불가능한 상태입니다

**에러 메시지:**
```
업체상품[103***11234]이 없거나 삭제가 불가능한 상태입니다. 
삭제는 '저장중', '임시저장' 상태에서만 가능합니다.
```

**해결 방법:**
```python
# 1. 상품 상태 확인
code, data = client.get_product(seller_product_id)
status = data["data"].get("statusName", "")

# 2. 모든 옵션 판매중지
items = data["data"].get("items", [])
for item in items:
    vendor_item_id = item.get("vendorItemId")
    if vendor_item_id:
        client.stop_sales(str(vendor_item_id))

# 3. 삭제 시도
# delete_product_from_coupang()에서 자동 처리됨
```

---

## 상품 아이템별 에러

### 가격변경에 실패했습니다

**에러 메시지:**
```
가격변경에 실패했습니다. [옵션ID[3572***698] : 판매가 변경이 불가능합니다. 
변경전 판매가의 최대 50% 인하/최대 100%인상까지 변경가능합니다.]
```

**해결 방법:**
```python
# force=True로 제한 없이 변경
code, data = client.update_price(vendor_item_id, new_price, force=True)
```

### 가격은 최소 10원 단위로 입력가능합니다

**에러 메시지:**
```
가격변경에 실패했습니다. [옵션ID[4685***739]: 가격은 최소 10원 단위로 입력가능합니다. (1원단위 입력 불가)]
```

**해결 방법:**
```python
# 10원 단위로 반올림
price = int(price / 10) * 10
code, data = client.update_price(vendor_item_id, price)
```

### 재고변경에 실패했습니다

**에러 메시지:**
```
재고변경에 실패했습니다. [옵션ID[3048***251] : 삭제된 상품은 변경이 불가능합니다.]
```

**해결 방법:**
```python
# 상품 상태 확인
code, data = client.get_product(seller_product_id)
status = data["data"].get("statusName", "")

if status == "상품삭제":
    print("삭제된 상품은 수정할 수 없습니다")
```

### 판매재개에 실패했습니다

**에러 메시지:**
```
판매재개에 실패했습니다. [옵션ID(55895***47)은 쿠팡의 모니터링에 의해 '판매중지'된 상품입니다.]
```

**해결 방법:**
```python
# 쿠팡 판매자콜센터 또는 온라인 문의로 문의
# API로는 해결 불가
```

---

## 에러 처리 모범 사례

### 1. 에러 메시지 정규화 활용

```python
code, data = client.create_product(payload)

if code != 200:
    # 정규화된 에러 메시지 확인
    normalized_msg = data.get("_normalized_message", data.get("message"))
    print(f"에러: {normalized_msg}")
```

### 2. 재시도 로직 구현

```python
import time

def create_product_with_retry(client, payload, max_retries=3):
    for attempt in range(max_retries):
        code, data = client.create_product(payload)
        
        if code == 200:
            return code, data
        
        # 429 에러는 자동 재시도됨
        if code == 429:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # 지수 백오프
                time.sleep(wait_time)
                continue
        
        # 500 에러는 재시도
        if code >= 500:
            if attempt < max_retries - 1:
                time.sleep(1)
                continue
        
        # 그 외 에러는 즉시 반환
        return code, data
    
    return code, data
```

### 3. 에러 로깅

```python
import logging

logger = logging.getLogger(__name__)

code, data = client.create_product(payload)

if code != 200:
    error_msg = data.get("_normalized_message", data.get("message"))
    logger.error(
        f"상품 생성 실패: {error_msg}",
        extra={
            "http_code": code,
            "error_data": data,
            "payload": payload
        }
    )
```

### 4. 사용자 친화적인 에러 메시지

```python
def handle_coupang_error(code, data):
    """쿠팡 API 에러를 사용자 친화적인 메시지로 변환"""
    error_msg = data.get("_normalized_message", data.get("message", ""))
    
    error_mapping = {
        "필수 구매 옵션이 존재하지 않습니다": "필수 구매 옵션을 확인하세요",
        "유효하지 않은 구매 옵션이 존재합니다": "구매 옵션을 확인하세요",
        "가격변경에 실패했습니다": "가격 변경 범위를 확인하세요",
        "재고변경에 실패했습니다": "재고 수량을 확인하세요",
    }
    
    for key, value in error_mapping.items():
        if key in error_msg:
            return value
    
    return error_msg
```

---

## 참고 자료

- [쿠팡 API 공식 문서](https://developers.coupang.com/)
- [쿠팡 API 사용 가이드](COUPANG_API_GUIDE.md)
