# 프론트엔드 (Next.js)

`frontend/`의 UI/UX와 백엔드 API 연동을 담당합니다.

## UI/UX & 스택
- **Framework**: Next.js (App Router)
- **Styling**: Tailwind CSS
- **Icons**: `lucide-react`
- **HTTP Client**: Axios 기반 `frontend/src/lib/api`
- **상태 관리**: 기본은 React Hooks(`useState`, `useEffect`)

## 구조
- `frontend/src/app/`: 페이지 라우팅(App Router)
- `frontend/src/components/`: UI 컴포넌트(`Button`, `Card`, `Badge` 등)
- `frontend/src/lib/`: API 클라이언트/유틸
- `frontend/src/types/`: 백엔드 응답과 맞춘 타입 정의

## 백엔드 연동 규칙
- **응답 필드 이름은 백엔드 스키마를 우선**으로 맞춥니다.
- Next.js 환경에서 `/api/products` → `/api/products/` 307 리다이렉트가 CORS/Network Error로 이어질 수 있어, 백엔드가 alias를 제공하는지 확인합니다.

## PR #20 관련 화면/타입
- 등록 페이지: `frontend/src/app/registration/page.tsx`
  - `market_listings`에서 쿠팡 리스팅을 찾아 `coupang_status`가 `DENIED`이면 반려 사유를 노출합니다.
  - `POST /api/coupang/sync-status/{productId}` 호출로 상태를 수동 갱신할 수 있습니다.
- 타입: `frontend/src/types/index.ts`
  - `Product.market_listings?: MarketListing[]`
  - `MarketListing.coupang_status?: string | null`
  - `MarketListing.rejection_reason?: object | null`

## 프론트 린트/빌드 주의
- CI에서 `npm run lint` + `npm run build`가 실행됩니다.
- 사용하지 않는 import(특히 아이콘 import)는 eslint 실패의 원인이 되므로 주기적으로 정리합니다.
