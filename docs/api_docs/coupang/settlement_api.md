# 쿠팡 정산 API 문서

> **API 적용 가능한 구매자 사용자 지역**: 한국

---

## 1. 매출내역 조회

매출 내역을 조회합니다.

### 기본 정보

| 항목 | 내용 |
|------|------|
| **HTTP Method** | `GET` |
| **Endpoint** | `/v2/providers/openapi/apis/api/v4/vendors/{vendorId}/settlements/sales` |

### 요청 파라미터 (Path)

| 파라미터명 | 타입 | 필수 | 설명 |
|-----------|------|------|------|
| `vendorId` | String | ✓ | 판매자 ID |

### 요청 파라미터 (Query String)

| 파라미터명 | 타입 | 필수 | 설명 |
|-----------|------|------|------|
| `recognitionDateFrom` | String | ✓ | 매출인식 시작일 (yyyy-MM-dd) |
| `recognitionDateTo` | String | ✓ | 매출인식 종료일 (yyyy-MM-dd) |
| `orderId` | Number | - | 주문번호 |
| `vendorItemId` | Number | - | 옵션ID |
| `nextToken` | String | - | 다음 페이지 토큰 |
| `maxPerPage` | Number | - | 페이지당 최대 조회 수 (default=50) |

### 응답 파라미터

| 파라미터명 | 타입 | 설명 |
|-----------|------|------|
| `orderId` | Number | 주문번호 |
| `orderDate` | String | 주문일시 |
| `recognitionDate` | String | 매출인식일 |
| `vendorItemId` | Number | 옵션ID |
| `vendorItemName` | String | 상품명 |
| `quantity` | Number | 수량 |
| `salePrice` | Number | 판매가격 |
| `commissionRate` | Number | 수수료율 |
| `commission` | Number | 수수료 |
| `settlementAmount` | Number | 정산금액 |

---

## 2. 지급내역 조회

지급 내역을 조회합니다.

### 기본 정보

| 항목 | 내용 |
|------|------|
| **HTTP Method** | `GET` |
| **Endpoint** | `/v2/providers/openapi/apis/api/v4/vendors/{vendorId}/settlements/payments` |

### 요청 파라미터 (Path)

| 파라미터명 | 타입 | 필수 | 설명 |
|-----------|------|------|------|
| `vendorId` | String | ✓ | 판매자 ID |

### 요청 파라미터 (Query String)

| 파라미터명 | 타입 | 필수 | 설명 |
|-----------|------|------|------|
| `paymentDateFrom` | String | ✓ | 지급 시작일 (yyyy-MM-dd) |
| `paymentDateTo` | String | ✓ | 지급 종료일 (yyyy-MM-dd) |
| `nextToken` | String | - | 다음 페이지 토큰 |
| `maxPerPage` | Number | - | 페이지당 최대 조회 수 |

### 응답 파라미터

| 파라미터명 | 타입 | 설명 |
|-----------|------|------|
| `paymentDate` | String | 지급일 |
| `paymentAmount` | Number | 지급금액 |
| `paymentType` | String | 지급유형 |
| `description` | String | 설명 |
