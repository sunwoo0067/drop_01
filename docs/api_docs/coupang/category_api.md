# 쿠팡 카테고리 API 문서

> **API 적용 가능한 구매자 사용자 지역**: 한국

---

## 1. 카테고리 메타정보 조회

노출 카테고리코드를 이용하여 해당 카테고리에 속한 고시정보, 옵션, 구비서류, 인증정보 목록 등을 조회합니다.

### 기본 정보

| 항목 | 내용 |
|------|------|
| **HTTP Method** | `GET` |
| **Endpoint** | `/v2/providers/seller_api/apis/api/v1/marketplace/meta/category-related-metas/display-category-codes/{displayCategoryCode}` |
| **Example URL** | `https://api-gateway.coupang.com/v2/providers/seller_api/apis/api/v1/marketplace/meta/category-related-metas/display-category-codes/78877` |

### 요청 파라미터 (Path)

| 파라미터명 | 타입 | 필수 | 설명 |
|-----------|------|------|------|
| `displayCategoryCode` | Number | ✓ | 노출카테고리코드 |

### 응답 파라미터

| 파라미터명 | 타입 | 설명 |
|-----------|------|------|
| `isAllowSingleItem` | Boolean | 단일상품 등록 가능 여부 |
| `attributes` | Array | 카테고리 옵션목록 |
| `attributes.attributeTypeName` | String | 옵션타입명 |
| `attributes.required` | String | 필수여부 (MANDATORY, OPTIONAL) |
| `attributes.dataType` | String | 데이터형식 (STRING, NUMBER, DATE) |
| `attributes.basicUnit` | String | 기본단위 |
| `attributes.usableUnits` | Array | 사용가능한단위값목록 |
| `attributes.groupNumber` | String | 그룹속성값 (NONE, 1, 2) |
| `attributes.exposed` | String | 구매옵션/검색옵션 (EXPOSED, NONE) |
| `noticeCategories` | Array | 상품고시정보목록 |
| `noticeCategories.noticeCategoryName` | String | 상품고시정보카테고리명 |
| `noticeCategories.noticeCategoryDetailNames` | Array | 상품고시정보카테고리상세목록 |
| `noticeCategories.noticeCategoryDetailNames.noticeCategoryDetailName` | String | 상품고시정보카테고리상세명 |
| `noticeCategories.noticeCategoryDetailNames.required` | String | 필수여부 (MANDATORY, OPTIONAL) |
| `requiredDocumentNames` | Array | 구비서류목록 |
| `requiredDocumentNames.templateName` | String | 구비서류명 |
| `requiredDocumentNames.required` | String | 필수여부 (MANDATORY, OPTIONAL) |
| `certifications` | Array | 상품 인증 정보 |
| `certifications.certificationType` | String | 인증타입 |
| `certifications.name` | String | 인증정보 이름 |
| `certifications.dataType` | String | 데이터타입 (CODE, NONE) |
| `certifications.required` | String | 필수여부 (MANDATORY, RECOMMEND, OPTIONAL) |

### 주의사항

- 상품 생성 시, 쿠팡에서 규정하고 있는 각 카테고리의 메타 정보와 일치하는 항목으로 상품 생성 전문을 구성해야 합니다.
- 2024년 10월 10일부터 필수 구매옵션 입력 시 데이터 형식에 맞게 입력해야 합니다.
- 자유로운 구매옵션 구성(open attribute) 가능하나, 2024년 10월 10일부터 자유 구매옵션 구성 시 노출 제한됩니다.

---

## 2. 카테고리 추천

상품 정보(상품명, 브랜드, 속성 등)를 입력하면 가장 일치하는 쿠팡 카테고리(displayCategoryCode)를 제안합니다. 머신러닝 모델 기반이며, 부정확한 정보 입력 시 정확도가 떨어질 수 있습니다.

### 기본 정보

| 항목 | 내용 |
|------|------|
| **HTTP Method** | `POST` |
| **Endpoint** | `/v2/providers/openapi/apis/api/v1/categorization/predict` |
| **Example URL** | `https://api-gateway.coupang.com/v2/providers/openapi/apis/api/v1/categorization/predict` |

### 요청 파라미터 (Body)

