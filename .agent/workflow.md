# 개발 워크플로우
 
## 실행 및 재시작
- **Backend**: `./run_api.sh` (또는 `./start_api.sh`)
- **Frontend**: `./start_frontend.sh` (기본 Port: 3333)
- **전체 재시작**: `./restart_dev.sh` (API와 프론트엔드를 동시에 재시작)

## 동기화 및 배치 작업
- **오너클랜 상품 수집 트리거**: `/api/suppliers/ownerclan/sync/items` (POST)
- **쿠팡 등록/동기화**: `app/api/endpoints/coupang.py` 및 `app/coupang_sync.py`
- **쿠팡 상태 동기화(PR #20)**: `/api/coupang/sync-status/{product_id}` (POST)
- **백그라운드 작업**: FastAPI `BackgroundTasks`를 사용합니다.
- **AI 오케스트레이션 (PR #31)**: `SourcingAgent.run()` 또는 `ProcessingAgent.run()`을 통해 비동기 그래프 워크플로우 실행.

## 테스트 및 검증
- **Scripts**: `scripts/` 디렉토리에 개별 테스트 및 배치 스크립트 위치
- **Integration Test**: `scripts/test_coupang_bulk_integration.py` 등으로 주요 기능 검증
- **로컬 Python 주의**: `python`이 Windows Python으로 잡힐 수 있어, 필요 시 `.venv/bin/python ...` 사용

## 지속적 통합
- `.github/workflows/ci.yml` 기준
  - **Frontend**: `npm ci` → `npm run lint` → `npm run build`
  - **Backend**: ruff(F821) → `pip check` → `python -m compileall app scripts`

## 배포
- **브랜치**: 모든 변경사항은 `feat/` 또는 `fix/` 브랜치에서 작업 후 `dev` 브랜치로 PR
- **Alembic**: 스키마 변경 시 `alembic revision --autogenerate`로 마이그레이션 생성 필수
