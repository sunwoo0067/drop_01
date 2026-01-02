#!/bin/bash
# OwnerClan Sync 동기화 실행 스크립트 (The Ultimate Multi-Job)
set -euo pipefail

# 1. 경로 및 환경 설정
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT="$SCRIPT_DIR/.."
ENV_PATH="$PROJECT_ROOT/.env"

# 2. 가변 파라미터 로드 (기본값 설정 후 .env로 오버라이드 가능)
REQUIRE_ENV=${REQUIRE_ENV:-false}
JOB_TYPE=${OWNERCLAN_JOB_TYPE:-"ownerclan_items_raw"}

# 환경 변수 사전 로드 (JOB_TYPE별 설정을 .env에서 제어 가능하게 함)
if [ -f "$ENV_PATH" ]; then
  set -a
  set +u
  source "$ENV_PATH" || { echo "[CRITICAL] Failed to source .env at $ENV_PATH"; exit 8; }
  set -u
  set +a
else
  [ "$REQUIRE_ENV" = "true" ] && { echo "[CRITICAL] .env file not found at $ENV_PATH"; exit 2; }
fi

# 3. 운영 옵션 확정
VERSION="Final-B"
DRY_RUN=${DRY_RUN:-false}
USE_HANDLER=${OWNERCLAN_USE_HANDLER:-false}
BATCH_SIZE=${OWNERCLAN_BATCH_COMMIT_SIZE:-200}
DEFAULT_ENTRYPOINT="python3 -m app.cli run-sync"
SYNC_ENTRYPOINT=${SYNC_ENTRYPOINT:-"$DEFAULT_ENTRYPOINT"}

# JOB_TYPE 기반 고유 락 파일 및 ID 생성
LOCK_FILE=${LOCK_FILE:-"/tmp/ownerclan_sync_${JOB_TYPE}.lock"}
RUN_ID=${RUN_ID:-"sync_${JOB_TYPE}_$(date +%Y%m%d_%H%M%S)"}

# [안전핀 1] flock 도구 존재 확인
if ! command -v flock >/dev/null 2>&1; then
  echo "[CRITICAL] 'flock' command not found."
  exit 6
fi

# [안전핀 2] 필수 환경 변수 값 검증 (상황에 따라 확장 가능)
if [ "$REQUIRE_ENV" = "true" ]; then
  REQUIRED_KEYS=("DATABASE_URL" "OWNERCLAN_PRIMARY_USERNAME" "OWNERCLAN_PRIMARY_PASSWORD")
  for key in "${REQUIRED_KEYS[@]}"; do
    if [ -z "${!key:-}" ]; then
      echo "[CRITICAL] Required environment variable '$key' is missing or empty."
      exit 4
    fi
  done
fi

# [안전핀 3] SYNC_ENTRYPOINT 형식 강제 (따옴표 포함 시 중단)
if [[ "$SYNC_ENTRYPOINT" == *\"* || "$SYNC_ENTRYPOINT" == *"'"* ]]; then
  echo "[CRITICAL] SYNC_ENTRYPOINT must not contain quotes. Use space-separated tokens only."
  exit 9
fi

# 엔트리포인트 문자열을 배열로 파싱
read -r -a ENTRYPOINT_ARR <<< "$SYNC_ENTRYPOINT"

# 에러 트랩
trap 'echo "[ERROR] [$VERSION] [ID:$RUN_ID] Line $LINENO failed. cmd=$BASH_COMMAND, Mode=$USE_HANDLER, Batch=$BATCH_SIZE"' ERR

# [안전핀 4] 중복 실행 방지 (flock)
if ! ( mkdir -p "$(dirname "$LOCK_FILE")" 2>/dev/null && touch "$LOCK_FILE" ) 2>/dev/null; then
  echo "[CRITICAL] Cannot write lock file at '$LOCK_FILE'."
  exit 7
fi

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "[CRITICAL] Another process for '$JOB_TYPE' is already running. Aborting."
  [ -x "$(command -v lsof)" ] && lsof "$LOCK_FILE" || true
  exit 5
fi

echo "===================================================="
echo "OwnerClan Sync Starter ($VERSION / ID: $RUN_ID)"
echo "Time: $(date)"
echo "Job: $JOB_TYPE"
echo "Mode: $( [ "$USE_HANDLER" = "true" ] && echo "New Handler" || echo "Legacy Path" )"
echo "Entrypoint: ${ENTRYPOINT_ARR[*]}"
echo "===================================================="

cd "$PROJECT_ROOT"

# [안전핀 5] 엔트리포인트 검증
if ! "${ENTRYPOINT_ARR[@]}" --help >/dev/null 2>&1; then
  echo "[CRITICAL] Entrypoint validation failed: ${ENTRYPOINT_ARR[*]}"
  exit 3
fi

# Dry-run 체크
if [ "$DRY_RUN" = "true" ]; then
  echo "[SUCCESS] Dry-run [ID:$RUN_ID] completed."
  exit 0
fi

# 실행 (추가 인자 $@ 전달 가능)
"${ENTRYPOINT_ARR[@]}" \
  --job-type "$JOB_TYPE" \
  --use-handler "$USE_HANDLER" \
  --batch-commit-size "$BATCH_SIZE" \
  "$@"

echo "[SUCCESS] [ID:$RUN_ID] Synchronization completed successfully."
