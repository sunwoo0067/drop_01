# 쿠팡 쿠폰/캐시백 API 문서

> **API 적용 가능한 구매자 사용자 지역**: 한국

---

## API 목록

쿠폰/캐시백 API는 총 16개의 API로 구성되어 있습니다.

### 공통 API

| API명 | 설명 |
|-------|------|
| 예산현황 조회 | 쿠폰 예산 현황 조회 |
| 계약서 단건 조회 | 쿠폰 계약서 단건 조회 |
| 계약서 목록 조회 | 쿠폰 계약서 목록 조회 |

### 즉시할인쿠폰 API

| API명 | 설명 |
|-------|------|
| 생성 | 즉시할인쿠폰 생성 |
| 파기 | 즉시할인쿠폰 파기 |
| 요청상태 확인 | 즉시할인쿠폰 요청상태 확인 |
| 아이템 생성 | 즉시할인쿠폰 아이템 생성 |
| 단건 조회(couponId) | couponId로 즉시할인쿠폰 단건 조회 |
| 단건 조회(couponItemId) | couponItemId로 즉시할인쿠폰 단건 조회 |
| 단건 조회(vendorItemId) | vendorItemId로 즉시할인쿠폰 단건 조회 |
| 목록 조회(status) | 상태별 즉시할인쿠폰 목록 조회 |
| 목록 조회(orderId) | 주문번호별 즉시할인쿠폰 목록 조회 |
| 아이템 목록 조회(status) | 상태별 즉시할인쿠폰 아이템 목록 조회 |

### 다운로드쿠폰 API

| API명 | 설명 |
|-------|------|
| 생성 | 다운로드쿠폰 생성 |
| 파기 | 다운로드쿠폰 파기 |
| 아이템 생성 | 다운로드쿠폰 아이템 생성 |

---

## 기본 정보

### Base Endpoint
`/v2/providers/openapi/apis/api/v1/vendors/{vendorId}/coupons`

### 공통 요청 파라미터 (Path)

| 파라미터명 | 타입 | 필수 | 설명 |
|-----------|------|------|------|
| `vendorId` | String | ✓ | 판매자 ID |

---

## 주요 API 상세

### 예산현황 조회

| 항목 | 내용 |
|------|------|
| **HTTP Method** | `GET` |
| **Endpoint** | `/v2/providers/openapi/apis/api/v1/vendors/{vendorId}/coupons/budgets` |

### 즉시할인쿠폰 생성

| 항목 | 내용 |
|------|------|
| **HTTP Method** | `POST` |
| **Endpoint** | `/v2/providers/openapi/apis/api/v1/vendors/{vendorId}/coupons/instant-discounts` |

### 즉시할인쿠폰 파기

| 항목 | 내용 |
|------|------|
| **HTTP Method** | `DELETE` |
| **Endpoint** | `/v2/providers/openapi/apis/api/v1/vendors/{vendorId}/coupons/instant-discounts/{couponId}` |

### 다운로드쿠폰 생성

| 항목 | 내용 |
|------|------|
| **HTTP Method** | `POST` |
| **Endpoint** | `/v2/providers/openapi/apis/api/v1/vendors/{vendorId}/coupons/downloadable` |