| 파라미터명 | 타입 | 필수 | 설명 |
|-----------|------|------|------|
| `productName` | String | - | 상품명 |
| `productDescription` | String | - | 상품에 대한 상세설명 |
| `brand` | String | - | 브랜드 |
| `attributes` | Object | - | 상품속성정보 (예: 사이즈, 색상, 소재 등) |
| `sellerSkuCode` | String | - | 판매자상품코드(업체상품코드) |

### 요청 예시

```json
{
  "productName": "코데즈컴바인 양트임싱글코트",
  "productDescription": "모니터 해상도, 밝기, 컴퓨터 사양 등에 따라 실물과 약간의 색상차이가 있을 수 있습니다...",
  "brand": "코데즈컴바인",
  "attributes": {
    "제품 소재": "모달:53.8 폴리:43.2 레이온:2.4 면:0.6",
    "색상": "베이지,네이비",
    "제조국": "한국"
  },
  "sellerSkuCode": "123123"
}
```

### 응답 파라미터

| 파라미터명 | 타입 | 설명 |
|-----------|------|------|
| `autoCategorizationPredictionResultType` | String | 결과 타입 (SUCCESS, FAILURE, INSUFFICIENT_INFORMATION) |
| `comment` | String | 코멘트 |
| `predictedCategoryId` | String | 추천 카테고리ID (displayCategoryCode) |
| `predictedCategoryName` | String | 추천 카테고리 명 |

### 응답 예시

```json
{
  "code": 200,
  "message": "OK",
  "data": {
    "autoCategorizationPredictionResultType": "SUCCESS",
    "predictedCategoryId": "63950",
    "predictedCategoryName": "일반 섬유유연제",
    "comment": null
  }
}
```

### 주의사항

- 상품 특성이 잘 나타나도록 상품명을 상세히 입력해야 합니다.
- 하나의 상품명에 다른 타입 상품이 섞이지 않도록 주의해야 합니다.

---

## 3. 카테고리 자동 매칭 서비스 동의 확인

판매자ID가 현재 카테고리 자동매칭 서비스에 동의했는지 체크합니다.

### 기본 정보

| 항목 | 내용 |
|------|------|
| **HTTP Method** | `GET` |
| **Endpoint** | `/v2/providers/seller_api/apis/api/v1/marketplace/vendors/{vendorId}/check-auto-category-agreed` |
| **Example URL** | `https://api-gateway.coupang.com/v2/providers/seller_api/apis/api/v1/marketplace/vendors/A00123456/check-auto-category-agreed` |

### 요청 파라미터 (Path)

| 파라미터명 | 타입 | 필수 | 설명 |
|-----------|------|------|------|
| `vendorId` | String | ✓ | 판매자ID (=업체코드) |

### 응답 파라미터

| 파라미터명 | 타입 | 설명 |
|-----------|------|------|
| `code` | String | SUCCESS/ERROR |
| `message` | String | 메세지 |
| `data` | Boolean | 동의여부 (true or false) |

### 응답 예시

```json
{
  "code": "SUCCESS",
  "message": "",
  "data": true
}
```

### Error Spec

| HTTP 상태 | 오류 내용 | 설명 |
|----------|----------|------|
| 400 | 요청변수확인 | 업체[A00123456]는 다른 업체[A0012***]의 정보을 검색 수 없습니다. (올바른 판매자ID 확인 필요) |

---

## 4. 카테고리 목록조회

노출 카테고리 목록 전체를 조회합니다.

### 기본 정보

| 항목 | 내용 |
|------|------|
| **HTTP Method** | `GET` |
| **Endpoint** | `/v2/providers/seller_api/apis/api/v1/marketplace/meta/display-categories` |
| **Example URL** | `https://api-gateway.coupang.com/v2/providers/seller_api/apis/api/v1/marketplace/meta/display-categories` |

### 요청 파라미터

없음 (Request Body 불필요)

### 응답 파라미터

| 파라미터명 | 타입 | 설명 |
|-----------|------|------|
| `code` | String | 결과코드 (SUCCESS/ERROR) |
| `message` | String | 메세지 |
| `data` | Object | 노출카테고리목록 (계층 구조) |
| `data.displayCategoryCode` | String | 노출카테고리코드 (최상위는 0) |
| `data.name` | String | 노출카테고리명 (최상위는 'ROOT') |
| `data.status` | String | 노출카테고리상태 (ACTIVE, READY, DISABLED) |
| `data.child` | Array | 하위노출카테고리 목록 (구조는 부모와 동일) |

