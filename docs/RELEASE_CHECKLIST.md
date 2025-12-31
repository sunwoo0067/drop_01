# 릴리즈 체크리스트 (Release Checklist v1.3.2-Final-B)

운영 환경 투입 전 다음 항목들을 반드시 확인하십시오.

> [!IMPORTANT]
> **운영팀 Day 1 퀵스타트 (Quick Start)**
> ```bash
> # 0. 설정 및 엔트리포인트 최종 검증 (Dry-run)
> REQUIRE_ENV=true DRY_RUN=true ./ops/run_ownerclan_sync.sh
> 
> # 1. 레거시 스모크 (안전망 확인)
> REQUIRE_ENV=true OWNERCLAN_USE_HANDLER=false ./ops/run_ownerclan_sync.sh --maxItems 10
> 
> # 2. 신규 핸들러 스모크
> REQUIRE_ENV=true OWNERCLAN_USE_HANDLER=true ./ops/run_ownerclan_sync.sh --maxItems 50
> ```

## 1. 환경 변수 및 설정 확인
- [ ] `.env` 파일이 `.env.example`을 기준으로 누락 없이 작성되었는가?
    - [ ] **형식 준수**: `.env`는 bash 호환 `KEY=VALUE` 형식인가? (복잡한 이스케이프 자제)
- [ ] `DATABASE_URL`, `OWNERCLAN_PRIMARY_USERNAME/PASSWORD` 등의 필수값이 실제 값으로 채워져 있는가?
- [ ] `OWNERCLAN_USE_HANDLER`: 첫 배포 시 `false`로 설정 (레거시 스모크 테스트용).
- [ ] **고급 설정 (커스텀 실행 시)**: `SYNC_ENTRYPOINT`를 정의할 경우, 공백으로 구분된 명령만 허용됩니다. (따옴표를 포함한 중첩 문자열 비권장)

## 2. DB 및 인프라 점검
- [ ] **엔트리포인트 확인**: 운영 서버에서 아래 명령어가 도움말을 출력하는가?
  ```bash
  # 실제 프로젝트 엔트리포인트에 맞게 조정 (예: python3 -m app.cli run-sync --help)
  python3 -m app.cli run-sync --help 
  ```
- [ ] **DB 인덱스 확인**: 아래 SQL을 실행하여 유니크 인덱스가 존재하는지 확인하십시오.
  ```sql
  -- (supplier_code, item_code) UNIQUE 인덱스 존재 확인 (스키마 포함)
  SELECT schemaname, indexname, indexdef 
  FROM pg_indexes 
  WHERE tablename = 'supplier_item_raw'
    AND indexdef ILIKE '%unique%'
    AND indexdef ILIKE '%(supplier_code, item_code)%';
  ```
- [ ] `supplier_item_raw` 테이블의 `raw` 컬럼이 `JSONB` 타입인가?
- [ ] 운영 네트워크에서 오너클랜 API(`api.ownerclan.com`) 접근이 허용되어 있는가?

## 3. 모니터링 준비
- [ ] **데이터 정규화 확인**: `supplier_item_raw.raw->'detail_html'`에 HTML 태그가 정규화되어 적재되는지 확인할 준비가 되었는가?
- [ ] 로그 수집 시스템에서 `HTTP 401`, `HTTP 429` 알림이 설정되었는가?

## 4. 롤백 및 복구 전략
- [ ] 문제 발생 시 `OWNERCLAN_USE_HANDLER=false`로 즉시 복구할 수 있는가?
- [ ] **상태 재개(Resume) 검증**: 실행 중 강제 종료 후 재실행 시 `last_cursor`에서 비정상 루프 없이 고르게 진행되는가?

## 5. Day 1: 단계별 스모크 테스트 (Day 1 Smoke Test)
운영 투입 첫날은 아래 순서대로 실행하여 안전성을 검증합니다.

1. **설정값 검증 (Dry-run)**
   ```bash
   REQUIRE_ENV=true DRY_RUN=true ./ops/run_ownerclan_sync.sh
   # [SUCCESS] Dry-run completed 메시지 확인
   ```
2. **레거시 스모크 (안전망 확인)**
   ```bash
   REQUIRE_ENV=true OWNERCLAN_USE_HANDLER=false ./ops/run_ownerclan_sync.sh --maxItems 10
   ```
3. **신규 핸들러 스모크**
   ```bash
   REQUIRE_ENV=true OWNERCLAN_USE_HANDLER=true ./ops/run_ownerclan_sync.sh --maxItems 50
   ```
4. **적재 결과 확인**: 아래 SQL로 최근 10분 내 데이터가 들어왔는지 확인하십시오.
   ```sql
   -- 최근 10분 내 적재 건수 (1개 이상이면 성공)
   SELECT count(*) FROM supplier_item_raw 
   WHERE supplier_code='ownerclan' AND fetched_at > now() - interval '10 minutes';
   ```

### 스모크 결과 해석 가이드 (Operator Guide)
- **0건 적재**: 인증(401), 네트워크 액세스, 엔트리포인트 경로, 또는 DB 연결 정보를 최우선 확인하십시오.
- **건수는 있으나 속도(items/sec) 급락**: HTTP 429(Rate Limit) 또는 DB 락 충돌 가능성이 높습니다.
- **HTTP 401 에러**: `TROUBLESHOOTING_PLAYBOOK.md`의 "대표계정 재설정 API"를 즉시 실행하십시오.
