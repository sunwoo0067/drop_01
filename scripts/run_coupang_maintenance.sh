#!/usr/bin/env bash
set -euo pipefail

# 쿠팡 운영 루틴(모니터링 + 자동복구)
# - 모니터링: 최신 MarketListing 기준 상태 리포트 생성
# - 자동복구: 이미지 규격 DENIED 대상에 대해 process→update→sync-status 수행

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT_DIR/.venv/bin/python"

if [ ! -x "$PY" ]; then
  echo "[오류] 가상환경 파이썬을 찾을 수 없습니다: $PY" >&2
  exit 1
fi

OUT_DIR="${OUT_DIR:-/tmp}"
NOW="$(date +%Y%m%d_%H%M%S)"

REPORT_OUT="$OUT_DIR/coupang_status_report_${NOW}.json"
FIX_OUT="$OUT_DIR/coupang_fix_denied_images_${NOW}.json"

SCAN_LIMIT="${SCAN_LIMIT:-5000}"
SAMPLE_LIMIT="${SAMPLE_LIMIT:-20}"

FIX_LIMIT="${FIX_LIMIT:-50}"
FIX_MIN_IMAGES="${FIX_MIN_IMAGES:-5}"
FIX_PROCESS_TIMEOUT="${FIX_PROCESS_TIMEOUT:-240}"
FIX_PROCESS_INTERVAL="${FIX_PROCESS_INTERVAL:-3}"
FIX_SYNC_TIMEOUT="${FIX_SYNC_TIMEOUT:-180}"
FIX_SYNC_INTERVAL="${FIX_SYNC_INTERVAL:-10}"

DO_FIX="${DO_FIX:-1}"
DRY_RUN="${DRY_RUN:-0}"

echo "[쿠팡] 상태 리포트 생성: $REPORT_OUT"
"$PY" "$ROOT_DIR/scripts/coupang_status_report.py" \
  --scan-limit "$SCAN_LIMIT" \
  --sample-limit "$SAMPLE_LIMIT" \
  --out "$REPORT_OUT"

if [ "$DO_FIX" = "1" ]; then
  echo "[쿠팡] 이미지 반려 자동 처리 실행: $FIX_OUT"

  EXTRA_ARGS=()
  if [ "$DRY_RUN" = "1" ]; then
    EXTRA_ARGS+=(--dry-run)
  fi

  "$PY" "$ROOT_DIR/scripts/coupang_fix_denied_images.py" \
    --limit "$FIX_LIMIT" \
    --min-images "$FIX_MIN_IMAGES" \
    --process-timeout "$FIX_PROCESS_TIMEOUT" \
    --process-interval "$FIX_PROCESS_INTERVAL" \
    --sync-timeout "$FIX_SYNC_TIMEOUT" \
    --sync-interval "$FIX_SYNC_INTERVAL" \
    --out "$FIX_OUT" \
    "${EXTRA_ARGS[@]}"
else
  echo "[쿠팡] DO_FIX=0 이므로 자동 복구를 건너뜁니다."
fi
