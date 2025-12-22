#!/bin/bash
# Ollama GPU 가속 구동 스크립트 (WSL2 RTX 4070 전용)

PROJECT_ROOT="/home/sunwoo/project/drop/drop_01/drop_01_dev"
OLLAMA_BIN="$PROJECT_ROOT/ollama_update/bin/ollama"
OLLAMA_LIB="$PROJECT_ROOT/ollama_update/lib/ollama"
WSL_LIB="/usr/lib/wsl/lib"

# 환경 변수 설정
export LD_LIBRARY_PATH="$WSL_LIB:$OLLAMA_LIB:$OLLAMA_LIB/cuda_v13:$LD_LIBRARY_PATH"
export OLLAMA_DEBUG=1

echo ">>> 기존 올라마 프로세스 종료 중..."
killall ollama 2>/dev/null || true
sleep 1

echo ">>> GPU 가속 올라마 서버 실행 중..."
nohup "$OLLAMA_BIN" serve > "$PROJECT_ROOT/ollama_gpu.log" 2>&1 &

echo ">>> 서버 시작 대기 중 (5초)..."
sleep 5

if "$OLLAMA_BIN" list >/dev/null 2>&1; then
    echo ">>> 올라마 서버가 정상적으로 시작되었습니다."
    "$OLLAMA_BIN" ps
else
    echo ">>> 에러: 서버 시작에 실패했습니다. $PROJECT_ROOT/ollama_gpu.log 를 확인하세요."
fi
