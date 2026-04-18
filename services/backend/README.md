# Backend Services

这个目录承载四类服务：

- `platform-api`: 对外统一 API
- `rag-engine`: 索引、召回、融合与问答入口
- `ops-agent`: 受控 Docker 运维代理
- `reranker`: 重排服务，默认支持启发式回退

Celery worker 与 beat 也复用同一套代码和依赖。

## 生产启动方式

容器内不再直接调用 `uvicorn`/`celery` 命令，而是统一通过 `python -m app.run_service` 启动：

- 启动前等待关键依赖可用
- `platform-api` 和 `rag-engine` 使用 `gunicorn + uvicorn workers`
- `platform-api` 启动时自动初始化数据库和默认管理员/模型配置
- `celery-worker`、`celery-beat` 会等待 Redis、Kafka、RAG 引擎可用后再启动

