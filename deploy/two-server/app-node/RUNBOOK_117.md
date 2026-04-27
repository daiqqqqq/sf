# 117 服务器上线清单

## 1. 基础准备

- [ ] 代码已同步到 `/opt/rag-platform/app`
- [ ] GPU 服务器 `192.168.110.241` 与应用服务器网络互通
- [ ] `.env` 已从 `.env.example` 复制并完成正式配置
- [ ] `JWT_SECRET`、`INTERNAL_SERVICE_TOKEN`、`OPS_AGENT_TOKEN` 已替换为随机值
- [ ] `POSTGRES_PASSWORD`、`MINIO_SECRET_KEY`、`GRAFANA_ADMIN_PASSWORD` 已替换

## 2. 主机初始化

- [ ] 执行 `sudo ./bootstrap_host.sh`
- [ ] 检查 `docker compose version` 正常
- [ ] 检查 `vm.max_map_count=262144`
- [ ] 检查 `/opt/rag-platform` 下的数据目录已创建

## 3. 部署前预检

- [ ] 执行 `sudo ./preflight.sh`
- [ ] 确认 Ollama 接口可达
- [ ] 确认两个 vLLM 接口可达
- [ ] 确认主机磁盘和内存满足单机部署要求

## 4. 启动服务

- [ ] 执行 `sudo ./deploy.sh`
- [ ] `db-migrate` 成功完成
- [ ] `platform-api`、`rag-engine`、`celery-worker`、`reranker`、`ops-agent` 为 healthy
- [ ] `prometheus`、`grafana` 正常启动

## 5. 核心验收

- [ ] 浏览器打开 `http://192.168.110.117/`
- [ ] 能用管理员账号登录
- [ ] `总览` 页面能看到健康状态和备份状态
- [ ] `模型连接` 页面能看到三个模型接口的探测结果
- [ ] 创建知识库成功
- [ ] 上传 PDF / DOCX / Markdown 文档成功
- [ ] 任务完成后，文档状态进入 `indexed`
- [ ] RAG 调试返回检索片段、调试信息和生成回答
- [ ] `容器与服务` 页面可以查看日志并执行白名单动作

## 6. 监控与备份

- [ ] Prometheus 可访问：`http://192.168.110.117:9090/`
- [ ] Grafana 可访问：`http://192.168.110.117:3000/`
- [ ] Grafana 预置面板已加载
- [ ] 执行一次 `./backup_stack.sh`
- [ ] `/opt/rag-platform/backups/last_backup.json` 已更新
- [ ] `systemctl status rag-platform-backup.timer` 正常

## 7. 故障排查命令

```bash
docker compose --env-file .env -f docker-compose.yml ps
docker compose --env-file .env -f docker-compose.yml logs -f --tail=100 platform-api rag-engine celery-worker prometheus grafana
docker compose --env-file .env -f docker-compose.yml restart platform-api rag-engine celery-worker
./backup_stack.sh
./restore_stack.sh <snapshot-timestamp>
```

## GPU Monitoring Acceptance

- [ ] GPU exporter is reachable: `curl http://192.168.110.241:9400/metrics`
- [ ] Prometheus target `gpu-exporter` is `UP`
- [ ] Grafana dashboard `RAG Platform GPU` is visible
- [ ] Platform page `/gpu` shows device load, memory, temperature, and power
