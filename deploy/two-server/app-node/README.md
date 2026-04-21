# App Node Deployment

这个目录用于在 `192.168.110.117` 上部署应用服务器节点。

## 推荐步骤

1. 把仓库放到目标目录，例如 `/opt/rag-platform/app`
2. 复制环境文件

```bash
cd /opt/rag-platform/app/deploy/two-server/app-node
cp .env.example .env
```

3. 修改 `.env`
4. 初始化主机

```bash
sudo ./bootstrap_host.sh
```

5. 运行预检

```bash
sudo ./preflight.sh
```

6. 启动整套服务

```bash
sudo ./deploy.sh
```

## 关键环境变量

- `JWT_SECRET`、`INTERNAL_SERVICE_TOKEN`、`OPS_AGENT_TOKEN`：必须替换成随机值
- `MINIO_SECRET_KEY`、`POSTGRES_PASSWORD`、`GRAFANA_ADMIN_PASSWORD`：必须替换成正式密码
- `OLLAMA_BASE_URL`、`VLLM_QWEN27_BASE_URL`、`VLLM_QWEN35_BASE_URL`：保持指向 GPU 服务器
- `BACKUP_ROOT`、`BACKUP_WINDOW_CRON`：控制本机备份路径和定时窗口

## 常用命令

```bash
docker compose --env-file .env -f docker-compose.yml ps
docker compose --env-file .env -f docker-compose.yml logs -f --tail=100 nginx platform-api rag-engine celery-worker prometheus grafana
docker compose --env-file .env -f docker-compose.yml restart platform-api rag-engine celery-worker
./backup_stack.sh
./restore_stack.sh 20260421-020000
```

## systemd

`bootstrap_host.sh` 会安装两个 unit：

- `rag-platform.service`：控制整套 Compose 堆栈
- `rag-platform-backup.timer`：按 `.env` 中的备份窗口定时执行 `backup_stack.sh`
