#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

PERSIST_ROOT="${PERSIST_ROOT:-/opt/rag-platform}"
APP_ROOT="${APP_ROOT:-${REPO_ROOT}}"
SERVICE_NAME="${SERVICE_NAME:-rag-platform}"
ENV_FILE="${ENV_FILE:-${SCRIPT_DIR}/.env}"
SYSTEMD_UNIT_PATH="/etc/systemd/system/${SERVICE_NAME}.service"
BACKUP_SERVICE_NAME="${SERVICE_NAME}-backup"
BACKUP_SERVICE_UNIT_PATH="/etc/systemd/system/${BACKUP_SERVICE_NAME}.service"
BACKUP_TIMER_UNIT_PATH="/etc/systemd/system/${BACKUP_SERVICE_NAME}.timer"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Please run this script as root." >&2
  exit 1
fi

install_dependency() {
  local package="$1"
  if command -v apt-get >/dev/null 2>&1; then
    apt-get update && apt-get install -y "${package}"
  elif command -v dnf >/dev/null 2>&1; then
    dnf install -y "${package}"
  elif command -v yum >/dev/null 2>&1; then
    yum install -y "${package}"
  else
    echo "Unable to install ${package} automatically. Please install it manually." >&2
    exit 1
  fi
}

selinux_relabel_path() {
  local target="$1"
  if ! command -v getenforce >/dev/null 2>&1; then
    return
  fi
  if [[ "$(getenforce)" == "Disabled" ]]; then
    return
  fi
  if command -v chcon >/dev/null 2>&1; then
    chcon -Rt container_file_t "${target}" 2>/dev/null || chcon -Rt svirt_sandbox_file_t "${target}" 2>/dev/null || true
  fi
}

command -v curl >/dev/null 2>&1 || install_dependency curl

mkdir -p \
  "${PERSIST_ROOT}/minio" \
  "${PERSIST_ROOT}/postgres" \
  "${PERSIST_ROOT}/redis" \
  "${PERSIST_ROOT}/kafka" \
  "${PERSIST_ROOT}/milvus/data" \
  "${PERSIST_ROOT}/milvus/etcd" \
  "${PERSIST_ROOT}/elasticsearch" \
  "${PERSIST_ROOT}/prometheus" \
  "${PERSIST_ROOT}/grafana" \
  "${PERSIST_ROOT}/logs" \
  "${PERSIST_ROOT}/data" \
  "${PERSIST_ROOT}/backups" \
  "${PERSIST_ROOT}/backups/elasticsearch-repository"

chown -R 1001:1001 "${PERSIST_ROOT}/kafka"
chown -R 1000:1000 "${PERSIST_ROOT}/elasticsearch"
chown -R 1000:1000 "${PERSIST_ROOT}/backups/elasticsearch-repository"
chown -R 472:472 "${PERSIST_ROOT}/grafana"
chmod -R u+rwX,g+rwX "${PERSIST_ROOT}/kafka" "${PERSIST_ROOT}/elasticsearch"
chmod -R u+rwX,g+rwX "${PERSIST_ROOT}/grafana"
chmod -R a+rX "${PERSIST_ROOT}/backups/elasticsearch-repository"

selinux_relabel_path "${PERSIST_ROOT}"

cat >/etc/sysctl.d/99-rag-platform.conf <<EOF
vm.max_map_count=262144
vm.overcommit_memory=1
fs.inotify.max_user_instances=512
EOF
sysctl --system >/dev/null

cat >/etc/security/limits.d/rag-platform.conf <<EOF
* soft nofile 65535
* hard nofile 65535
root soft nofile 65535
root hard nofile 65535
EOF

if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
fi

systemctl enable docker >/dev/null 2>&1 || true
systemctl start docker

if ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose plugin is missing. Please verify the Docker installation." >&2
  exit 1
fi

if [[ ! -f "${ENV_FILE}" ]]; then
  cp "${SCRIPT_DIR}/.env.example" "${ENV_FILE}"
  echo "Created ${ENV_FILE}. Update passwords, tokens, and network settings before deployment."
fi

backup_oncalendar_from_env() {
  local raw minute hour
  raw="$(grep -E '^BACKUP_WINDOW_CRON=' "${ENV_FILE}" | head -n1 | cut -d= -f2- || true)"
  minute="$(awk '{print $1}' <<<"${raw:-0 2 * * *}")"
  hour="$(awk '{print $2}' <<<"${raw:-0 2 * * *}")"
  if [[ "${minute}" =~ ^[0-9]+$ && "${hour}" =~ ^[0-9]+$ ]]; then
    printf '*-*-* %02d:%02d:00' "${hour}" "${minute}"
    return
  fi
  printf '*-*-* 02:00:00'
}

sed "s|__APP_ROOT__|${APP_ROOT}|g; s|__ENV_FILE__|${ENV_FILE}|g; s|__SERVICE_NAME__|${SERVICE_NAME}|g" \
  "${SCRIPT_DIR}/rag-platform.service.template" >"${SYSTEMD_UNIT_PATH}"
sed "s|__APP_ROOT__|${APP_ROOT}|g; s|__ENV_FILE__|${ENV_FILE}|g; s|__SERVICE_NAME__|${SERVICE_NAME}|g" \
  "${SCRIPT_DIR}/rag-platform-backup.service.template" >"${BACKUP_SERVICE_UNIT_PATH}"
sed "s|__SERVICE_NAME__|${SERVICE_NAME}|g; s|__BACKUP_ON_CALENDAR__|$(backup_oncalendar_from_env)|g" \
  "${SCRIPT_DIR}/rag-platform-backup.timer.template" >"${BACKUP_TIMER_UNIT_PATH}"

chmod 644 "${SYSTEMD_UNIT_PATH}" "${BACKUP_SERVICE_UNIT_PATH}" "${BACKUP_TIMER_UNIT_PATH}"
chmod +x "${SCRIPT_DIR}/deploy.sh" "${SCRIPT_DIR}/preflight.sh" "${SCRIPT_DIR}/backup_stack.sh" "${SCRIPT_DIR}/restore_stack.sh"

systemctl daemon-reload
systemctl enable "${SERVICE_NAME}" >/dev/null 2>&1 || true
systemctl enable "${BACKUP_SERVICE_NAME}.timer" >/dev/null 2>&1 || true

echo "Host bootstrap completed."
echo "Next steps:"
echo "1. Edit ${ENV_FILE}"
echo "2. Run ${SCRIPT_DIR}/preflight.sh"
echo "3. Run ${SCRIPT_DIR}/deploy.sh"
echo "4. Optional: systemctl start ${SERVICE_NAME}"
echo "5. Optional: systemctl start ${BACKUP_SERVICE_NAME}.timer"
