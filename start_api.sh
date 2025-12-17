#!/usr/bin/env bash
set -euo pipefail

PORT="8888"
PID_FILE=".api.pid"
LOG_FILE="api.log"

RELOAD_ARGS=()
if [ "${API_RELOAD:-}" = "1" ]; then
  RELOAD_ARGS+=(--reload)
fi

if ss -ltn | grep -qE ":${PORT}\\b"; then
  echo "[백엔드] 포트 ${PORT}가 이미 사용 중입니다. 먼저 stop_api.sh를 실행하세요." >&2
  exit 1
fi

nohup ./.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port "${PORT}" "${RELOAD_ARGS[@]}" > "${LOG_FILE}" 2>&1 &
echo $! > "${PID_FILE}"

echo "[백엔드] 시작 완료: http://127.0.0.1:${PORT} (pid=$(cat "${PID_FILE}"))"
