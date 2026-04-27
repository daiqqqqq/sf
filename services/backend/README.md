# Backend Services

后端目录承载以下服务：

- `platform-api`：对外统一 API，负责登录、知识库、文档、任务、模型健康、审计和容器操作代理
- `rag-engine`：负责切块、embedding、Milvus/Elasticsearch 索引、混合召回、RRF 融合和生成模型调用
- `ops-agent`：受控 Docker 运维代理，只允许对白名单服务执行动作
- `reranker`：重排服务，优先使用 `BAAI/bge-reranker-v2-m3`
- `celery-worker` / `celery-beat`：异步解析与健康探测任务

## 生产启动方式

容器统一通过 `python -m app.run_service` 启动：

- 启动前等待数据库、Redis、Kafka、MinIO、Elasticsearch、Milvus、RAG 引擎等依赖就绪
- `platform-api`、`rag-engine`、`ops-agent` 使用 `gunicorn + uvicorn workers`
- `db-migrate` 一次性执行 `alembic upgrade head`
- `celery-worker` 使用健康检查脚本 `python -m app.worker_healthcheck`

## 关键能力

- `Alembic` 迁移管理
- JWT 登录鉴权和三角色 RBAC
- 生产环境默认关闭对象存储本地静默降级
- `/metrics` 指标暴露，供 Prometheus 采集
- `Ollama /api/embed` 向量化
- `Milvus + Elasticsearch + RRF + reranker` 混合召回

## 本地开发

轻量开发可继续使用 SQLite，但完整功能建议在 Compose 环境验证：

```bash
python -m compileall app tests
```

## GPU Monitoring API

The platform API exposes a read-only GPU overview endpoint:

- `GET /api/gpu/overview`

It aggregates Prometheus GPU exporter metrics and model endpoint reachability into one response for the platform dashboard.

如果需要验证混合检索和监控栈，请在 Linux Docker 环境中按应用服务器 Compose 启动。
