# 운영 가이드 (Operations Guide)

이 문서는 오너클랜 동기화 서비스의 운영, 안정적인 배포(Rollout) 및 장애 발생 시 복구(Rollback) 절차를 설명합니다.

## 처음 실행 체크리스트

1.  **환경 변수 설정**: `.env.example`을 복사하여 `.env` 파일을 생성하고 필수 값들을 채웁니다.
    -   `SOURCE_DATABASE_URL`, `DROPSHIP_DATABASE_URL`, `MARKET_DATABASE_URL`
    -   `OWNERCLAN_PRIMARY_USERNAME`, `OWNERCLAN_PRIMARY_PASSWORD` 등
2.  **설정 검증**: 앱 기동 시 Pydantic validator가 실행됩니다. URL 형식이 틀리거나 필수 값이 누락되면 기동 단계에서 에러가 발생합니다.
3.  **로그 확인**: 기동 후 "배치 커밋 성공" 로그가 정상적으로 찍히는지 확인합니다.

## OwnerClan Handler 점진적 롤아웃 가이드

신규 핸들러(`OwnerClanItemSyncHandler`)는 성능과 안정성이 대폭 개선되었으나, 운영 환경에 맞춰 점진적으로 적용하는 것을 권장합니다.

### 1단계: 수동 검증 (특정 Job에만 적용)
특정 동기화 작업(Job)을 생성할 때 `params`에 `{"useHandler": true, "maxItems": 100}`를 포함하여 소량의 데이터로 먼저 테스트합니다.

### 2단계: 전역 적용 (환경 변수)
안정성이 확인되면 `.env`에서 전역 설정을 변경합니다.
```env
OWNERCLAN_USE_HANDLER=true
```

## 장애 대응 및 롤백 절차

신규 핸들러 사용 중 예상치 못한 장애(데이터 유실, API 속도 제한 등) 발생 시 즉시 레거시 경로로 복구할 수 있습니다.

### 즉시 롤백 방법
`.env` 파일에서 다음 값을 수정하고 앱을 재기동합니다.
```env
OWNERCLAN_USE_HANDLER=false
```
이 설정은 `run_ownerclan_job` 브릿지 로직을 통해 즉시 기존의 `sync_ownerclan_items_raw` 함수를 사용하도록 강제합니다.

## 모니터링 포인트

-   **처리 속도**: `배치 커밋 성공: 누적 X개 | 속도: Y items/sec` 로그를 통해 성능을 모니터링합니다.
-   **재시도 횟수**: `API 재시도 중...` 로그가 너무 빈번하게 발생하면 `OWNERCLAN_API_SLEEP` 값을 높여야 할 수 있습니다.
-   **에러 메시지**: `tenacity.RetryError`가 발생하면 설정된 재시도 횟수(`OWNERCLAN_RETRY_COUNT`)를 초초과한 것이므로 상세 에러를 분석해야 합니다.

## 쉘 및 환경 설정 제약 사항 (Constraints)

-   **SYNC_ENTRYPOINT**: `ops/run_ownerclan_sync.sh` 내에서 엔트리포인트를 배열로 파싱하므로, 공백으로 구분된 단순 명렁어열만 허용됩니다. 따옴표를 중첩하여 사용하는 복잡한 래퍼 커맨드는 비권장됩니다. (예: `poetry run python -m app.cli` 형태는 OK)
-   **.env 포맷**: `set -a; source .env` 방식을 사용하므로, `.env` 파일은 표준 bash 호환 `KEY=VALUE` 형식을 유지해야 합니다.
-   **락 파일**: 컨테이너 환경에서 `/tmp` 쓰기가 제한될 경우, 환경 변수 `LOCK_FILE`을 통해 경로를 오버라이드하십시오.
