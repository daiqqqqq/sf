#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-${SCRIPT_DIR}/docker-compose.yml}"
ENV_FILE="${ENV_FILE:-${SCRIPT_DIR}/.env}"
SKIP_PULL="${SKIP_PULL:-1}"

show_diagnostics() {
  echo "Deployment failed. Current container state and recent logs:" >&2
  docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" ps || true
  docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" logs --tail=200 \
    nginx platform-api rag-engine celery-worker celery-beat kafka minio minio-init milvus reranker postgres redis prometheus grafana \
    || true
}

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing ${ENV_FILE}. Copy it from .env.example first." >&2
  exit 1
fi

trap 'rc=$?; if [[ $rc -ne 0 ]]; then show_diagnostics; fi; exit $rc' EXIT

if [[ "${SKIP_PULL}" != "1" ]]; then
  docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" pull --ignore-pull-failures
else
  echo "Skipping remote image pull. Set SKIP_PULL=0 to enable docker compose pull."
fi

docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" build
docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" up -d --remove-orphans
docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" ps

echo "Deployment completed."
echo "Suggested next command:"
echo "docker compose --env-file ${ENV_FILE} -f ${COMPOSE_FILE} logs -f --tail=100 nginx platform-api rag-engine celery-worker prometheus grafana"
