# Development Workflows

## 🚀 Execution & Restart
- **Backend**: `./run_api.sh` 또는 `python -m app.main`
- **Frontend**: `cd frontend && npm run dev` (Port: 3333)
- **전체 재시작**: `./restart_dev.sh` (API와 프론트엔드를 동시에 재시작)

## 🔄 Sync & Batch Jobs
- **오너클랜 상품 수집**: `/api/sync/ownerclan/items` (POST) 호출
- **쿠팡 상품 연동**: `app/coupang_sync.py` 및 관련 API를 통해 비동기로 처리
- **백그라운드 작업**: FastAPI `BackgroundTasks`를 통해 처리되며, `api.log`에서 상태 확인 가능

## 🧪 Testing & Verification
- **Scripts**: `scripts/` 디렉토리에 개별 테스트 및 배치 스크립트 위치
- **Integration Test**: `scripts/test_coupang_bulk_integration.py` 등으로 주요 기능 검증
- **Logging**: 모든 테스트 실행 시 `structlog` 표준을 준수하여 결과 확인

## 🚢 Deployment
- **Branch**: 모든 변경사항은 `feat/` 또는 `fix/` 브랜치에서 작업 후 `dev` 브랜치로 PR
- **Alembic**: 스키마 변경 시 `alembic revision --autogenerate`로 마이그레이션 생성 필수
