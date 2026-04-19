# 192.168.110.117 上线执行清单（可勾选）

适用目标：将本仓库部署为应用服务器节点。  
执行日期：`2026-04-18` 之后版本。  
默认目录：`/opt/rag-platform/app`。  
默认执行身份：`root`（脚本含系统级变更）。

---

## 0. 登录与会话准备

- [ ] 本地终端登录到 `117`

```bash
ssh root@192.168.110.117
```

- [ ] 设置本次执行变量（后续命令可直接复用）

```bash
export APP_ROOT=/opt/rag-platform/app
export DEPLOY_DIR=${APP_ROOT}/deploy/two-server/app-node
```

- [ ] 确认当前主机就是目标机

```bash
hostname -I
```

---

## 1. 代码到位

- [ ] 创建部署根目录

```bash
mkdir -p /opt/rag-platform
```

- [ ] 进入应用目录（已存在仓库可跳过 clone）

```bash
cd /opt/rag-platform
```

- [ ] 首次部署：克隆仓库（把 `<your-repo-url>` 替换为真实仓库地址）

```bash
git clone <your-repo-url> app
```

- [ ] 已有仓库：拉取最新代码

```bash
cd ${APP_ROOT}
git pull --ff-only
```

- [ ] 进入部署目录

```bash
cd ${DEPLOY_DIR}
```

---

## 2. 环境文件初始化

- [ ] 创建 `.env`

```bash
cp .env.example .env
```

- [ ] 生成安全密钥（写入当前 shell 变量）

```bash
export NEW_ADMIN_PASSWORD="Admin_$(date +%Y%m%d)_$(openssl rand -hex 4)"
export NEW_JWT_SECRET="$(openssl rand -hex 32)"
export NEW_INTERNAL_TOKEN="$(openssl rand -hex 24)"
export NEW_OPS_TOKEN="$(openssl rand -hex 24)"
export NEW_MINIO_SECRET="$(openssl rand -hex 16)"
```

- [ ] 写入关键安全参数

```bash
sed -i "s|^ADMIN_PASSWORD=.*|ADMIN_PASSWORD=${NEW_ADMIN_PASSWORD}|" .env
sed -i "s|^JWT_SECRET=.*|JWT_SECRET=${NEW_JWT_SECRET}|" .env
sed -i "s|^INTERNAL_SERVICE_TOKEN=.*|INTERNAL_SERVICE_TOKEN=${NEW_INTERNAL_TOKEN}|" .env
sed -i "s|^OPS_AGENT_TOKEN=.*|OPS_AGENT_TOKEN=${NEW_OPS_TOKEN}|" .env
sed -i "s|^MINIO_SECRET_KEY=.*|MINIO_SECRET_KEY=${NEW_MINIO_SECRET}|" .env
```

- [ ] 可选：按机器资源调整工作进程（默认值可用）

```bash
sed -i "s|^API_WORKERS=.*|API_WORKERS=2|" .env
sed -i "s|^RAG_WORKERS=.*|RAG_WORKERS=2|" .env
sed -i "s|^CELERY_WORKER_CONCURRENCY=.*|CELERY_WORKER_CONCURRENCY=2|" .env
```

- [ ] 确认模型服务器地址已正确指向 `192.168.110.241`

```bash
grep -E "^(OLLAMA_BASE_URL|VLLM_QWEN27_BASE_URL|VLLM_QWEN35_BASE_URL)=" .env
```

- [ ] 记录管理员密码到安全位置（本命令仅用于屏幕确认）

```bash
echo "${NEW_ADMIN_PASSWORD}"
```
admin password ： admin123
---

## 3. 主机初始化（Docker、sysctl、目录、自启模板）

- [ ] 执行主机初始化脚本

```bash
cd ${DEPLOY_DIR}
chmod +x bootstrap_host.sh preflight.sh deploy.sh
./bootstrap_host.sh
```

- [ ] 验证 Docker / Compose 可用

```bash
docker --version
docker compose version
```

