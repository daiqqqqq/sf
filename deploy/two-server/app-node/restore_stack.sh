#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-${SCRIPT_DIR}/docker-compose.yml}"
ENV_FILE="${ENV_FILE:-${SCRIPT_DIR}/.env}"

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <snapshot-timestamp>" >&2
  exit 1
fi

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing ${ENV_FILE}. Copy it from .env.example first." >&2
  exit 1
fi

set -a
source "${ENV_FILE}"
set +a

SNAPSHOT_ID="$1"
BACKUP_ROOT="${BACKUP_ROOT:-/opt/rag-platform/backups}"
SNAPSHOT_DIR="${BACKUP_ROOT}/${SNAPSHOT_ID}"
ES_SNAPSHOT_NAME="snapshot-${SNAPSHOT_ID}"

if [[ ! -d "${SNAPSHOT_DIR}" ]]; then
  echo "Snapshot ${SNAPSHOT_DIR} does not exist." >&2
  exit 1
fi

echo "[restore] stopping application traffic"
docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" stop nginx dashboard-web platform-api rag-engine celery-worker celery-beat || true

echo "[restore] restoring PostgreSQL"
docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" up -d postgres
docker cp "${SNAPSHOT_DIR}/postgres/postgres.dump" rag-postgres:/tmp/postgres.dump
docker exec rag-postgres pg_restore -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" --clean --if-exists /tmp/postgres.dump
docker exec rag-postgres rm -f /tmp/postgres.dump

echo "[restore] restoring MinIO bucket"
docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" up -d minio minio-init
docker run --rm \
  --network container:rag-minio \
  -v "${SNAPSHOT_DIR}/minio:/backup" \
  minio/mc:RELEASE.2025-02-15T10-37-16Z \
  /bin/sh -c "mc alias set local http://127.0.0.1:9000 '${MINIO_ACCESS_KEY}' '${MINIO_SECRET_KEY}' >/dev/null && mc rm --recursive --force 'local/${MINIO_BUCKET}' >/dev/null 2>&1 || true && mc mb --ignore-existing 'local/${MINIO_BUCKET}' >/dev/null && mc mirror --overwrite '/backup/${MINIO_BUCKET}' 'local/${MINIO_BUCKET}'"

echo "[restore] restoring Elasticsearch snapshot"
docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" up -d elasticsearch
docker run --rm \
  --network container:rag-elasticsearch \
  curlimages/curl:8.10.1 \
  -sS -XPUT "http://127.0.0.1:9200/_snapshot/local_fs" \
  -H "Content-Type: application/json" \
  -d '{"type":"fs","settings":{"location":"/opt/backups/es-repository","compress":true}}' >/dev/null
docker run --rm \
  --network container:rag-elasticsearch \
  curlimages/curl:8.10.1 \
  -sS -XDELETE "http://127.0.0.1:9200/${ELASTICSEARCH_INDEX}" >/dev/null || true
docker run --rm \
  --network container:rag-elasticsearch \
  curlimages/curl:8.10.1 \
  -sS -XPOST "http://127.0.0.1:9200/_snapshot/local_fs/${ES_SNAPSHOT_NAME}/_restore?wait_for_completion=true" \
  -H "Content-Type: application/json" \
  -d "{\"indices\":\"${ELASTICSEARCH_INDEX}\",\"include_global_state\":false}" >/dev/null

echo "[restore] restoring Milvus/etcd archive"
docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" stop milvus etcd || true
rm -rf "${PERSIST_ROOT}/milvus/data"/* "${PERSIST_ROOT}/milvus/etcd"/*
tar -xzf "${SNAPSHOT_DIR}/milvus/milvus-data.tgz" -C "${PERSIST_ROOT}/milvus"
docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" up -d etcd milvus

echo "[restore] starting full stack"
docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" up -d --remove-orphans
echo "[restore] completed snapshot ${SNAPSHOT_ID}"
