#!/usr/bin/env bash
set -euo pipefail

PORT="8888"
PID_FILE=".api.pid"

pids_from_port() {
  ss -ltnp 2>/dev/null \
    | grep -E ":${PORT}\\b" \
    | grep -o 'pid=[0-9]*' \
    | cut -d= -f2 \
    | sort -u \
    || true
}

kill_pid_if_alive() {
  local pid="$1"
  if [ -z "${pid}" ]; then
    return 0
  fi
  if kill -0 "${pid}" 2>/dev/null; then
    kill "${pid}" 2>/dev/null || true
  fi
}

if [ -f "${PID_FILE}" ]; then
  pid="$(cat "${PID_FILE}" | tr -d '[:space:]' || true)"
  kill_pid_if_alive "${pid}"
fi

for pid in $(pids_from_port); do
  kill_pid_if_alive "${pid}"
done

for _ in $(seq 1 30); do
  if ! ss -ltn 2>/dev/null | grep -qE ":${PORT}\\b"; then
    rm -f "${PID_FILE}" || true
    echo "[백엔드] 종료 완료 (포트 ${PORT})"
    exit 0
  fi
  sleep 0.2
done

for pid in $(pids_from_port); do
  kill -9 "${pid}" 2>/dev/null || true
 
  # uvicorn reloader/worker가 여러 개일 수 있으므로 포트 기준으로 반복 종료한다.
 

done

rm -f "${PID_FILE}" || true

echo "[백엔드] 강제 종료 완료 (포트 ${PORT})"
