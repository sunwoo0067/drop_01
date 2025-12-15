# 쿠팡 상품 API 문서

> **API 적용 가능한 구매자 사용자 지역**: 한국

---

## 1. 상품 생성

쿠팡에서 판매할 상품을 등록하는 API입니다.

### 기본 정보

| 항목 | 내용 |
|------|------|
| **HTTP Method** | `POST` |
| **Endpoint** | `/v2/providers/seller_api/apis/api/v1/marketplace/seller-products` |
| **Example URL** | `https://api-gateway.coupang.com/v2/providers/seller_api/apis/api/v1/marketplace/seller-products` |

### 주요 요청 파라미터 (Body)

| 파라미터명 | 타입 | 필수 | 설명 |
|-----------|------|------|------|
| `displayCategoryCode` | Number | ✓ | 노출카테고리코드 |
| `sellerProductName` | String | ✓ | 등록상품명 (최대 100자) |
| `vendorId` | String | ✓ | 판매자ID (=업체코드) |
| `displayProductName` | String | ✓ | 노출상품명 (최대 100자) |
| `brand` | String | ✓ | 브랜드 |
| `generalProductName` | String | ✓ | 제품명 |
| `deliveryMethod` | String | ✓ | 배송방법 (SEQUENCIAL, COLD_FRESH, MAKE_ORDER 등) |
| `deliveryCompanyCode` | String | ✓ | 택배사 코드 |
| `deliveryChargeType` | String | ✓ | 배송비종류 (FREE, NOT_FREE, CHARGE_RECEIVED 등) |
| `returnCenterCode` | String | ✓ | 반품지센터코드 |
| `returnCharge` | Number | ✓ | 반품배송비 |
| `vendorUserId` | String | ✓ | 실사용자아이디 (쿠팡 Wing ID) |
| `requested` | Boolean | - | 자동승인요청여부 (true/false) |
| `items` | Array | ✓ | 업체상품옵션목록 (최대 200개) |

### items 배열 주요 파라미터

| 파라미터명 | 타입 | 필수 | 설명 |
|-----------|------|------|------|
| `itemName` | String | ✓ | 업체상품옵션명 (최대 150자) |
| `originalPrice` | Number | ✓ | 할인율기준가 (정가) |
| `salePrice` | Number | ✓ | 판매가격 |
| `maximumBuyCount` | Number | - | 최대구매수량 |
| `vendorItemId` | String | - | 판매자상품옵션코드 |
| `barcode` | String | - | 바코드 (13자리) |
| `images` | Array | - | 이미지 정보 |
| `contents` | Array | ✓ | 상세설명 |
| `attributes` | Array | ✓ | 구매옵션 |
| `noticeCategories` | Array | ✓ | 상품고시정보 |

### 응답 파라미터

| 파라미터명 | 타입 | 설명 |
|-----------|------|------|
| `code` | String | 결과코드 (SUCCESS/ERROR) |
| `message` | String | 메세지 |
| `data` | String | 등록상품ID (sellerProductId) |

---

## 2. 상품 승인 요청

임시저장 상태의 상품을 승인 요청하여 판매 가능 상태로 변경합니다.

### 기본 정보

| 항목 | 내용 |
|------|------|
| **HTTP Method** | `PUT` |
| **Endpoint** | `/v2/providers/seller_api/apis/api/v1/marketplace/seller-products/{sellerProductId}/approvals` |

### 요청 파라미터 (Path)

| 파라미터명 | 타입 | 필수 | 설명 |
|-----------|------|------|------|
| `sellerProductId` | Number | ✓ | 등록상품ID |

### 응답 예시

```json
{
  "code": "SUCCESS",
  "message": "1320***567 승인 요청되었습니다.",
  "data": "1320***567"
}
```

### 주의사항
- '임시저장', '승인완료', '승인반려', '부분승인완료' 상태에서만 요청 가능
- 상품 생성/수정 시 `requested=true`로 설정하면 자동 승인 요청됨

---

## 3. 상품 수정 (승인필요)

업체상품 정보를 수정합니다. 승인 후에 반영됩니다.

### 기본 정보

| 항목 | 내용 |
|------|------|
| **HTTP Method** | `PUT` |
| **Endpoint** | `/v2/providers/seller_api/apis/api/v1/marketplace/seller-products` |

### 요청 파라미터 (Body)

상품 생성 API와 거의 동일하며, 추가로 다음 파라미터가 필요합니다:

| 파라미터명 | 타입 | 필수 | 설명 |
|-----------|------|------|------|
| `sellerProductId` | Number | ✓ | 등록상품ID |
| `items.sellerProductItemId` | Number | - | 옵션 수정/삭제 시 필요 |

### 주의사항
- '상품 조회 API'로 조회된 JSON 전체에서 수정 후 전송
- 옵션 수정/삭제/추가 가능하지만, 승인 이력이 있는 옵션 삭제는 불가
- 가격/재고/상태 등은 별도 API를 사용

---

## 4. 상품 삭제

등록된 상품을 삭제합니다.

### 기본 정보

| 항목 | 내용 |
|------|------|
| **HTTP Method** | `DELETE` |
| **Endpoint** | `/v2/providers/seller_api/apis/api/v1/marketplace/seller-products/{sellerProductId}` |

### 요청 파라미터 (Path)

| 파라미터명 | 타입 | 필수 | 설명 |
|-----------|------|------|------|
| `sellerProductId` | Number | ✓ | 등록상품ID |

