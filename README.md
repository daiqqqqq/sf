# 双机 RAG 平台与统一管理 Dashboard

这个仓库实现了一套面向双机部署的 RAG 平台骨架：

- `192.168.110.117` 作为应用服务器，承载网关、平台 API、RAG 引擎、异步任务、对象存储、检索和 Dashboard。
- `192.168.110.241` 作为 GPU 模型服务器，继续使用已部署好的 `Ollama` 和 `vLLM` 模型服务。
- Dashboard 提供统一入口，用于服务观测、知识库管理、任务追踪、RAG 调试、模型连接检查和应用服务器容器运维。

## 目录结构

- [deploy/two-server/app-node/docker-compose.yml](/d:/study/1/sf/deploy/two-server/app-node/docker-compose.yml) 应用服务器主编排文件
- [services/backend](/d:/study/1/sf/services/backend) Python 后端工程，包含 `platform-api`、`rag-engine`、`ops-agent`、`reranker`、`celery`
- [dashboard](/d:/study/1/sf/dashboard) React + Vite 管理台
- [PLAN.md](/d:/study/1/sf/PLAN.md) 实施计划

## 核心能力

- 本地账号登录与 JWT 会话
- 知识库、文档、任务、审计、模型配置元数据管理
- 文档上传后通过 Celery 执行解析、切块、索引
- `Milvus + Elasticsearch` 混合检索的可扩展 RAG 流程
- 通过 `ops-agent` 对应用服务器白名单容器执行查看状态、日志、启停、重建
- 对 GPU 服务器模型接口执行只读健康探测

## 直接部署到 192.168.110.117

推荐直接在应用服务器仓库目录执行这一组命令：

```bash
cd /opt/rag-platform/app/deploy/two-server/app-node
cp .env.example .env
```

更适合在应用服务器上使用的顺序是：

1. `cp .env.example .env`
2. 修改 `.env` 里的管理员密码、JWT、内部 token、MinIO 密码和模型配置
3. `sudo ./bootstrap_host.sh`
4. `sudo ./preflight.sh`
5. `sudo ./deploy.sh`
6. 浏览器打开 `http://192.168.110.117/`

更详细的服务器侧说明见 [deploy/two-server/app-node/README.md](/d:/study/1/sf/deploy/two-server/app-node/README.md)。

## 本地开发说明

- 后端默认支持使用 SQLite 进行轻量开发，生产 Compose 会切换为 Postgres。
- 文档解析、Docker 运维、OCR、向量检索、重排都做了“可选依赖 + 优雅降级”，便于在不完整环境中先跑通骨架。
- 当前执行环境没有 `Node.js` 和 `Docker`，因此本仓库内已补齐前后端和部署代码，但前端构建与整套 Compose 拉起需要在目标 Linux 服务器或完整开发机上验证。

## 预设模型接入

- `Ollama Embedding`: `http://192.168.110.241:11434`，模型默认 `qwen3-embedding:latest`
- `vLLM 27B`: `http://192.168.110.241:12434/v1`
- `vLLM 35B`: `http://192.168.110.241:13434/v1`

## 建议的下一步

- 在 `117` 上执行 `bootstrap_host.sh`，自动完成 Docker、sysctl、目录、自启模板准备
- 先用 `preflight.sh` 验证模型服务器连通性和主机资源，再执行 `deploy.sh`
- 首次拉起后重点检查 `nginx`、`platform-api`、`rag-engine`、`celery-worker` 四个容器日志
- 完成首轮联调后，再根据业务量调整 `Elasticsearch`、`Milvus`、`Kafka` 资源和 `API_WORKERS`
