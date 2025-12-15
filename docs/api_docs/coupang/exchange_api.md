# 쿠팡 교환 API 문서

> **API 적용 가능한 구매자 사용자 지역**: 한국

---

## 1. 교환요청 목록조회

교환요청 목록을 조회합니다.

### 기본 정보

| 항목 | 내용 |
|------|------|
| **HTTP Method** | `GET` |
| **Endpoint** | `/v2/providers/openapi/apis/api/v4/vendors/{vendorId}/exchangeRequests` |

### 요청 파라미터 (Path)

| 파라미터명 | 타입 | 필수 | 설명 |
|-----------|------|------|------|
| `vendorId` | String | ✓ | 판매자 ID |

### 요청 파라미터 (Query String)

| 파라미터명 | 타입 | 필수 | 설명 |
|-----------|------|------|------|
| `createdAtFrom` | String | ✓ | 검색 시작일 (yyyy-MM-dd) |
| `createdAtTo` | String | ✓ | 검색 종료일 (yyyy-MM-dd) |
| `status` | String | - | 교환상태 필터 |
| `nextToken` | String | - | 다음 페이지 토큰 |
| `maxPerPage` | Number | - | 페이지당 최대 조회 수 |

---

## 2. 교환요청상품 입고 확인처리

교환 상품 입고 완료 처리를 합니다.

### 기본 정보

| 항목 | 내용 |
|------|------|
| **HTTP Method** | `PUT` |
| **Endpoint** | `/v2/providers/openapi/apis/api/v4/vendors/{vendorId}/exchangeRequests/{receiptId}/confirmation` |

### 요청 파라미터 (Path)

| 파라미터명 | 타입 | 필수 | 설명 |
|-----------|------|------|------|
| `vendorId` | String | ✓ | 판매자 ID |
| `receiptId` | Number | ✓ | 교환접수번호 |

---

## 3. 교환요청 거부 처리

교환요청을 거부 처리합니다.

### 기본 정보

| 항목 | 내용 |
|------|------|
| **HTTP Method** | `PUT` |
| **Endpoint** | `/v2/providers/openapi/apis/api/v4/vendors/{vendorId}/exchangeRequests/{receiptId}/rejection` |

### 요청 파라미터 (Path)

| 파라미터명 | 타입 | 필수 | 설명 |
|-----------|------|------|------|
| `vendorId` | String | ✓ | 판매자 ID |
| `receiptId` | Number | ✓ | 교환접수번호 |

### 요청 파라미터 (Body)

| 파라미터명 | 타입 | 필수 | 설명 |
|-----------|------|------|------|
| `rejectReason` | String | ✓ | 거부 사유 |

---

## 4. 교환상품 송장 업로드 처리

교환 상품의 송장을 업로드합니다.

### 기본 정보

| 항목 | 내용 |
|------|------|
| **HTTP Method** | `PUT` |
| **Endpoint** | `/v2/providers/openapi/apis/api/v4/vendors/{vendorId}/exchangeRequests/{receiptId}/invoice` |

### 요청 파라미터 (Path)

| 파라미터명 | 타입 | 필수 | 설명 |
|-----------|------|------|------|
| `vendorId` | String | ✓ | 판매자 ID |
| `receiptId` | Number | ✓ | 교환접수번호 |

### 요청 파라미터 (Body)

| 파라미터명 | 타입 | 필수 | 설명 |
|-----------|------|------|------|
| `deliveryCompanyCode` | String | ✓ | 택배사 코드 |
| `invoiceNumber` | String | ✓ | 송장번호 |
