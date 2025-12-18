# Backend Documentation

## 🛰️ Architecture & Stack
- **Framework**: FastAPI (Asynchronous)
- **Database Architecture**:
  - `Source`: Raw data collection
  - `Dropship`: Core business logic and processed data
  - `Market`: Market-specific synchronized data
- **ORM**: SQLAlchemy 2.0 (with `get_session` dependency)
- **Logging**: `structlog`을 사용한 구조화된 로깅 (Key-Value 형식)
- **Authentication**: Supabase Auth & JWT

## 🛠️ Key Components
- `app/coupang_client.py`: 쿠팡 API 연동 클라이언트
- `app/ownerclan_client.py`: 오너클랜 API 연동 클라이언트
- `app/services/`: 비즈니스 로직 처리 서비스 레이어
- `app/models.py`: SQLAlchemy 모델 정의

## 📝 Backend Guidelines
- **Logging**: `logger.info("message", key="value")` 형식을 권장합니다.
- **Transactions**: 데이터 변경 작업 시 `@transactional` 데코레이터 또는 세션 관리에 유의합니다.
- **Async**: API 엔드포인트는 가급적 `async def`를 사용하고, 블로킹 작업은 `BackgroundTasks`를 활용합니다.
- **Pydantic**: 모든 요청/응답 모델은 `app/schemas/`에 정의하고 타입을 명시합니다.
