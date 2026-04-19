#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

PERSIST_ROOT="${PERSIST_ROOT:-/opt/rag-platform}"
APP_ROOT="${APP_ROOT:-${REPO_ROOT}}"
SERVICE_NAME="${SERVICE_NAME:-rag-platform}"
ENV_FILE="${ENV_FILE:-${SCRIPT_DIR}/.env}"
SYSTEMD_UNIT_PATH="/etc/systemd/system/${SERVICE_NAME}.service"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "请使用 root 执行本脚本。" >&2
  exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
  if command -v apt-get >/dev/null 2>&1; then
    apt-get update && apt-get install -y curl
  elif command -v dnf >/dev/null 2>&1; then
    dnf install -y curl
  elif command -v yum >/dev/null 2>&1; then
    yum install -y curl
  else
    echo "缺少 curl，且无法自动安装，请先手动安装 curl。" >&2
    exit 1
  fi
fi

mkdir -p \
  "${PERSIST_ROOT}/minio" \
  "${PERSIST_ROOT}/postgres" \
  "${PERSIST_ROOT}/redis" \
  "${PERSIST_ROOT}/kafka" \
  "${PERSIST_ROOT}/milvus/data" \
  "${PERSIST_ROOT}/milvus/etcd" \
  "${PERSIST_ROOT}/elasticsearch" \
  "${PERSIST_ROOT}/logs" \
  "${PERSIST_ROOT}/data" \
  "${PERSIST_ROOT}/backups"

# Align host volume ownership with container runtime users so services can
# initialize state under bind mounts on first boot.
chown -R 1001:1001 "${PERSIST_ROOT}/kafka"
chown -R 1000:1000 "${PERSIST_ROOT}/elasticsearch"
chmod -R u+rwX,g+rwX "${PERSIST_ROOT}/kafka" "${PERSIST_ROOT}/elasticsearch"

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
  echo "Docker Compose plugin 未安装，请确认 Docker Engine 安装完整。" >&2
  exit 1
fi

if [[ ! -f "${ENV_FILE}" ]]; then
  cp "${SCRIPT_DIR}/.env.example" "${ENV_FILE}"
  echo "已生成 ${ENV_FILE}，请先编辑其中的密码、Token 和内网地址。"
fi

sed "s|__APP_ROOT__|${APP_ROOT}|g; s|__ENV_FILE__|${ENV_FILE}|g; s|__SERVICE_NAME__|${SERVICE_NAME}|g" \
  "${SCRIPT_DIR}/rag-platform.service.template" >"${SYSTEMD_UNIT_PATH}"

chmod 644 "${SYSTEMD_UNIT_PATH}"
chmod +x "${SCRIPT_DIR}/deploy.sh" "${SCRIPT_DIR}/preflight.sh"

systemctl daemon-reload
systemctl enable "${SERVICE_NAME}" >/dev/null 2>&1 || true

echo "主机初始化完成。"
echo "下一步："
echo "1. 编辑 ${ENV_FILE}"
echo "2. 运行 ${SCRIPT_DIR}/preflight.sh"
echo "3. 运行 ${SCRIPT_DIR}/deploy.sh"
echo "4. 如需开机自启，执行 systemctl start ${SERVICE_NAME}"
