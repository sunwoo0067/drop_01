# DB 3개 분리 설계 (source / dropship / market)

## 1. 목표

현재 단일 Postgres DB(`drop01`)에 혼재된 데이터를 아래 3개 DB로 **물리 분리**합니다.

- **source DB**: 공급사(오너클랜) 원본/스냅샷 데이터 저장
- **dropship DB**: 내부 가공/상품화 데이터 저장
- **market DB**: 마켓(쿠팡 등) 연동 결과 및 운영 데이터 저장

### 1.1 기대 효과

- 데이터 성격(원본/가공/운영)의 분리로 스키마/마이그레이션/권한 관리가 단순해짐
- 대용량 원본(raw) 테이블이 운영성 테이블에 주는 부담 감소
- 확장(공급사 추가/마켓 추가) 시 영향 범위 축소

---

## 2. 범위

### 2.1 포함

- Postgres 서버는 그대로 유지, DB만 3개로 분리
- SQLAlchemy 엔진/세션을 DB 3개로 분리
- 모델의 **교차 DB Foreign Key 제거**(컬럼은 UUID로 유지)
- 데이터 이관(선택지 및 절차) 정리
- Alembic 운영 전략 정리

### 2.2 제외(이번 단계에서 하지 않음)

- Cross-DB JOIN을 가능하게 하는 FDW/Postgres 확장 도입
- 분산 트랜잭션(2PC) 도입
- 이벤트 소싱/CDC 도입

---

## 3. 현행 요약

- 단일 DB(`drop01`)에 공급사 원본, 가공 상품, 마켓 운영 데이터가 혼재
- FastAPI에서 `Depends(get_session)` 기반으로 단일 세션을 사용
- 벡터 임베딩(`pgvector`) 사용 가능성이 있음
  - `benchmark_products.embedding` (market 성격)
  - `embeddings.embedding` / `sourcing_candidates` (dropship 성격)

---

## 4. 핵심 제약사항 및 원칙

### 4.1 교차 DB Foreign Key 불가

Postgres에서 DB가 다르면 DB-level FK 제약을 걸 수 없습니다.

- 따라서 아래 관계는 **FK 제약을 제거**하고, **UUID 컬럼만 유지**합니다.

#### 4.1.1 교차 DB 관계(예상)

- dropship → source
  - `products.supplier_item_id` (UUID) → `supplier_item_raw.id` (UUID)
- market → dropship
  - `market_listings.product_id` (UUID) → `products.id` (UUID)
- dropship → market
  - `sourcing_candidates.benchmark_product_id` (UUID) → `benchmark_products.id` (UUID)

### 4.2 교차 DB JOIN 불가

DB가 다르면 일반 SQL로 JOIN을 수행할 수 없습니다.

- 애플리케이션 레벨에서
  - 1) A DB에서 ID 목록 조회
  - 2) B DB에서 `IN (...)`으로 재조회
  형태로 처리합니다.

### 4.3 트랜잭션 원칙

- 단일 요청에서 여러 DB에 쓰기가 발생할 수 있으나, **원자적 보장(ACID) 범위는 DB 단위**입니다.
- 교차 DB 쓰기는 다음 원칙을 따릅니다.
  - **기본**: 한 요청에서 2개 이상 DB에 쓰기를 하지 않도록 설계
  - 불가피한 경우: 실패 시 보상(롤백) 전략을 문서화

---

## 5. DB 구성(권장)

### 5.1 DB 이름

- `drop01_source`
- `drop01_dropship`
- `drop01_market`

### 5.2 환경 변수 예시

```bash
SOURCE_DATABASE_URL=postgresql+psycopg://sunwoo@/drop01_source?host=/var/run/postgresql&port=5434
DROPSHIP_DATABASE_URL=postgresql+psycopg://sunwoo@/drop01_dropship?host=/var/run/postgresql&port=5434
MARKET_DATABASE_URL=postgresql+psycopg://sunwoo@/drop01_market?host=/var/run/postgresql&port=5434
```

