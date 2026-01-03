#!/usr/bin/env bash
set -euo pipefail

./scripts/stop_frontend.sh || true
./scripts/stop_api.sh || true

./scripts/start_api.sh
./scripts/start_frontend.sh

echo "[완료] 백엔드(8888), 프런트(3333) 재시작 완료"
