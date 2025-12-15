# 쿠팡 Open API 문서

> **쿠팡 판매자용 Open API 공식 문서**  
> 출처: https://developers.coupangcorp.com/hc/ko

---

## 📋 API 카테고리 목록

| 카테고리 | 파일명 | API 개수 | 설명 |
|----------|--------|----------|------|
| [카테고리 API](category_api.md) | `category_api.md` | 6개 | 카테고리 조회, 추천, 메타정보 |
| [물류센터 API](logistics_api.md) | `logistics_api.md` | 8개 | 출고지/반품지 관리, 택배사 코드 |
| [상품 API](product_api.md) | `product_api.md` | 17개 | 상품 CRUD, 가격/재고 변경 |
| [배송/환불 API](delivery_api.md) | `delivery_api.md` | 12개 | 발주서 조회, 송장 업로드, 취소 처리 |
| [반품 API](return_api.md) | `return_api.md` | 7개 | 반품요청 조회/처리, 입고확인 |
| [교환 API](exchange_api.md) | `exchange_api.md` | 4개 | 교환요청 조회/처리 |
| [쿠폰/캐시백 API](coupon_api.md) | `coupon_api.md` | 16개 | 즉시할인쿠폰, 다운로드쿠폰 |
| [CS API](cs_api.md) | `cs_api.md` | 6개 | 고객문의 조회/답변 |
| [정산 API](settlement_api.md) | `settlement_api.md` | 2개 | 매출/지급 내역 조회 |
| [로켓그로스 API](rocketgrowth_api.md) | `rocketgrowth_api.md` | 9개 | 로켓그로스 전용 상품/주문/재고 |

---

## 🔑 공통 정보

### Base URL
```
https://api-gateway.coupang.com
```

### 인증 방식
HMAC-SHA256 기반 인증

### 공통 응답 형식
```json
{
  "code": "SUCCESS",
  "message": "",
  "data": { ... }
}
```

### 공통 에러 코드

| HTTP 상태 | 코드 | 설명 |
|----------|------|------|
| 200 | SUCCESS | 성공 |
| 400 | 요청변수확인 | 잘못된 요청 파라미터 |
| 401 | 인증오류 | 인증 실패 |
| 403 | 권한없음 | 접근 권한 없음 |
| 500 | 서버오류 | 서버 내부 오류 |

---

## 📌 주요 ID 설명

| ID명 | 설명 |
|------|------|
| `vendorId` | 판매자 ID (업체코드, 예: A00012345) |
| `sellerProductId` | 등록상품 ID |
| `vendorItemId` | 옵션 ID (상품 옵션별 고유 ID) |
| `orderId` | 주문번호 |
| `shipmentBoxId` | 배송번호 (묶음배송번호) |
| `receiptId` | 반품/교환 접수번호 |
| `displayCategoryCode` | 노출 카테고리 코드 |

---

## 📅 문서 생성일
2025-12-15

## 📖 참고 링크
- [쿠팡 Open API 개발자 센터](https://developers.coupangcorp.com/hc/ko)