### 주의사항
- 상품이 승인대기중 상태가 아니어야 함
- 상품에 포함된 옵션(아이템)이 모두 판매중지된 경우에만 삭제 가능

---

## 5. 상품 목록 페이징 조회

등록상품 목록을 페이징 조회합니다.

### 기본 정보

| 항목 | 내용 |
|------|------|
| **HTTP Method** | `GET` |
| **Endpoint** | `/v2/providers/seller_api/apis/api/v1/marketplace/seller-products` |

### 요청 파라미터 (Query String)

| 파라미터명 | 타입 | 필수 | 설명 |
|-----------|------|------|------|
| `vendorId` | String | ✓ | 판매자 ID |
| `nextToken` | Number | - | 다음 페이지 키값 (첫 페이지는 1 또는 미입력) |
| `maxPerPage` | Number | - | 페이지당 건수 (기본 10, 최대 100) |
| `sellerProductId` | Number | - | 등록상품ID |
| `sellerProductName` | String | - | 등록상품명 (20자 이하) |
| `status` | String | - | 업체상품상태 |
| `createdAt` | String | - | 상품등록일시 ("yyyy-MM-dd") |

### 상품 상태 (status) 값

| 값 | 설명 |
|----|------|
| `IN_REVIEW` | 심사중 |
| `SAVED` | 임시저장 |
| `APPROVING` | 승인대기 |
| `APPROVED` | 승인완료 |
| `PARTIAL_APPROVED` | 부분승인완료 |
| `DENIED` | 승인반려 |
| `DELETED` | 삭제 |

### 응답 파라미터

| 파라미터명 | 타입 | 설명 |
|-----------|------|------|
| `nextToken` | String | 다음페이지 키 (없으면 빈 문자열) |
| `data` | Array | 상품 목록 배열 |
| `data.sellerProductId` | String | 등록상품ID |
| `data.sellerProductName` | String | 등록상품명 |
| `data.displayCategoryCode` | Number | 노출카테고리코드 |
| `data.statusName` | String | 등록상품상태 |

---

## 6. 상품 아이템별 수량 변경

상품 아이템별 재고수량을 변경합니다.

### 기본 정보

| 항목 | 내용 |
|------|------|
| **HTTP Method** | `PUT` |
| **Endpoint** | `/v2/providers/seller_api/apis/api/v1/marketplace/vendor-items/{vendorItemId}/quantities/{quantity}` |

### 요청 파라미터 (Path)

| 파라미터명 | 타입 | 필수 | 설명 |
|-----------|------|------|------|
| `vendorItemId` | Number | ✓ | 옵션ID |
| `quantity` | Number | ✓ | 재고수량 |

### 응답 예시

```json
{
  "code": "SUCCESS",
  "message": "재고 변경을 완료했습니다."
}
```

---

## 7. 상품 아이템별 가격 변경

상품 아이템별 판매가격을 변경합니다.

### 기본 정보

| 항목 | 내용 |
|------|------|
| **HTTP Method** | `PUT` |
| **Endpoint** | `/v2/providers/seller_api/apis/api/v1/marketplace/vendor-items/{vendorItemId}/prices/{price}` |

### 요청 파라미터 (Path)

| 파라미터명 | 타입 | 필수 | 설명 |
|-----------|------|------|------|
| `vendorItemId` | Number | ✓ | 옵션ID |
| `price` | Number | ✓ | 가격 (최소 10원 단위) |

### 요청 파라미터 (Query String)

| 파라미터명 | 타입 | 필수 | 설명 |
|-----------|------|------|------|
| `forceSalePriceUpdate` | Boolean | - | 가격 변경 비율 제한 여부 (true: 제한 없음) |

### 응답 예시

```json
{
  "code": "SUCCESS",
  "message": "가격 변경을 완료했습니다.",
  "data": null
}
```

### 주의사항
- 가격 변경 범위 초과 시 `forceSalePriceUpdate=true`로 해결 가능

---

## 8. 상품 아이템별 판매 중지

상품 아이템별 판매상태를 판매중지로 변경합니다.

### 기본 정보

| 항목 | 내용 |
|------|------|
| **HTTP Method** | `PUT` |
| **Endpoint** | `/v2/providers/seller_api/apis/api/v1/marketplace/vendor-items/{vendorItemId}/sales/stop` |

### 요청 파라미터 (Path)

| 파라미터명 | 타입 | 필수 | 설명 |
|-----------|------|------|------|
| `vendorItemId` | Number | ✓ | 옵션ID |

### 응답 예시

```json
{
  "code": "SUCCESS",
  "message": "판매 중지 처리되었습니다."
}
```

---

## 9. 상품 아이템별 판매 재개

상품 아이템별 판매상태를 판매중으로 변경합니다.

### 기본 정보

| 항목 | 내용 |
|------|------|
| **HTTP Method** | `PUT` |
| **Endpoint** | `/v2/providers/seller_api/apis/api/v1/marketplace/vendor-items/{vendorItemId}/sales/resume` |

### 요청 파라미터 (Path)

| 파라미터명 | 타입 | 필수 | 설명 |
|-----------|------|------|------|
| `vendorItemId` | Number | ✓ | 옵션ID |

### 응답 예시

```json
{
  "code": "SUCCESS",
  "message": "판매가 재개되었습니다."
}
```

### 주의사항
- 모니터링으로 판매중지된 경우 재개 불가
