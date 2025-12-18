# 백엔드 (FastAPI)

`app/` 내 비즈니스 로직과 API 연동을 담당합니다.

## 아키텍처 및 스택
- **Framework**: FastAPI
- **ORM**: SQLAlchemy 2
- **DB 구조**: PostgreSQL 3중 분리
  - **Source**: 공급사 Raw 수집
  - **Dropship**: Product/가공/비즈니스 도메인
  - **Market**: 마켓 동기화/리스팅/주문 Raw

## 멀티 DB 세션 바인딩 규칙
- `app/db.py`의 `get_session`은 모델 Base(`SourceBase`, `DropshipBase`, `MarketBase`)에 따라 **자동으로 엔진이 바인딩**됩니다.
- **중요**: 서로 다른 DB의 테이블을 ORM `relationship`로 바로 엮지 않습니다.
  - 예: Product(Dropship) ↔ MarketListing(Market)은 **별도 조회 후 응답에서 합치기** 방식으로 처리합니다.
- PR #20 보강: `GET /api/products/` 및 `GET /api/products/{id}`에서 `market_listings`를 별도 조회 후 `ProductResponse`로 합쳐 내려줍니다.

## 외부 API 연동 규칙
- **클라이언트**: `CoupangClient`, `OwnerClanClient` 사용 시 예외 처리를 필수 적용합니다.
- **에러 처리/로그**: 실패 시 HTTP 상태 코드와 메시지를 포함해 한국어로 남깁니다.

## PR #20 관련 핵심 기능
- **MarketListing 필드 추가**: `coupang_status`, `rejection_reason(JSONB)`
- **상태 동기화 엔드포인트**: `POST /api/coupang/sync-status/{product_id}`
- **상품 목록 응답 보강**: `ProductResponse.market_listings` 포함

## 로컬/CI 검증 팁
- 이 환경에서는 `python`이 Windows Python으로 연결될 수 있어, 로컬 검증은 가능하면 `.venv/bin/python ...` 사용을 권장합니다.
- CI는 아래를 수행합니다.
  - **Backend**: ruff(F821) + `python -m compileall app scripts`
  - **Frontend**: `npm run lint` + `npm run build`

## 307 Redirect(Next.js) 주의
- Next.js 경로 정규화로 `/api/products` → `/api/products/` 리다이렉트가 발생하면 CORS/Network Error가 날 수 있습니다.
- 따라서 `app/main.py`에 **슬래시 없는 alias 라우트**를 유지합니다.
