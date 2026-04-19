#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${ENV_FILE:-${SCRIPT_DIR}/.env}"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "缺少 ${ENV_FILE}，先执行 cp .env.example .env 并填写配置。" >&2
  exit 1
fi

read_env() {
  local key="$1"
  local value
  value="$(grep -E "^${key}=" "${ENV_FILE}" | tail -n1 | cut -d= -f2- || true)"
  printf '%s' "${value}"
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "缺少命令：$1" >&2
    exit 1
  fi
}

check_tcp() {
  local host="$1"
  local port="$2"
  timeout 3 bash -c "cat < /dev/null > /dev/tcp/${host}/${port}" 2>/dev/null
}

require_command docker
require_command bash
require_command free
require_command df
require_command ss

PYTHON_BIN="$(command -v python3 || command -v python || true)"
if [[ -z "${PYTHON_BIN}" ]]; then
  echo "缺少 python3/python，无法解析模型服务 URL。" >&2
  exit 1
fi

app_port="$(read_env APP_PORT)"
ollama_url="$(read_env OLLAMA_BASE_URL)"
vllm27_url="$(read_env VLLM_QWEN27_BASE_URL)"
vllm35_url="$(read_env VLLM_QWEN35_BASE_URL)"
persist_root="$(read_env PERSIST_ROOT)"
persist_root="${persist_root:-/opt/rag-platform}"
persist_probe="${persist_root%/*}"
persist_probe="${persist_probe:-/}"

if ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose 插件不可用。" >&2
  exit 1
fi

docker compose --env-file "${ENV_FILE}" -f "${SCRIPT_DIR}/docker-compose.yml" config >/dev/null

mem_gb="$(free -g | awk '/^Mem:/ {print $2}')"
disk_gb="$(df -BG "${persist_probe}" | awk 'NR==2 {gsub(/G/, "", $4); print $4}')"
vm_map_count="$(sysctl -n vm.max_map_count)"

echo "Memory: ${mem_gb}G"
echo "Disk free on /opt: ${disk_gb}G"
echo "vm.max_map_count: ${vm_map_count}"

if [[ "${mem_gb}" -lt 16 ]]; then
  echo "警告：内存低于 16G，完整栈可能不稳定。" >&2
fi

if [[ "${disk_gb}" -lt 80 ]]; then
  echo "警告：/opt 可用空间低于 80G，索引和镜像可能不足。" >&2
fi

if [[ "${vm_map_count}" -lt 262144 ]]; then
  echo "警告：vm.max_map_count 低于 262144，Elasticsearch 可能无法启动。" >&2
fi

echo "检查 GPU 服务器模型连通性..."
while IFS=: read -r host port; do
  check_tcp "${host}" "${port}" || { echo "无法连接 ${host}:${port}" >&2; exit 1; }
done < <("${PYTHON_BIN}" - "${ollama_url}" "${vllm27_url}" "${vllm35_url}" <<'PY'
import sys
from urllib.parse import urlparse

for raw in sys.argv[1:]:
    parsed = urlparse(raw)
    host = parsed.hostname
    port = parsed.port
    if not host or not port:
        raise SystemExit(f"invalid url in env: {raw}")
    print(f"{host}:{port}")
PY
)

echo "检查目标端口占用..."
for port in "${app_port:-80}" 5432 6379 9092 9000 9200 19530 9998; do
  if ss -ltn "( sport = :${port} )" | grep -q ":${port}"; then
    echo "警告：端口 ${port} 已被占用，请确认是否冲突。"
  fi
done

echo "Preflight 检查完成。"
