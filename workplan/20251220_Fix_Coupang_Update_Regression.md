# 20251220 쿠팡 업데이트 로직 회귀 버그 수정 계획

## 개요
이슈 #35의 후속 조치로, 쿠팡 상품 업데이트 시 로컬 가공 데이터가 누락되는 현상과 가격 불일치 문제를 해결합니다.

## 상세 이슈
1. **로컬 데이터 미반영**: `update_product_on_coupang`이 로컬의 `description`, `images`를 무시함.
2. **가격 불일치**: `salePrice` 상향 시 `originalPrice`보다 커져서 오류 발생 가능.

## 해결 방안
- `update_product_on_coupang` 함수 내부에서 로컬 `Product` 객체의 데이터를 페이로드에 적극적으로 주입.
- `originalPrice`를 `salePrice`와 동기화.

## 관련 문서
- [implementation_plan.md](file:///home/sunwoo/.gemini/antigravity/brain/7914351f-305f-4369-8319-6efa78580a9f/implementation_plan.md)