- [ ] 验证系统参数生效（Elasticsearch 关键）

```bash
sysctl vm.max_map_count
```

---

## 4. 部署前预检

- [ ] 运行预检（会检查：Compose 配置、资源、端口占用、到 `241` 连通性）

```bash
cd ${DEPLOY_DIR}
./preflight.sh
```

- [ ] 若预检报端口冲突，先定位占用进程

```bash
ss -ltnp | grep -E ":80|:5432|:6379|:9092|:9000|:9200|:19530|:9998"
```

---

## 5. 正式部署

- [ ] 启动全栈容器

```bash
cd ${DEPLOY_DIR}
./deploy.sh
```

- [ ] 查看容器状态（应全部为 `Up`，`minio-init` 为一次性 `Exited (0)`）

```bash
docker compose --env-file .env -f docker-compose.yml ps
```

- [ ] 观察核心服务日志（建议至少观察 2-3 分钟）

```bash
docker compose --env-file .env -f docker-compose.yml logs -f --tail=100 nginx platform-api rag-engine celery-worker
```

---

## 6. 上线验收（最小可用）

- [ ] 检查网关健康

```bash
curl -fsS http://127.0.0.1/healthz
```

- [ ] 检查 API 健康

```bash
curl -fsS http://127.0.0.1/api/system/health -o /dev/null || true
curl -fsS http://127.0.0.1:8000/readyz
```

- [ ] 检查 RAG 引擎就绪

```bash
curl -fsS http://127.0.0.1:8100/readyz
```

- [ ] 检查 Ops Agent 健康

```bash
curl -fsS http://127.0.0.1:8200/healthz
```

- [ ] 浏览器验收（在内网访问）

```bash
echo "Open: http://192.168.110.117/"
```

- [ ] 登录验证（账号：`admin`，密码：上面生成的 `NEW_ADMIN_PASSWORD`）

```bash
echo "username=admin"
```

---

## 7. 开机自启

- [ ] 启动并检查 systemd 服务

```bash
systemctl start rag-platform
systemctl status rag-platform --no-pager
```

- [ ] 验证开机自启状态

```bash
systemctl is-enabled rag-platform
```

---

## 8. 常见运维命令

- [ ] 查看所有容器

```bash
cd ${DEPLOY_DIR}
docker compose --env-file .env -f docker-compose.yml ps
```

- [ ] 重启核心业务服务

```bash
docker compose --env-file .env -f docker-compose.yml restart platform-api rag-engine celery-worker
```

- [ ] 查看某个服务日志（示例：platform-api）

```bash
docker compose --env-file .env -f docker-compose.yml logs -f --tail=200 platform-api
```

- [ ] 停止整栈

```bash
docker compose --env-file .env -f docker-compose.yml down
```

- [ ] 重新拉起整栈

```bash
docker compose --env-file .env -f docker-compose.yml up -d --remove-orphans
```

---

## 9. 回滚与恢复（紧急）

- [ ] 先保留现场日志

```bash
mkdir -p /opt/rag-platform/backups/logs-$(date +%Y%m%d-%H%M%S)
docker compose --env-file .env -f docker-compose.yml logs --no-color > /opt/rag-platform/backups/logs-$(date +%Y%m%d-%H%M%S)/stack.log
```

- [ ] 回滚到上一版代码（仅在你使用 git 管理版本时）

```bash
cd ${APP_ROOT}
git log --oneline -n 5
git checkout <previous-commit-sha>
```

- [ ] 按回滚版本重新部署

```bash
cd ${DEPLOY_DIR}
./deploy.sh
```

---

## 10. 交接记录（上线完成后填写）

- [ ] 上线开始时间：`____`
- [ ] 上线完成时间：`____`
- [ ] 执行人：`____`
- [ ] 核心容器状态截图已留档：`是/否`
- [ ] Dashboard 登录验证完成：`是/否`
- [ ] 模型连通性检查通过：`是/否`
- [ ] 遗留问题：`____`

