# 장애 대응 플레이북 (Troubleshooting Playbook) - OwnerClan Sync

오너클랜 동기화 중 발생할 수 있는 주요 장애 상황별 행동 지침입니다.

## 1. 인증 오류 (401 Unauthorized)
-   **현상**: 로그에 `RuntimeError: 오너클랜 인증이 만료되었습니다(401)` 발생.
-   **원인**: `access_token`이 만료되었거나, 계정 비밀번호가 변경됨.
-   **조치 절차**:
    1.  **대표 계정 재설정**: 인증 실패 시 아래 API를 통해 계정 정보를 갱신하십시오.
        ```bash
        # 운영 환경에 맞춰 <BASE_URL> 및 <AUTH_TOKEN>을 수정하십시오.
        curl -X POST "https://<API_DOMAIN>/api/suppliers/ownerclan/primary" \
             -H "Content-Type: application/json" \
             -H "Authorization: Bearer <ADMIN_TOKEN>" \
             -d '{
               "username": "YOUR_OWNERCLAN_ID", 
               "password": "YOUR_OWNERCLAN_PASSWORD"
             }'
        ```
    2.  **토큰 갱신 확인**: DB의 `supplier_accounts` 테이블에서 해당 계정의 `access_token`이 갱신되었는지 확인.
    3.  **스모크 재실행**: `maxItems=10`으로 소량 실행하여 200 OK 여부를 최종 확인.
    4.  **참고**: 비밀번호 자체가 변경된 경우 `.env`의 `OWNERCLAN_PRIMARY_PASSWORD`도 함께 업데이트해야 합니다.

## 2. 속도 제한 (429 Too Many Requests)
-   **현상**: `tenacity.RetryError` 발생 및 로그에 `HTTP 429` 다수 찍힘.
-   **원인**: 짧은 시간 내에 너무 많은 API 호출 시도.
-   **조치**:
    1.  `.env`에서 `OWNERCLAN_API_SLEEP` 값을 상향 조정 (예: 0.5 -> 1.0).
    2.  `OWNERCLAN_API_SLEEP_LOOP` 값을 상향 조정 (예: 1.0 -> 2.0).
    3.  동시 실행 중인 다른 동기화 작업이 있는지 확인.

## 3. 데이터베이스 락 (DB Lock Timeout)
-   **현상**: `OperationalError: lock timeout` 또는 커밋 시 응답 없음.
-   **원인**: 큰 배치를 처리하는 동안 다른 프로세스(예: 상품 가공, 마켓 등록)와 충돌.
-   **조치**:
    1.  `OWNERCLAN_BATCH_COMMIT_SIZE`를 낮춤 (예: 500 -> 100).
    2.  DB 성능 지표(CPU/Memory) 및 활성 쿼리 모니터링.

## 4. 커서 루프/무한 루프 의심
-   **현상**: 로그에 동일한 커서(cursor)값이 반복되거나, 처리량 지표가 올라가지 않음.
-   **원인**: API 응답의 `hasNextPage` 로직 오류 또는 데이터 불일치.
-   **조치**:
    1.  즉시 작업을 중단하고 `OWNERCLAN_USE_HANDLER=false`로 전환하여 레거시 경로로 복구.
    2.  로그에서 문제의 `last_cursor` 값을 추출하여 API 직접 호출 테스트.

## 5. 서버 리소스 부족 (OOM)
-   **현상**: 프로세스가 갑자기 종료되거나 `MemoryError` 발생.
-   **원인**: 상세 페이지 HTML이 너무 크거나, 메모리 내에 너무 많은 아이템을 적재.
-   **조치**:
    1.  배치 사이즈(`first`)를 줄임 (예: 100 -> 50).
    2.  프로세스 메모리 점유율 모니터링.