### 응답 예시

```json
{
  "code": "SUCCESS",
  "message": "",
  "data": {
    "displayItemCategoryCode": 0,
    "name": "ROOT",
    "status": "ACTIVE",
    "child": [
      {
        "displayItemCategoryCode": 69182,
        "name": "패션의류잡화",
        "status": "ACTIVE",
        "child": [
          {
            "displayItemCategoryCode": 69183,
            "name": "여성패션",
            "status": "ACTIVE",
            "child": []
          }
        ]
      }
    ]
  }
}
```

---

## 5. 카테고리 조회

카테고리 정보를 노출 카테고리 코드(displayCategoryCode)를 이용하여 조회합니다.

### 기본 정보

| 항목 | 내용 |
|------|------|
| **HTTP Method** | `GET` |
| **Endpoint** | `/v2/providers/seller_api/apis/api/v1/marketplace/meta/display-categories/{displayCategoryCode}` |
| **Example URL** | `https://api-gateway.coupang.com/v2/providers/seller_api/apis/api/v1/marketplace/meta/display-categories/0` |

### 요청 파라미터 (Path)

| 파라미터명 | 타입 | 필수 | 설명 |
|-----------|------|------|------|
| `displayCategoryCode` | String | ✓ | 노출카테고리코드 (1 Depth 조회 시 0) |

### 응답 파라미터

| 파라미터명 | 타입 | 설명 |
|-----------|------|------|
| `displayCategoryCode` | String | 노출카테고리코드 |
| `name` | String | 노출카테고리명 |
| `status` | String | 노출카테고리상태 (ACTIVE, READY, DISABLED) |
| `child` | Array | 하위노출카테고리 목록 (1 Depth 하위) |

### 응답 예시

```json
{
  "code": "SUCCESS",
  "message": "",
  "data": {
    "displayItemCategoryCode": 0,
    "name": "ROOT",
    "status": "ACTIVE",
    "child": [
      {
        "displayItemCategoryCode": 77834,
        "name": "가구/홈데코",
        "status": "ACTIVE",
        "child": []
      },
      {
        "displayItemCategoryCode": 62588,
        "name": "가전/디지털",
        "status": "ACTIVE",
        "child": []
      }
    ]
  }
}
```

### 주의사항

- 1 Depth 카테고리 정보 조회는 노출카테고리코드 값을 `0`으로 설정 후 호출합니다.

---

## 6. 카테고리 유효성 검사

해당 노출 카테고리가 현재 사용 가능한지 체크합니다.

### 기본 정보

| 항목 | 내용 |
|------|------|
| **HTTP Method** | `GET` |
| **Endpoint** | `/v2/providers/seller_api/apis/api/v1/marketplace/meta/display-categories/{displayCategoryCode}/status` |
| **Example URL** | `https://api-gateway.coupang.com/v2/providers/seller_api/apis/api/v1/marketplace/meta/display-categories/{displayCategoryCode}/status` |

### 요청 파라미터 (Path)

| 파라미터명 | 타입 | 필수 | 설명 |
|-----------|------|------|------|
| `displayCategoryCode` | String | ✓ | 노출카테고리코드 |

### 응답 파라미터

| 파라미터명 | 타입 | 설명 |
|-----------|------|------|
| `code` | String | SUCCESS/ERROR |
| `message` | String | 메세지 |
| `data` | Boolean | 사용가능여부 (true or false) |

### 응답 예시

```json
{
  "code": "SUCCESS",
  "message": "",
  "data": true
}
```

### Error Spec

| HTTP 상태 | 오류 내용 | 설명 |
|----------|----------|------|
| 400 | 요청변수확인 | 노출카테고리코드는 숫자형으로 입력해주세요. |
| 400 | 요청변수확인 | 노출카테고리 72631은 leaf category code가 아닙니다. (최하단 카테고리만 입력 가능) |

### 주의사항

- 카테고리 리뉴얼 등으로 인해 사용 중인 카테고리가 변경될 수 있습니다.
- 리뉴얼은 연 2회이며 사전 공지되므로 수시 검사 필요는 없습니다.
