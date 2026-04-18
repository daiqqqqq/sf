# App Node Deployment

这个目录用于在 `192.168.110.117` 上直接部署应用服务器节点。

## 推荐顺序

1. 将仓库放到目标目录，例如 `/opt/rag-platform/app`
2. 复制环境文件：

```bash
cd /opt/rag-platform/app/deploy/two-server/app-node
cp .env.example .env
```

3. 修改 `.env` 中的管理员密码、JWT、内部 token、对象存储密码
4. 运行主机初始化：

```bash
sudo ./bootstrap_host.sh
```

5. 执行 preflight：

```bash
sudo ./preflight.sh
```

6. 部署：

```bash
sudo ./deploy.sh
```

7. 如需开机自启：

```bash
sudo systemctl start rag-platform
sudo systemctl status rag-platform
```

## 常用命令

```bash
docker compose --env-file .env -f docker-compose.yml ps
docker compose --env-file .env -f docker-compose.yml logs -f --tail=100 nginx platform-api rag-engine celery-worker
docker compose --env-file .env -f docker-compose.yml restart platform-api rag-engine celery-worker
```