> 참고: 현재 프로젝트의 `alembic.ini`는 `drop01`을 가리키고 있으므로 분리 후에는 전략에 따라 변경이 필요합니다.

---

## 6. 테이블 배치(최종)

### 6.1 source DB

- `supplier_accounts`
- `supplier_sync_jobs`, `supplier_sync_state`
- `supplier_raw_fetch_log`
- `supplier_item_raw`, `supplier_order_raw`, `supplier_qna_raw`, `supplier_category_raw`

### 6.2 dropship DB

- `products`
- `sourcing_candidates`
- `embeddings`
- `api_keys`

### 6.3 market DB

- `market_accounts`
- `market_order_raw`, `market_product_raw`
- `market_listings`
- `orders`, `supplier_orders`
- `benchmark_products`, `benchmark_collect_jobs`

---

## 7. 애플리케이션 코드 변경(요약)

### 7.1 변경 파일

- `app/settings.py`
  - 단일 `DATABASE_URL` → 3개 DB URL(`SOURCE_`, `DROPSHIP_`, `MARKET_`)로 확장
- `app/db.py`
  - 엔진 3개 생성
  - 세션 전략 결정(권장: 멀티 바인드)
- `app/models.py`
  - 모델을 DB 그룹으로 분리(메타데이터/베이스 분리)
  - 교차 DB FK 제거
- `app/main.py`
  - DB별 extension/bootstrap 처리
  - 특히 `pgvector`는 필요한 DB에만 적용

### 7.2 세션 전략(권장: 멀티 바인드)

- API 레벨에서는 `Depends(get_session)`을 유지
- SQLAlchemy `Session`이 모델/테이블별로 `binds`를 통해 적절한 DB 엔진을 사용
- 장점
  - 기존 코드 변경량 최소
  - 대부분의 조회/저장 로직을 유지
- 주의
  - 한 세션으로 여러 DB를 동시에 만질 수 있으므로, 4.3 트랜잭션 원칙을 준수해야 함

---

## 8. pgvector(extension) 적용 정책

벡터 컬럼이 있는 DB에만 extension을 설치합니다.

- dropship DB
  - `embeddings`, (필요 시) `sourcing_candidates` 관련
- market DB
  - `benchmark_products` 관련
- source DB
  - 기본적으로 불필요

---

## 9. 데이터 이관 전략

### 9.1 선택지 A(간단): 재수집/재생성

- 개발 초기/데이터 손실 허용 시
- raw는 재수집
- dropship/market은 재가공/재동기화

### 9.2 선택지 B(보존): 테이블 단위 dump/restore

- 기존 `drop01`에서 DB별로 테이블을 분리하여 옮김
- 주의 사항
  - sequence/identity reset
  - vector extension을 먼저 생성
  - FK 제약은 교차 DB에선 제거됨

---

## 10. Alembic 운영 전략

### 10.1 권장: DB별 Alembic 환경 3개

- `alembic_source/`, `alembic_dropship/`, `alembic_market/` 또는
- 동일 `alembic/` 아래에서 env를 분기하는 3개 엔트리 구성

각 DB에 대해
- 독립적인 `alembic.ini`(또는 실행 시 URL 주입)
- 독립적인 `versions/` 관리

### 10.2 적용 순서(예시)

1) source migrations
2) dropship migrations
3) market migrations

---

## 11. 롤백/리스크

- **리스크**: 교차 DB 쓰기 실패 시 데이터 불일치
  - 대응: 쓰기 순서 표준화, 실패 시 보상 로직 정의
- **리스크**: 운영/개발 환경에서 DB URL 혼선
  - 대응: `.env.example`에 3개 URL 명시, 부팅 시 현재 DB 연결 로깅

---

## 12. 진행 체크리스트

1) DB명/URL 확정 및 `.env.example` 업데이트
2) 모델 그룹핑 및 교차 FK 제거
3) `db.py`에 엔진/세션 분리 적용
4) `main.py`에서 vector extension 적용 위치 확정
5) Alembic 전략 확정 및 baseline 생성
6) (선택) 데이터 이관 수행

---

## 문서 메타

- 생성일: 2025-12-17
- 상태: 초안
