#!/usr/bin/env bash
set -euo pipefail

PORT="3333"
PID_FILE=".frontend.pid"
LOG_FILE="frontend.log"

if ss -ltn | grep -qE ":${PORT}\\b"; then
  echo "[프런트] 포트 ${PORT}가 이미 사용 중입니다. 먼저 stop_frontend.sh를 실행하세요." >&2
  exit 1
fi

(
  cd frontend
  nohup npm run dev -- --hostname 0.0.0.0 > "../${LOG_FILE}" 2>&1 &
  echo $! > "../${PID_FILE}"
)

echo "[프런트] 시작 완료: http://localhost:${PORT} (pid=$(cat "${PID_FILE}"))"
