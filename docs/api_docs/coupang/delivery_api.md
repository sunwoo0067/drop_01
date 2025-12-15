# 쿠팡 배송/환불 API 문서

> **API 적용 가능한 구매자 사용자 지역**: 한국

---

## 1. 발주서 목록 조회 (일단위 페이징)

등록상품 발주서 목록을 일단위로 페이징 조회합니다.

### 기본 정보

| 항목 | 내용 |
|------|------|
| **HTTP Method** | `GET` |
| **Endpoint** | `/v2/providers/openapi/apis/api/v4/vendors/{vendorId}/ordersheets` |

### 요청 파라미터 (Path)

| 파라미터명 | 타입 | 필수 | 설명 |
|-----------|------|------|------|
| `vendorId` | String | ✓ | 판매자 ID |

### 요청 파라미터 (Query String)

| 파라미터명 | 타입 | 필수 | 설명 |
|-----------|------|------|------|
| `createdAtFrom` | String | ✓ | 주문일 시작 (yyyy-MM-dd) |
| `createdAtTo` | String | ✓ | 주문일 종료 (yyyy-MM-dd) |
| `status` | String | - | 주문상태 필터 |
| `maxPerPage` | Number | - | 페이지당 건수 (기본 50, 최대 100) |
| `nextToken` | String | - | 다음 페이지 토큰 |

---

## 2. 상품준비중 처리

주문상태를 "결제완료"에서 "상품준비중"으로 변경합니다.

### 기본 정보

| 항목 | 내용 |
|------|------|
| **HTTP Method** | `PATCH` |
| **Endpoint** | `/v2/providers/openapi/apis/api/v4/vendors/{vendorId}/ordersheets/acknowledgement` |

### 요청 파라미터 (Path)

| 파라미터명 | 타입 | 필수 | 설명 |
|-----------|------|------|------|
| `vendorId` | String | ✓ | 판매자 ID |

### 요청 파라미터 (Body)

| 파라미터명 | 타입 | 필수 | 설명 |
|-----------|------|------|------|
| `vendorId` | String | ✓ | 판매자 ID |
| `shipmentBoxIds` | Array | ✓ | 상품준비중 상태로 변경할 묶음배송번호 배열 (최대 50개) |

### 응답 파라미터

| 파라미터명 | 타입 | 설명 |
|-----------|------|------|
| `code` | Number | 서버 응답 코드 |
| `message` | String | 서버 응답 메시지 |
| `data.responseCode` | Number | 결과 상태 (-1: 결과없음, 0: 성공, 1: 부분실패, 99: 실패) |
| `data.responseList` | Array | 개별 건 결과 |
| `data.responseList.shipmentBoxId` | Number | 묶음배송번호 |
| `data.responseList.succeed` | Boolean | 성공여부 |
| `data.responseList.retryRequired` | Boolean | 재시도 필요 여부 |

### 주의사항
- 상품준비중 처리 후 발주서 단건 조회를 통해 배송지 변경 여부 확인 필수

---

## 3. 송장업로드 처리

송장을 업로드하여 주문을 배송지시 상태로 변경합니다.

### 기본 정보

| 항목 | 내용 |
|------|------|
| **HTTP Method** | `POST` |
| **Endpoint** | `/v2/providers/openapi/apis/api/v4/vendors/{vendorId}/orders/invoices` |

### 요청 파라미터 (Path)

| 파라미터명 | 타입 | 필수 | 설명 |
|-----------|------|------|------|
| `vendorId` | String | ✓ | 판매자 ID |

### 요청 파라미터 (Body)

