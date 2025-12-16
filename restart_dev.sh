#!/usr/bin/env bash
set -euo pipefail

./stop_frontend.sh || true
./stop_api.sh || true

./start_api.sh
./start_frontend.sh

echo "[완료] 백엔드(8888), 프런트(3333) 재시작 완료"
