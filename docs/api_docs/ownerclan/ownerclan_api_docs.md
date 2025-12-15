# 오너클랜 API 문서 (프로덕션)

> 이 문서는 오너클랜 API 센터의 프로덕션 환경 API를 정리한 문서입니다.
> 
> **Base URL**: `https://api.ownerclan.com`
> **인증 URL**: `https://auth.ownerclan.com`

---

## 목차

1. [인증 API](#1-인증-api)
2. [주문 API](#2-주문-api)
3. [상품 API](#3-상품-api)
4. [문의 API](#4-문의-api)
5. [카테고리 API](#5-카테고리-api)
6. [데이터 타입](#6-데이터-타입)

---

## 1. 인증 API

### 1.1 토큰 발급

API 호출을 위한 인증 토큰을 발급받습니다.

| 항목 | 값 |
|------|-----|
| **Endpoint** | `POST https://auth.ownerclan.com/auth` |
| **Content-Type** | `application/json` |

#### 요청 Body

```json
{
  "service": "ownerclan",
  "userType": "seller",
  "username": "판매사ID",
  "password": "판매사PW"
}
```

#### 요청 파라미터

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `service` | String | Y | 서비스명 (고정값: `ownerclan`) |
| `userType` | String | Y | 사용자 유형 (`seller` 또는 `supplier`) |
| `username` | String | Y | 판매사 ID |
| `password` | String | Y | 판매사 비밀번호 |

#### 응답 예시

```json
{
  "success": true,
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "expiresIn": 3600
}
```

#### 인증 헤더 사용

발급받은 토큰은 모든 API 요청 시 헤더에 포함해야 합니다:

```
Authorization: Bearer {token}
```

---

## 2. 주문 API

### 2.1 단일 주문 정보 조회 API

특정 주문의 상세 정보를 조회합니다.

| 항목 | 값 |
|------|-----|
| **Endpoint** | `GET /v1/order/{order_id}` |
| **Method** | GET |

#### Path 파라미터

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `order_id` | String | Y | 주문 ID |

#### 응답 필드

| 필드 | 타입 | 설명 |
|------|------|------|
| `order_id` | String | 주문 고유 ID |
| `order_status` | String | 주문 상태 |
| `order_date` | DateTime | 주문 일시 |
| `buyer_name` | String | 구매자명 |
| `buyer_phone` | String | 구매자 연락처 |
| `recipient_name` | String | 수령인명 |
| `recipient_phone` | String | 수령인 연락처 |
| `recipient_address` | String | 배송 주소 |
| `items` | Array | 주문 상품 목록 |
| `total_amount` | Number | 총 주문 금액 |
| `shipping_fee` | Number | 배송비 |

---

### 2.2 복수 주문 내역 조회 API

여러 주문을 조건에 따라 조회합니다.

| 항목 | 값 |
|------|-----|
| **Endpoint** | `GET /v1/orders` |
| **Method** | GET |

#### Query 파라미터

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `start_date` | String | N | 조회 시작일 (YYYY-MM-DD) |
| `end_date` | String | N | 조회 종료일 (YYYY-MM-DD) |
| `status` | String | N | 주문 상태 필터 |
| `page` | Number | N | 페이지 번호 (기본값: 1) |
| `limit` | Number | N | 페이지당 항목 수 (기본값: 20, 최대: 100) |

#### 응답 필드

| 필드 | 타입 | 설명 |
|------|------|------|
| `orders` | Array | 주문 목록 |
| `total_count` | Number | 전체 주문 수 |
| `page` | Number | 현재 페이지 |
| `total_pages` | Number | 전체 페이지 수 |

---

### 2.3 새 주문 등록 API

새로운 주문을 등록합니다.

| 항목 | 값 |
|------|-----|
| **Endpoint** | `POST /v1/order` |
| **Method** | POST |
| **Content-Type** | `application/json` |

#### 요청 Body

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `product_code` | String | Y | 상품 코드 |
| `quantity` | Number | Y | 수량 |
| `buyer_name` | String | Y | 구매자명 |
| `buyer_phone` | String | Y | 구매자 연락처 |
| `recipient_name` | String | Y | 수령인명 |
| `recipient_phone` | String | Y | 수령인 연락처 |
| `recipient_address` | String | Y | 배송 주소 |
| `recipient_zipcode` | String | Y | 우편번호 |
| `delivery_message` | String | N | 배송 메시지 |
| `order_memo` | String | N | 주문 메모 |

#### 응답 필드

| 필드 | 타입 | 설명 |
|------|------|------|
| `success` | Boolean | 성공 여부 |
| `order_id` | String | 생성된 주문 ID |
| `message` | String | 결과 메시지 |

---

### 2.4 테스트 주문 API

테스트 주문을 생성합니다.

| 항목 | 값 |
|------|-----|
| **Endpoint** | `POST /v1/order/test` |
| **Method** | POST |

> 테스트 주문은 실제 처리되지 않으며, API 연동 테스트 목적으로 사용됩니다.

---

### 2.5 주문 메모 업데이트 API

주문에 메모를 추가하거나 수정합니다.

| 항목 | 값 |
|------|-----|
| **Endpoint** | `PUT /v1/order/{order_id}/memo` |
| **Method** | PUT |

#### 요청 Body

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `memo` | String | Y | 메모 내용 |

---

### 2.6 주문 취소 API

주문을 취소합니다.

| 항목 | 값 |
|------|-----|
| **Endpoint** | `DELETE /v1/order/{order_id}` |
| **Method** | DELETE |

#### Path 파라미터

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `order_id` | String | Y | 취소할 주문 ID |

#### 요청 Body

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `cancel_reason` | String | Y | 취소 사유 |

---

## 3. 상품 API

### 3.1 단일 상품 정보 조회 API

특정 상품의 상세 정보를 조회합니다.

| 항목 | 값 |
|------|-----|
| **Endpoint** | `GET /v1/item/{item_code}` |
| **Method** | GET |

#### Path 파라미터

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `item_code` | String | Y | 상품 코드 |

#### 응답 필드

| 필드 | 타입 | 설명 |
|------|------|------|
| `item_code` | String | 상품 코드 |
| `item_name` | String | 상품명 |
| `price` | Number | 판매가 |
| `supply_price` | Number | 공급가 |
| `stock` | Number | 재고 수량 |
| `category` | String | 카테고리 |
| `description` | String | 상품 설명 |
| `images` | Array | 상품 이미지 URL 목록 |
| `options` | Array | 옵션 정보 |
| `status` | String | 상품 상태 |

---

### 3.2 복수 상품 정보 조회 API

여러 상품을 조건에 따라 조회합니다.

| 항목 | 값 |
|------|-----|
| **Endpoint** | `GET /v1/items` |
| **Method** | GET |

#### Query 파라미터

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `category` | String | N | 카테고리 필터 |
| `status` | String | N | 상품 상태 필터 |
| `keyword` | String | N | 검색 키워드 |
| `page` | Number | N | 페이지 번호 |
| `limit` | Number | N | 페이지당 항목 수 |

---

### 3.3 상품 변경 이력 조회 API

상품의 변경 이력을 조회합니다.

| 항목 | 값 |
|------|-----|
| **Endpoint** | `GET /v1/item/{item_code}/history` |
| **Method** | GET |

#### Path 파라미터

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `item_code` | String | Y | 상품 코드 |

#### Query 파라미터

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `start_date` | String | N | 조회 시작일 |
| `end_date` | String | N | 조회 종료일 |

---

### 3.4 여러 상품 정보 조회 API

여러 상품 코드로 상품 정보를 일괄 조회합니다.

| 항목 | 값 |
|------|-----|
| **Endpoint** | `POST /v1/items/bulk` |
| **Method** | POST |

#### 요청 Body

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `item_codes` | Array | Y | 상품 코드 목록 |

---

## 4. 문의 API

### 4.1 문의 목록 조회 API

문의 목록을 조회합니다.

| 항목 | 값 |
|------|-----|
| **Endpoint** | `GET /v1/qna` |
| **Method** | GET |

#### Query 파라미터

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `status` | String | N | 문의 상태 (answered, pending) |
| `start_date` | String | N | 조회 시작일 |
| `end_date` | String | N | 조회 종료일 |
| `page` | Number | N | 페이지 번호 |
| `limit` | Number | N | 페이지당 항목 수 |

#### 응답 필드

| 필드 | 타입 | 설명 |
|------|------|------|
| `qna_list` | Array | 문의 목록 |
| `total_count` | Number | 전체 문의 수 |

---

### 4.2 단일 문의 조회 API

특정 문의의 상세 정보를 조회합니다.

| 항목 | 값 |
|------|-----|
| **Endpoint** | `GET /v1/qna/{qna_id}` |
| **Method** | GET |

#### Path 파라미터

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `qna_id` | String | Y | 문의 ID |

---

### 4.3 문의 답변 등록 API

문의에 답변을 등록합니다.

| 항목 | 값 |
|------|-----|
| **Endpoint** | `POST /v1/qna/{qna_id}/answer` |
| **Method** | POST |

#### Path 파라미터

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `qna_id` | String | Y | 문의 ID |

#### 요청 Body

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `answer` | String | Y | 답변 내용 |

---

### 4.4 문의 답변 수정 API

등록된 답변을 수정합니다.

| 항목 | 값 |
|------|-----|
| **Endpoint** | `PUT /v1/qna/{qna_id}/answer` |
| **Method** | PUT |

#### 요청 Body

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `answer` | String | Y | 수정할 답변 내용 |

---

## 5. 카테고리 API

### 5.1 단일 카테고리 정보 조회 API

특정 카테고리의 정보를 조회합니다.

| 항목 | 값 |
|------|-----|
| **Endpoint** | `GET /v1/category/{category_id}` |
| **Method** | GET |

#### Path 파라미터

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `category_id` | String | Y | 카테고리 ID |

#### 응답 필드

| 필드 | 타입 | 설명 |
|------|------|------|
| `category_id` | String | 카테고리 ID |
| `category_name` | String | 카테고리명 |
| `parent_id` | String | 상위 카테고리 ID |
| `level` | Number | 카테고리 레벨 |
| `children` | Array | 하위 카테고리 목록 |

---

### 5.2 카테고리 목록 조회 API

전체 카테고리 목록을 조회합니다.

| 항목 | 값 |
|------|-----|
| **Endpoint** | `GET /v1/categories` |
| **Method** | GET |

#### Query 파라미터

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `parent_id` | String | N | 상위 카테고리 ID (하위 카테고리만 조회) |
| `level` | Number | N | 카테고리 레벨 |

---

## 6. 데이터 타입

### 6.1 주문 상태 (Order Status)

| 코드 | 설명 |
|------|------|
| `ORDER_RECEIVED` | 주문 접수 |
| `PAYMENT_COMPLETE` | 결제 완료 |
| `PREPARING` | 상품 준비중 |
| `SHIPPING` | 배송중 |
| `DELIVERED` | 배송 완료 |
| `CANCELLED` | 주문 취소 |
| `RETURN_REQUESTED` | 반품 요청 |
| `RETURN_COMPLETE` | 반품 완료 |
| `EXCHANGE_REQUESTED` | 교환 요청 |
| `EXCHANGE_COMPLETE` | 교환 완료 |

---

### 6.2 상품 상태 (Item Status)

| 코드 | 설명 |
|------|------|
| `ACTIVE` | 판매중 |
| `INACTIVE` | 판매 중지 |
| `OUT_OF_STOCK` | 품절 |
| `DELETED` | 삭제됨 |

---

### 6.3 문의 상태 (QnA Status)

| 코드 | 설명 |
|------|------|
| `PENDING` | 답변 대기 |
| `ANSWERED` | 답변 완료 |

---

## 공통 응답 형식

### 성공 응답

```json
{
  "success": true,
  "data": { ... },
  "message": "Success"
}
```

### 에러 응답

```json
{
  "success": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "에러 메시지"
  }
}
```

### 공통 에러 코드

| 에러 코드 | HTTP 상태 | 설명 |
|-----------|-----------|------|
| `UNAUTHORIZED` | 401 | 인증 실패 |
| `FORBIDDEN` | 403 | 권한 없음 |
| `NOT_FOUND` | 404 | 리소스 없음 |
| `INVALID_PARAMETER` | 400 | 잘못된 파라미터 |
| `INTERNAL_ERROR` | 500 | 서버 내부 오류 |

---

## 페이지네이션

목록 조회 API는 공통적으로 페이지네이션을 지원합니다.

### 요청 파라미터

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `page` | Number | 1 | 페이지 번호 |
| `limit` | Number | 20 | 페이지당 항목 수 (최대 100) |

### 응답 필드

| 필드 | 타입 | 설명 |
|------|------|------|
| `total_count` | Number | 전체 항목 수 |
| `page` | Number | 현재 페이지 |
| `total_pages` | Number | 전체 페이지 수 |
| `has_next` | Boolean | 다음 페이지 존재 여부 |
| `has_prev` | Boolean | 이전 페이지 존재 여부 |

---

## 참고 사항

1. **인증 만료**: 토큰은 발급 후 1시간(3600초) 후 만료됩니다. 만료 전에 새 토큰을 발급받아야 합니다.

2. **Rate Limiting**: API 호출은 분당 60회로 제한됩니다. 초과 시 `429 Too Many Requests` 오류가 반환됩니다.

3. **타임존**: 모든 날짜/시간은 KST (Korea Standard Time, UTC+9) 기준입니다.

4. **문자 인코딩**: 모든 API 요청/응답은 UTF-8 인코딩을 사용합니다.

---

> **문서 생성일**: 2025-12-15
> 
> **참조**: [오너클랜 API 센터](https://www.ownerclan.com/V2/service/api-center-info.php)
