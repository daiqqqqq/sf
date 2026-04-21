#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-${SCRIPT_DIR}/docker-compose.yml}"
ENV_FILE="${ENV_FILE:-${SCRIPT_DIR}/.env}"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing ${ENV_FILE}. Copy it from .env.example first." >&2
  exit 1
fi

set -a
source "${ENV_FILE}"
set +a

BACKUP_ROOT="${BACKUP_ROOT:-/opt/rag-platform/backups}"
BACKUP_STATUS_FILE="${BACKUP_STATUS_FILE:-${BACKUP_ROOT}/last_backup.json}"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
SNAPSHOT_DIR="${BACKUP_ROOT}/${TIMESTAMP}"
ES_SNAPSHOT_NAME="snapshot-${TIMESTAMP}"
PAUSE_SERVICES=(rag-engine celery-worker celery-beat)
PAUSED=0

mkdir -p "${SNAPSHOT_DIR}/postgres" "${SNAPSHOT_DIR}/minio" "${SNAPSHOT_DIR}/milvus" "${SNAPSHOT_DIR}/meta" "${BACKUP_ROOT}/elasticsearch-repository"

cleanup() {
  local rc=$?
  if [[ ${PAUSED} -eq 1 ]]; then
    docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" start "${PAUSE_SERVICES[@]}" >/dev/null 2>&1 || true
  fi
  exit ${rc}
}
trap cleanup EXIT

echo "[backup] creating PostgreSQL dump"
docker exec rag-postgres pg_dump -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -Fc > "${SNAPSHOT_DIR}/postgres/postgres.dump"

echo "[backup] mirroring MinIO bucket ${MINIO_BUCKET}"
docker run --rm \
  --network container:rag-minio \
  -v "${SNAPSHOT_DIR}/minio:/backup" \
  minio/mc:RELEASE.2025-02-15T10-37-16Z \
  /bin/sh -c "mc alias set local http://127.0.0.1:9000 '${MINIO_ACCESS_KEY}' '${MINIO_SECRET_KEY}' >/dev/null && mc mirror --overwrite 'local/${MINIO_BUCKET}' '/backup/${MINIO_BUCKET}'"

echo "[backup] pausing write-heavy services for Milvus/etcd archive"
docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" stop "${PAUSE_SERVICES[@]}"
PAUSED=1
tar -czf "${SNAPSHOT_DIR}/milvus/milvus-data.tgz" -C "${PERSIST_ROOT}/milvus" data etcd
docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" start "${PAUSE_SERVICES[@]}"
PAUSED=0

echo "[backup] creating Elasticsearch snapshot ${ES_SNAPSHOT_NAME}"
docker run --rm \
  --network container:rag-elasticsearch \
  curlimages/curl:8.10.1 \
  -sS -XPUT "http://127.0.0.1:9200/_snapshot/local_fs" \
  -H "Content-Type: application/json" \
  -d '{"type":"fs","settings":{"location":"/opt/backups/es-repository","compress":true}}' >/dev/null
docker run --rm \
  --network container:rag-elasticsearch \
  curlimages/curl:8.10.1 \
  -sS -XPUT "http://127.0.0.1:9200/_snapshot/local_fs/${ES_SNAPSHOT_NAME}?wait_for_completion=true" \
  -H "Content-Type: application/json" \
  -d "{\"indices\":\"${ELASTICSEARCH_INDEX}\",\"include_global_state\":false}" > "${SNAPSHOT_DIR}/meta/elasticsearch_snapshot.json"

python - "${BACKUP_ROOT}" "${BACKUP_RETENTION_DAILY:-7}" "${BACKUP_RETENTION_WEEKLY:-4}" <<'PY'
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil
import sys

backup_root = Path(sys.argv[1])
keep_daily = int(sys.argv[2])
keep_weekly = int(sys.argv[3])

snapshots = []
for child in backup_root.iterdir():
    if not child.is_dir():
        continue
    try:
        ts = datetime.strptime(child.name, "%Y%m%d-%H%M%S")
    except ValueError:
        continue
    snapshots.append((ts, child))

snapshots.sort(reverse=True)
daily_keep = {child for _, child in snapshots[:keep_daily]}
weekly_keep = set()
seen_weeks: set[tuple[int, int]] = set()
for ts, child in snapshots:
    week = ts.isocalendar()[:2]
    if week in seen_weeks:
        continue
    weekly_keep.add(child)
    seen_weeks.add(week)
    if len(weekly_keep) >= keep_weekly:
        break

preserve = daily_keep | weekly_keep
for _, child in snapshots:
    if child not in preserve:
        shutil.rmtree(child, ignore_errors=True)
PY

python - "${BACKUP_STATUS_FILE}" "${TIMESTAMP}" "${ES_SNAPSHOT_NAME}" "${MINIO_BUCKET}" "${POSTGRES_DB}" <<'PY'
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import json
import sys

status_path = Path(sys.argv[1])
payload = {
    "status": "success",
    "snapshot": sys.argv[2],
    "elasticsearch_snapshot": sys.argv[3],
    "minio_bucket": sys.argv[4],
    "postgres_db": sys.argv[5],
    "last_success_ts": int(datetime.now(UTC).timestamp()),
    "updated_at": datetime.now(UTC).isoformat(),
}
status_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
PY

echo "[backup] completed snapshot ${TIMESTAMP}"