| 파라미터명 | 타입 | 필수 | 설명 |
|-----------|------|------|------|
| `vendorId` | String | ✓ | 판매자 ID |
| `orderSheetInvoiceApplyDtos` | Array | ✓ | 배송지시 변경 대상 목록 |
| `orderSheetInvoiceApplyDtos.shipmentBoxId` | Number | ✓ | 배송번호 |
| `orderSheetInvoiceApplyDtos.orderId` | Number | ✓ | 주문번호 |
| `orderSheetInvoiceApplyDtos.deliveryCompanyCode` | String | ✓ | 택배사 코드 |
| `orderSheetInvoiceApplyDtos.invoiceNumber` | String | ✓ | 송장번호 |
| `orderSheetInvoiceApplyDtos.vendorItemId` | Number | ✓ | 옵션ID |
| `orderSheetInvoiceApplyDtos.splitShipping` | Boolean | ✓ | 분리배송 여부 (false: 전체, true: 분리) |
| `orderSheetInvoiceApplyDtos.preSplitShipped` | Boolean | ✓ | 기 분리배송 진행 여부 |
| `orderSheetInvoiceApplyDtos.estimatedShippingDate` | String | ✓ | 출고예정일 (YYYY-MM-DD 또는 "") |

### 응답 파라미터

| 파라미터명 | 타입 | 설명 |
|-----------|------|------|
| `data.responseCode` | Number | 결과 상태 (0: 성공, 1: 부분실패, 99: 실패) |
| `data.responseList` | Array | 개별 건 결과 |
| `data.responseList.shipmentBoxId` | Number | 배송번호 |
| `data.responseList.succeed` | Boolean | 성공여부 |
| `data.responseList.code` | String | 결과코드 |
| `data.responseList.retryRequired` | Boolean | 재시도 필요 여부 |

### 주의사항
- 상품준비중 상태의 주문에 대해서만 가능
- 분리배송 지원
- 6개월 이내 중복 송장번호 입력 시 에러 발생 가능

---

## 4. 주문 상품 취소 처리

[결제완료] 또는 [상품준비중] 상태의 상품을 취소합니다.

### 기본 정보

| 항목 | 내용 |
|------|------|
| **HTTP Method** | `POST` |
| **Endpoint** | `/v2/providers/openapi/apis/api/v5/vendors/{vendorId}/orders/{orderId}/cancel` |

### 요청 파라미터 (Path)

| 파라미터명 | 타입 | 필수 | 설명 |
|-----------|------|------|------|
| `vendorId` | String | ✓ | 판매자 ID |
| `orderId` | Number | ✓ | 주문번호 |

### 요청 파라미터 (Body)

| 파라미터명 | 타입 | 필수 | 설명 |
|-----------|------|------|------|
| `orderId` | Number | ✓ | 주문번호 |
| `vendorItemIds` | Array | ✓ | 취소할 vendorItemId 배열 |
| `receiptCounts` | Array | ✓ | 취소 수량 배열 (vendorItemIds와 대응) |
| `bigCancelCode` | String | ✓ | 대분류 취소 사유 코드 |
| `middleCancelCode` | String | ✓ | 중분류 취소 사유 코드 |
| `vendorId` | String | ✓ | 업체 ID |
| `userId` | String | ✓ | Wing 로그인 ID |

### 취소 사유 코드

| 대분류 (bigCancelCode) | 중분류 (middleCancelCode) | 설명 |
|-----------------------|--------------------------|------|
| `CANERR` | `CCTTER` | 주문 실수/고객 변심 |
| `CANERR` | `CCPNER` | 상품 품절 |
| `CANERR` | `CCPRER` | 가격 오류 |

### 응답 파라미터

| 파라미터명 | 타입 | 설명 |
|-----------|------|------|
| `code` | String | 응답 코드 (200: 성공, 400: 실패) |
| `data.receiptMap` | Object | 접수ID별 상세 |
| `data.receiptMap.receiptType` | String | CANCEL(즉시취소) or STOP_SHIPMENT(출고중지) |
| `data.failedItemIds` | Array | 실패한 vendorItemId 목록 |

### 주의사항
- [결제완료]는 즉시 취소
- [상품준비중]은 출고 중지 처리
- `shipmentBoxId` 별로 각각 취소 요청 필요
- 판매자 점수에 영향
