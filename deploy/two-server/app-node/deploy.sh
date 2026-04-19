#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-${SCRIPT_DIR}/docker-compose.yml}"
ENV_FILE="${ENV_FILE:-${SCRIPT_DIR}/.env}"
SKIP_PULL="${SKIP_PULL:-1}"

show_diagnostics() {
  echo "部署失败，输出当前容器状态与关键服务日志..." >&2
  docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" ps || true
  docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" logs --tail=200 \
    nginx platform-api rag-engine celery-worker celery-beat kafka minio minio-init milvus reranker postgres redis \
    || true
}

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "缺少 ${ENV_FILE}，请先从 .env.example 复制并填写。" >&2
  exit 1
fi

trap 'rc=$?; if [[ $rc -ne 0 ]]; then show_diagnostics; fi; exit $rc' EXIT

if [[ "${SKIP_PULL}" != "1" ]]; then
  docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" pull --ignore-pull-failures
else
  echo "跳过远端拉取，直接使用本地已有镜像。设置 SKIP_PULL=0 可恢复 pull。"
fi
docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" build
docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" up -d --remove-orphans
docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" ps

echo "部署完成。建议继续执行："
echo "docker compose --env-file ${ENV_FILE} -f ${COMPOSE_FILE} logs -f --tail=100 nginx platform-api rag-engine celery-worker"
