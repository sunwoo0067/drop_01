# 쿠팡 반품 API 문서

> **API 적용 가능한 구매자 사용자 지역**: 한국

---

## 1. 반품/취소 요청 목록 조회

접수 일자를 기준으로 반품/취소 접수 내역을 조회합니다.

### 기본 정보

| 항목 | 내용 |
|------|------|
| **HTTP Method** | `GET` |
| **Endpoint** | `/v2/providers/openapi/apis/api/v6/vendors/{vendorId}/returnRequests` |

### 요청 파라미터 (Path)

| 파라미터명 | 타입 | 필수 | 설명 |
|-----------|------|------|------|
| `vendorId` | String | ✓ | 판매자 ID |

### 요청 파라미터 (Query String)

| 파라미터명 | 타입 | 필수 | 설명 |
|-----------|------|------|------|
| `searchType` | String | - | `timeFrame` 설정 시 분단위 조회 |
| `createdAtFrom` | String | ✓ | 검색 시작일 (yyyy-MM-dd 또는 yyyy-MM-ddTHH:mm) |
| `createdAtTo` | String | ✓ | 검색 종료일 (yyyy-MM-dd 또는 yyyy-MM-ddTHH:mm) |
| `status` | String | - | 반품상태 코드 |
| `cancelType` | String | - | RETURN(반품, default) 또는 CANCEL(취소) |
| `nextToken` | String | - | 다음 페이지 토큰 |
| `maxPerPage` | Number | - | 페이지당 최대 조회 수 (default=50) |
| `orderId` | Number | - | 주문번호 |

### 반품상태 (status) 코드

| 코드 | 설명 |
|------|------|
| `RU` | 출고중지요청 |
| `UC` | 반품접수 |
| `CC` | 반품완료 |
| `PR` | 쿠팡확인요청 |

### 응답 파라미터

| 파라미터명 | 타입 | 설명 |
|-----------|------|------|
| `receiptId` | Number | 취소(반품)접수번호 |
| `orderId` | Number | 주문번호 |
| `receiptType` | String | 취소유형 (RETURN or CANCEL) |
| `receiptStatus` | String | 취소(반품)진행 상태 |
| `createdAt` | String | 취소(반품) 접수시간 |
| `cancelReason` | String | 취소사유 상세내역 |
| `cancelCountSum` | Number | 총 취소수량 |
| `returnDeliveryType` | String | 회수종류 |
| `releaseStopStatus` | String | 출고중지처리상태 |

---

## 2. 반품요청 단건 조회

반품요청 접수번호로 단건 조회합니다.

### 기본 정보

| 항목 | 내용 |
|------|------|
| **HTTP Method** | `GET` |
| **Endpoint** | `/v2/providers/openapi/apis/api/v4/vendors/{vendorId}/returnRequests/{receiptId}` |

### 요청 파라미터 (Path)

| 파라미터명 | 타입 | 필수 | 설명 |
|-----------|------|------|------|
| `vendorId` | String | ✓ | 판매자 ID |
| `receiptId` | Number | ✓ | 반품접수번호 |

---

## 3. 반품상품 입고 확인처리

반품 상품 입고 완료 처리를 합니다.

### 기본 정보

| 항목 | 내용 |
|------|------|
| **HTTP Method** | `PUT` |
| **Endpoint** | `/v2/providers/openapi/apis/api/v4/vendors/{vendorId}/returnRequests/{receiptId}/confirmation` |

### 요청 파라미터 (Path)

| 파라미터명 | 타입 | 필수 | 설명 |
|-----------|------|------|------|
| `vendorId` | String | ✓ | 판매자 ID |
| `receiptId` | Number | ✓ | 반품접수번호 |

---

## 4. 반품요청 승인 처리

입고완료 상태의 반품 건을 승인 처리하여 환불을 진행합니다.

### 기본 정보

| 항목 | 내용 |
|------|------|
| **HTTP Method** | `PATCH` |
| **Endpoint** | `/v2/providers/openapi/apis/api/v4/vendors/{vendorId}/returnRequests/{receiptId}/approval` |

### 요청 파라미터 (Path)

| 파라미터명 | 타입 | 필수 | 설명 |
|-----------|------|------|------|
| `vendorId` | String | ✓ | 업체코드 |
| `receiptId` | Number | ✓ | 반품접수번호 |

### 요청 파라미터 (Body)

| 파라미터명 | 타입 | 필수 | 설명 |
|-----------|------|------|------|
| `vendorId` | String | ✓ | 업체코드 |
| `receiptId` | Number | ✓ | 반품접수번호 |
| `cancelCount` | Number | ✓ | 반품접수 수량 |

### 응답 파라미터

| 파라미터명 | 타입 | 설명 |
|-----------|------|------|
| `code` | Number | 서버 응답 코드 |
| `message` | String | 성공/실패 메시지 |

### 주의사항
- [반품 상품 입고 확인 처리] 후에 호출
- 선환불/빠른환불 또는 시간 경과 시 자동 승인될 수 있음

---

## 5. 회수 송장 등록

반품 회수 송장을 등록합니다.

### 기본 정보

| 항목 | 내용 |
|------|------|
| **HTTP Method** | `PUT` |
| **Endpoint** | `/v2/providers/openapi/apis/api/v4/vendors/{vendorId}/returnRequests/{receiptId}/invoice` |

### 요청 파라미터 (Path)

| 파라미터명 | 타입 | 필수 | 설명 |
|-----------|------|------|------|
| `vendorId` | String | ✓ | 판매자 ID |
| `receiptId` | Number | ✓ | 반품접수번호 |

### 요청 파라미터 (Body)

| 파라미터명 | 타입 | 필수 | 설명 |
|-----------|------|------|------|
| `deliveryCompanyCode` | String | ✓ | 택배사 코드 |
| `invoiceNumber` | String | ✓ | 송장번호 |
