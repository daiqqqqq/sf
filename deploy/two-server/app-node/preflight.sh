#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${ENV_FILE:-${SCRIPT_DIR}/.env}"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing ${ENV_FILE}. Run 'cp .env.example .env' first." >&2
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
    echo "Missing required command: $1" >&2
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
  echo "Missing python3/python. Unable to parse model service URLs." >&2
  exit 1
fi

app_port="$(read_env APP_PORT)"
ollama_url="$(read_env OLLAMA_BASE_URL)"
vllm27_url="$(read_env VLLM_QWEN27_BASE_URL)"
vllm35_url="$(read_env VLLM_QWEN35_BASE_URL)"
gpu_node_host="$(read_env GPU_NODE_HOST)"
gpu_exporter_port="$(read_env GPU_EXPORTER_PORT)"
persist_root="$(read_env PERSIST_ROOT)"
persist_root="${persist_root:-/opt/rag-platform}"
persist_probe="${persist_root%/*}"
persist_probe="${persist_probe:-/}"

if ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose plugin is unavailable." >&2
  exit 1
fi

docker compose --env-file "${ENV_FILE}" -f "${SCRIPT_DIR}/docker-compose.yml" config >/dev/null

mem_gb="$(free -g | awk '/^Mem:/ {print $2}')"
disk_gb="$(df -BG "${persist_probe}" | awk 'NR==2 {gsub(/G/, "", $4); print $4}')"
vm_map_count="$(sysctl -n vm.max_map_count)"

echo "Memory: ${mem_gb}G"
echo "Disk free near ${persist_root}: ${disk_gb}G"
echo "vm.max_map_count: ${vm_map_count}"

if [[ "${mem_gb}" -lt 16 ]]; then
  echo "Warning: memory is below 16G. The full stack may be unstable." >&2
fi

if [[ "${disk_gb}" -lt 80 ]]; then
  echo "Warning: available disk space is below 80G. Images and indices may run out of space." >&2
fi

if [[ "${vm_map_count}" -lt 262144 ]]; then
  echo "Warning: vm.max_map_count is below 262144. Elasticsearch may fail to start." >&2
fi

echo "Checking GPU model endpoints..."
while IFS=: read -r host port; do
  check_tcp "${host}" "${port}" || { echo "Unable to connect to ${host}:${port}" >&2; exit 1; }
done < <("${PYTHON_BIN}" - "${ollama_url}" "${vllm27_url}" "${vllm35_url}" <<'PY'
import sys
from urllib.parse import urlparse

for raw in sys.argv[1:]:
    parsed = urlparse(raw)
    if not parsed.hostname or not parsed.port:
        raise SystemExit(f"invalid url in env: {raw}")
    print(f"{parsed.hostname}:{parsed.port}")
PY
)

gpu_node_host="${gpu_node_host:-192.168.110.241}"
gpu_exporter_port="${gpu_exporter_port:-9400}"
echo "Checking GPU exporter endpoint..."
check_tcp "${gpu_node_host}" "${gpu_exporter_port}" || {
  echo "Unable to connect to GPU exporter ${gpu_node_host}:${gpu_exporter_port}. Deploy dcgm-exporter on the GPU node first." >&2
  exit 1
}

echo "Checking local port conflicts..."
for port in "${app_port:-80}" 5432 6379 9092 9000 9200 19530 9998 9090 3000; do
  if ss -ltn "( sport = :${port} )" | grep -q ":${port}"; then
    echo "Warning: port ${port} is already in use. Verify there is no conflict." >&2
  fi
done

echo "Preflight checks completed."
