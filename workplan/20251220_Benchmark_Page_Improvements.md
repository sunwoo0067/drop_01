# Benchmark: 기능/페이지 개선 계획 (2025-12-20)

## 배경
- 벤치마크 수집 기능은 다중 마켓 랭킹을 모으고 LangGraph 기반 소싱 워크플로우의 입력으로 사용된다.
- 현 UI는 카드 목록/수동 새로고침 중심이라 대량 데이터 운영, 상태 모니터링, 상세 분석이 어렵다.
- 수집 job/상품 데이터에 대한 필수 메타데이터(범주, 품질 점수, 태그 등)가 부족해 AI/MD가 활용하기 힘들다.

## 현재 문제
1. **수집 신뢰성/가시성 부족**
   - `/benchmarks/collect/ranking`은 marketCode=ALL 시 동시 실행 전략이 없어 대기열/재시작이 어렵고, 실패 사유가 job.last_error 문자열에만 남는다.
   - Job history/진행률 API는 있으나 UI에는 최근 5건만 보이고, 완료된 작업 열람·재시작, 실패 마켓 재시도 UI가 없다.
2. **상품 데이터 활용성 제약**
   - 단순 목록 API(`GET /api/benchmarks`)만 있어 페이지네이션, 범주/가격대 필터링, 품질 지표(리뷰·블록 여부) 정렬을 지원하지 않는다.
   - 상세 보기(`GET /api/benchmarks/{id}`)를 UI에서 사용하지 않아 detail_html, raw_html, painPoints, reviewSummary 데이터를 검토할 수 없다.
3. **벤치마크 페이지 UX 부족**
   - 카드형 뷰 50개 고정 + 새로고침 버튼만 제공하며, 결과 다운로드/정렬 UI가 없다.
   - 진행 중 Job 알림만 있고 완료 결과나 실패 사유 알림이 없어 사용자가 poll 해야 한다.
   - 소싱/상품 가공과 연결되는 CTA(예: "이 벤치마크로 소싱 시작")가 없다.

## 개선 목표
- 수집 파이프라인의 안정성과 상태 추적을 높인다.
- API/DB에 벤치마크 품질 지표·검색/정렬 옵션을 확장한다.
- 프런트 UI를 목록+상세 투 패널 구조로 개편해 분석/후속 액션을 자연스럽게 한다.

## 작업 항목
1. **수집 파이프라인 개선 (백엔드)**
   - BenchmarkCollectJob에 `category_url`, `total_count`, `processed_count`, `retry_of_job_id` 필드 추가(Alembic).
   - `collect_benchmark_ranking`를 Celery/Background task queue처럼 재시작 가능한 구조로 리팩터링하고, market별 실패를 개별 Job item으로 기록.
   - `GET /api/benchmarks/jobs`에 상태 필터/offset 도입, `/jobs/{id}/retry` API 추가로 실패 Job 재시작 지원.
2. **데이터/검색 기능 보강 (백엔드)**
   - BenchmarkProduct에 `category_path`, `review_count`, `rating`, `embedding_updated_at`, `quality_score` 추가 및 수집 시 저장.
   - `/api/benchmarks`에 다중 필터(시장, 가격 범위, 카테고리 키워드, 품질 점수, review threshold) 및 pagination 응답(`items`, `total`, `offset`, `limit`).
   - `/api/benchmarks/{id}` 응답에 LangGraph 입력으로 쓰일 요약 필드(e.g. `aiSummary`, `recommendedKeywords`) 포함.
3. **벤치마크 페이지 UX 개편 (프런트)**
   - 레이아웃: 좌측 필터 패널 + 우측 결과 테이블(가상 스크롤) + 우측 Drawer로 상세/원문/이미지/수집 로그 표시.
   - Job 모니터 탭: 진행/완료/실패 Job 리스트, Job 클릭 시 상태 타임라인 및 실패 마켓 재시도 버튼.
   - 액션 버튼: "소싱 실행"(POST `/api/sourcing/benchmark/{id}`), "CSV 내보내기", "품질 태그 편집"을 지원.
   - useEffect polling 대신 SSE/WebSocket (예: `/api/jobs/stream`)으로 실시간 상태 반영.
4. **품질 모니터링 & 알림**
   - scripts/test_benchmark.py에 멀티마켓 케이스/품질 점수 검증 추가.
   - Slack/Webhook 통합: Job 실패/성공 시 알림 payload 발송.

## 예상 산출물
- Alembic migration + models 업데이트
- 백엔드 API 확장/신규 엔드포인트
- `frontend/src/app/benchmarks` 하위 리팩터링 (컴포넌트 세분화, Job 탭, 상세 Drawer)
- QA 체크리스트 & 테스트 스크립트 업데이트

## 타임라인(예시)
1. 주 1: 스키마 확장, Job API 개선, 기본 테스트 보강
2. 주 2: 프런트 필터/목록/상세 개편, SSE 기반 상태 구독, UX QA
3. 주 3: LangGraph 연계 버튼, CSV/Export, Slack 알림, 최종 문서화

