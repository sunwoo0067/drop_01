# Frontend Documentation

## 🎨 UI/UX & Stack
- **Framework**: Next.js 15+ (App Router)
- **Styling**: Tailwind CSS 4
- **Typography**: Inter (English), Noto Sans KR (Korean)
- **Icons**: `lucide-react`
- **State Management**: React Hooks (useState, useEffect) & API integration

## 🏗️ Structure
- `frontend/src/app/`: App Router 기반 페이지 구성
- `frontend/src/components/`: 재사용 가능한 UI 컴포넌트 (Button, Card, Badge 등)
- `frontend/src/lib/`: 공통 유틸리티 및 API 클라이언트 (`api.ts`)

## 💅 Design Principles
- **Aesthetics**: 다크 모드 지원, 부드러운 그라데이션, 마이크로 애니메이션을 통한 프리미엄 느낌 강조
- **Consistency**: 정의된 CSS 변수와 `Card`, `Button` 컴포넌트를 일관되게 사용
- **Responsiveness**: 모든 페이지는 모바일/데스크탑 반응형 대응 필수
- **Type Safety**: `any` 타입 사용을 지양하고 인터페이스를 명확히 정의
