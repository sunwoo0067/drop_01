#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"
IMAGE="${GITHUB_MCP_IMAGE:-ghcr.io/github/github-mcp-server:latest}"

if ! command -v docker >/dev/null 2>&1; then
  echo "[GitHub MCP] Docker가 설치되어 있어야 합니다." >&2
  exit 1
fi

if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # 로컬 .env를 읽어 GitHub PAT 및 추가 옵션을 불러온다.
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi

if [[ -z "${GITHUB_PERSONAL_ACCESS_TOKEN:-}" ]]; then
  echo "[GitHub MCP] 환경 변수 GITHUB_PERSONAL_ACCESS_TOKEN이 필요합니다." >&2
  echo "[GitHub MCP] .env 또는 셸 환경에 GitHub PAT를 설정하세요." >&2
  exit 1
fi

DOCKER_CMD=(docker run -i --rm)

if [[ -t 1 ]]; then
  DOCKER_CMD+=(-t)
fi

DOCKER_CMD+=(-e "GITHUB_PERSONAL_ACCESS_TOKEN=${GITHUB_PERSONAL_ACCESS_TOKEN}")

add_env_if_set() {
  local var_name="$1"
  local value="${!var_name:-}"
  if [[ -n "${value}" ]]; then
    DOCKER_CMD+=(-e "${var_name}=${value}")
  fi
}

add_env_if_set "GITHUB_HOST"
add_env_if_set "GITHUB_TOOLSETS"
add_env_if_set "GITHUB_TOOLS"
add_env_if_set "GITHUB_TOOLS_CONFIG"
add_env_if_set "GITHUB_READ_ONLY"
add_env_if_set "GITHUB_LOG_LEVEL"

if [[ -n "${GITHUB_MCP_EXTRA_DOCKER_FLAGS:-}" ]]; then
  # shellcheck disable=SC2206
  EXTRA_FLAGS=(${GITHUB_MCP_EXTRA_DOCKER_FLAGS})
  DOCKER_CMD+=("${EXTRA_FLAGS[@]}")
fi

echo "[GitHub MCP] 컨테이너 이미지를 사용합니다: ${IMAGE}"
echo "[GitHub MCP] 서버를 시작합니다... (Ctrl+C 로 종료)"
exec "${DOCKER_CMD[@]}" "${IMAGE}" "$@"
