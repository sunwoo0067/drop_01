# 쿠팡 CS API 문서

> **API 적용 가능한 구매자 사용자 지역**: 한국

---

## 1. 상품별 고객문의 조회

상품별 고객문의를 조회합니다.

### 기본 정보

| 항목 | 내용 |
|------|------|
| **HTTP Method** | `GET` |
| **Endpoint** | `/v2/providers/openapi/apis/api/v4/vendors/{vendorId}/product-inquiries` |

### 요청 파라미터 (Path)

| 파라미터명 | 타입 | 필수 | 설명 |
|-----------|------|------|------|
| `vendorId` | String | ✓ | 판매자 ID |

### 요청 파라미터 (Query String)

| 파라미터명 | 타입 | 필수 | 설명 |
|-----------|------|------|------|
| `vendorItemId` | Number | - | 옵션ID |
| `answeredType` | String | - | 답변상태 (ANSWERED, UNANSWERED) |
| `createdAtFrom` | String | - | 문의 시작일 (yyyy-MM-dd) |
| `createdAtTo` | String | - | 문의 종료일 (yyyy-MM-dd) |

---

## 2. 상품별 고객문의 답변

상품별 고객문의에 답변합니다.

### 기본 정보

| 항목 | 내용 |
|------|------|
| **HTTP Method** | `POST` |
| **Endpoint** | `/v2/providers/openapi/apis/api/v4/vendors/{vendorId}/product-inquiries/{inquiryId}/reply` |

### 요청 파라미터 (Path)

| 파라미터명 | 타입 | 필수 | 설명 |
|-----------|------|------|------|
| `vendorId` | String | ✓ | 판매자 ID |
| `inquiryId` | Number | ✓ | 문의 ID |

### 요청 파라미터 (Body)

| 파라미터명 | 타입 | 필수 | 설명 |
|-----------|------|------|------|
| `content` | String | ✓ | 답변 내용 |

---

## 3. 쿠팡 고객센터 문의조회

쿠팡 고객센터를 통해 접수된 문의를 조회합니다.

### 기본 정보

| 항목 | 내용 |
|------|------|
| **HTTP Method** | `GET` |
| **Endpoint** | `/v2/providers/openapi/apis/api/v4/vendors/{vendorId}/cs-inquiries` |

### 요청 파라미터 (Query String)

| 파라미터명 | 타입 | 필수 | 설명 |
|-----------|------|------|------|
| `answeredType` | String | - | 답변상태 |
| `createdAtFrom` | String | - | 문의 시작일 |
| `createdAtTo` | String | - | 문의 종료일 |
| `nextToken` | String | - | 다음 페이지 토큰 |

---

## 4. 쿠팡 고객센터 문의 단건 조회

쿠팡 고객센터 문의를 단건 조회합니다.

### 기본 정보

| 항목 | 내용 |
|------|------|
| **HTTP Method** | `GET` |
| **Endpoint** | `/v2/providers/openapi/apis/api/v4/vendors/{vendorId}/cs-inquiries/{inquiryId}` |

---

## 5. 쿠팡 고객센터 문의답변

쿠팡 고객센터 문의에 답변합니다.

### 기본 정보

| 항목 | 내용 |
|------|------|
| **HTTP Method** | `POST` |
| **Endpoint** | `/v2/providers/openapi/apis/api/v4/vendors/{vendorId}/cs-inquiries/{inquiryId}/reply` |

### 요청 파라미터 (Body)

| 파라미터명 | 타입 | 필수 | 설명 |
|-----------|------|------|------|
| `content` | String | ✓ | 답변 내용 |

---

## 6. 쿠팡 고객센터 문의확인

쿠팡 고객센터 문의를 확인 처리합니다.

### 기본 정보

| 항목 | 내용 |
|------|------|
| **HTTP Method** | `PUT` |
| **Endpoint** | `/v2/providers/openapi/apis/api/v4/vendors/{vendorId}/cs-inquiries/{inquiryId}/confirmation` |
