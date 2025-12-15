# 쿠팡 로켓그로스 API 문서

> **API 적용 가능한 구매자 사용자 지역**: 한국

---

## API 목록

로켓그로스 API는 총 9개의 API로 구성되어 있습니다.

### 주문 관련 API

| API명 | 설명 |
|-------|------|
| 로켓그로스 주문 API(목록 쿼리) | 로켓그로스 주문 목록 조회 |
| 로켓그로스 주문 API | 로켓그로스 주문 상세 조회 |

### 재고 관련 API

| API명 | 설명 |
|-------|------|
| 로켓창고 재고 API | 로켓창고 재고 조회 |

### 상품 관련 API

| API명 | 설명 |
|-------|------|
| 상품 목록 페이징 조회 | 로켓그로스 및 마켓플레이스/로켓그로스 동시 운영 상품 목록 조회 |
| 상품 생성 | 로켓그로스 및 마켓플레이스/로켓그로스 동시 운영 상품 생성 |
| 상품 수정 | 로켓그로스 또는 마켓플레이스/로켓그로스 동시 운영 상품 수정 |
| 상품 조회 | 로켓그로스 또는 마켓플레이스/로켓그로스 동시 운영 상품 조회 |

### 카테고리 관련 API

| API명 | 설명 |
|-------|------|
| 카테고리 메타 정보 조회 | 로켓그로스 카테고리 메타 정보 조회 |
| 카테고리 목록 조회 | 로켓그로스 운영 카테고리 목록 조회 |

---

## 주요 API 상세

### 로켓그로스 주문 API (목록 쿼리)

| 항목 | 내용 |
|------|------|
| **HTTP Method** | `GET` |
| **Endpoint** | `/v2/providers/rocket_growth_api/apis/api/v1/orders` |

#### 요청 파라미터 (Query String)

| 파라미터명 | 타입 | 필수 | 설명 |
|-----------|------|------|------|
| `vendorId` | String | ✓ | 판매자 ID |
| `createdAtFrom` | String | ✓ | 주문 시작일 |
| `createdAtTo` | String | ✓ | 주문 종료일 |
| `status` | String | - | 주문상태 |

---

### 로켓창고 재고 API

| 항목 | 내용 |
|------|------|
| **HTTP Method** | `GET` |
| **Endpoint** | `/v2/providers/rocket_growth_api/apis/api/v1/inventory` |

#### 요청 파라미터 (Query String)

| 파라미터명 | 타입 | 필수 | 설명 |
|-----------|------|------|------|
| `vendorId` | String | ✓ | 판매자 ID |
| `vendorItemId` | Number | - | 옵션ID |

---

### 상품 목록 페이징 조회

| 항목 | 내용 |
|------|------|
| **HTTP Method** | `GET` |
| **Endpoint** | `/v2/providers/rocket_growth_api/apis/api/v1/products` |

#### 요청 파라미터 (Query String)

| 파라미터명 | 타입 | 필수 | 설명 |
|-----------|------|------|------|
| `vendorId` | String | ✓ | 판매자 ID |
| `nextToken` | String | - | 다음 페이지 토큰 |
| `maxPerPage` | Number | - | 페이지당 최대 조회 수 |

---

### 상품 생성 (로켓그로스)

| 항목 | 내용 |
|------|------|
| **HTTP Method** | `POST` |
| **Endpoint** | `/v2/providers/rocket_growth_api/apis/api/v1/products` |

> **주의**: 로켓그로스 상품 생성은 일반 마켓플레이스 상품 생성과 유사하나, 로켓그로스 전용 필드가 추가됩니다.

---

### 상품 수정 (로켓그로스)

| 항목 | 내용 |
|------|------|
| **HTTP Method** | `PUT` |
| **Endpoint** | `/v2/providers/rocket_growth_api/apis/api/v1/products/{sellerProductId}` |

---

### 상품 조회 (로켓그로스)

| 항목 | 내용 |
|------|------|
| **HTTP Method** | `GET` |
| **Endpoint** | `/v2/providers/rocket_growth_api/apis/api/v1/products/{sellerProductId}` |

---

### 카테고리 메타 정보 조회 (로켓그로스)

| 항목 | 내용 |
|------|------|
| **HTTP Method** | `GET` |
| **Endpoint** | `/v2/providers/rocket_growth_api/apis/api/v1/categories/{displayCategoryCode}/meta` |

---

### 카테고리 목록 조회 (로켓그로스)

| 항목 | 내용 |
|------|------|
| **HTTP Method** | `GET` |
| **Endpoint** | `/v2/providers/rocket_growth_api/apis/api/v1/categories` |
