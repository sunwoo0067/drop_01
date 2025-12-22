# 드랍쉬핑 연동 (쿠팡 & 오너클랜)

이 파일은 프로젝트의 통합 규칙과 기술적 개요를 담고 있습니다. 상세 기술 문서는 `.agent/` 디렉토리의 개별 파일을 참조하세요.

---

## 기술 스택

### Backend
- **Framework**: FastAPI
- **Database**: PostgreSQL (Source, Dropship, Market 3중 DB 구조)
- **ORM**: SQLAlchemy (with Alembic migrations)
- **Search/AI**: pgvector (embeddings), LangGraph (orchestration)
- **Embedding**: Ollama (nomic-embed-text), OpenAI
- **Storage**: Supabase Storage

### Frontend
- **Framework**: Next.js 15+ (App Router)
- **UI**: React 19, Tailwind CSS 4
- **Icons**: Lucide React
- **HTTP Client**: Axios

---

## 핵심 규칙

### 1. 언어 및 코딩 스타일
- **기본 언어**: 한국어 (문서, 주석, 커밋 메시지, 커뮤니케이션)
- **변수명**: 영어 (CamelCase/snake_case 프로젝트 관례 준수)
- **커밋 메시지**: [태그]: [Jira issue ID] [작업 내용 요약] (한국어)
    - 예: `feat: KAN-1 상품 상세 페이지 UI 구현`
- **에러 처리**: Try-Catch 필수, 로그는 HTTP 상태 코드와 메시지를 포함하여 한국어로 작성

### 2. 브랜치 전략 (Gitflow-Lite)
- `main`: 배포 (안정)
- `dev`: 개발 통합
- `feat/`, `fix/`, `hotfix/`: 기능 및 버그 수정 브랜치

---

- `feat/langgraph-orchestration` 브랜치에서 **LangGraph** 기반의 AI 오케스트레이션이 도입되었습니다. (PR #31)
  - `SourcingAgent`, `ProcessingAgent`를 통한 워크플로우 자동화
  - `EmbeddingService` 배치 생성 기능 및 `pgvector` 연동 강화
- `dev` 브랜치에 PR #20이 병합되었습니다.
  - 쿠팡 상품 `DENIED` 반려 사유 조회/저장(`MarketListing.coupang_status`, `MarketListing.rejection_reason`)
  - 상태 동기화 엔드포인트 추가: `POST /api/coupang/sync-status/{product_id}`
  - 상품 목록/상세 응답에 `market_listings` 포함(멀티 DB 구조로 인해 별도 조회 후 합치기)
- 로컬 환경에서 `python`이 Windows Python으로 잡힐 수 있어, 필요 시 `.venv/bin/python ...` 사용을 권장합니다.

---

## 문서 가이드
- **Backend 상세**: [.agent/backend.md](file:///home/sunwoo/project/drop/drop_01/drop_01_dev/.agent/backend.md)
- **Frontend 상세**: [.agent/frontend.md](file:///home/sunwoo/project/drop/drop_01/drop_01_dev/.agent/frontend.md)
- **Workflow 상세**: [.agent/workflow.md](file:///home/sunwoo/project/drop/drop_01/drop_01_dev/.agent/workflow.md)
