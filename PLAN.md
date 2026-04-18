# 双机 RAG 平台与统一管理 Dashboard 实施计划

## Summary
- 在 `192.168.110.117` 上落一套单机容器化应用平台，承载图中上半部分全部能力：`NGINX`、`FastAPI` 编排层、`Celery`、`Kafka`、`Redis`、`MinIO`、`Milvus`、`Elasticsearch`、文档解析链路、`RAG` 引擎、`reranker` 和 Dashboard。
- `192.168.110.241` 保持现状，不改动已部署模型；应用侧通过网络接入三个已验证接口：`Ollama@11434`、`vLLM qwen3.5-27b@12434/v1`、`vLLM qwen3.5-35b@13434/v1`。
- Dashboard 采用“应用服务器全管、GPU 服务器只读”的边界：`117` 上容器支持启停/重启/查看日志，`241` 上仅展示模型健康、配置和连通性。
- 技术栈固定为 `FastAPI + React/Vite + Nginx + Celery`；所有自研服务统一使用 Python，前端为独立 SPA，统一经 Nginx 暴露。
- 部署产物按三块组织：`deploy/two-server/app-node/` 放 Compose 与网关配置，`services/backend/` 放 API/RAG/Worker/Ops Agent，`dashboard/` 放前端。

## Key Changes
- 在应用服务器编排这些容器：`nginx`、`dashboard-web`、`platform-api`、`rag-engine`、`celery-worker`、`celery-beat`、`ops-agent`、`postgres`、`redis`、`kafka`（KRaft 单节点）、`minio`、`etcd`、`milvus`、`elasticsearch`、`tika`、`reranker`。
- `Postgres` 作为平台元数据存储补充到方案中，保存管理员账号、知识库、文档、任务、模型配置、审计记录；`etcd` 作为 `Milvus` 必需依赖补充到方案中。
- `Redis` 同时承担缓存与 `Celery` broker/result backend；`Kafka` 不承担 Celery broker，而是承担文档摄取、索引状态、审计流等事件总线，避免 `Celery + Kafka` 的不稳定组合。
- 文档解析能力按“一个逻辑模块、两类实现”落地：`tika` 负责 Office/PDF/通用文本抽取，自研 parser/worker 镜像内集成 `pypdf`、`python-docx`、Markdown 解析和 `PaddleOCR` 中文 OCR。
- `RAG` 引擎负责分块、召回、融合、重排和答案组装；检索走 `Milvus + Elasticsearch` 混合召回，重排默认使用应用侧 CPU 容器运行的 `BAAI/bge-reranker-v2-m3`。
- 嵌入模型默认接 `http://192.168.110.241:11434` 的 `qwen3-embedding:latest`；保留 provider 配置层，后续可无代码切换到图中的 `BGE-large-zh-v1.5-INT8` 风格服务。
- 生成模型默认预置两个 provider：`qwen3.5-27b-int8-128k` 作为常规问答模型，`qwen3.5-35b-a3b-int4-256k` 作为长上下文/复杂任务模型；两者都按 OpenAI-compatible 接口接入。
- Nginx 作为唯一入口，路由 `/` 到 Dashboard，路由 `/api` 到 `platform-api`；内部服务全部只在 Docker 网络暴露，不直接对外开端口。
- Dashboard 页面固定为：登录页、总览页、容器与服务页、知识库页、文档与任务页、模型连接页、RAG 调试页、系统设置页、审计日志页。
- 容器运维能力通过独立 `ops-agent` 实现，而不是把 Docker Socket 直接挂进主 API；`ops-agent` 是唯一持有 Docker 权限的服务，只允许白名单动作：查看状态、查看日志、启停、重启、重新创建指定 Compose 服务。
- `241` 的统一管理只做只读监测：轮询 `/api/tags` 和 `/v1/models`，展示模型名、上下文长度、接口可用性和最近失败信息，不做远程 Docker 控制。
- 核心数据流固定为：上传文档到 `MinIO`，写元数据到 `Postgres`，投递 `Celery` 任务并写 `Kafka` 事件，解析后写入 `Milvus` 和 `Elasticsearch`，查询时做混合召回和 rerank，必要时调用远端大模型生成答案。

## Public APIs / Interfaces
- 对外后台 API 固定分组为：`/api/auth/*`、`/api/system/*`、`/api/containers/*`、`/api/kb/*`、`/api/documents/*`、`/api/jobs/*`、`/api/models/*`、`/api/rag/*`、`/api/audit/*`。
- 内部服务接口固定为：`rag-engine` 提供索引与检索能力，`ops-agent` 提供受控容器操作，二者都只接受内网服务间调用并使用独立内部 token。
- 需要定义并持久化的核心实体为：`AdminUser`、`KnowledgeBase`、`Document`、`ChunkIndexTask`、`IngestJob`、`ModelProvider`、`ServiceHealthSnapshot`、`ContainerActionAudit`。
- 登录方式固定为本地账号体系：初始 `admin` 账号通过环境变量注入，应用签发 JWT access/refresh token，后续如需 LDAP/OAuth2 再扩展，不在本次实现里预埋复杂身份流。

## Test Plan
- 验证 `117` 上所有容器可一次性拉起，卷目录创建正确，服务重启后 `MinIO`、`Postgres`、`Milvus`、`Elasticsearch` 数据不丢失。
- 验证 Dashboard 登录、退出、过期刷新、未登录拦截和管理员权限边界。
- 验证容器管理链路可对白名单容器执行查看状态、看日志、重启、停止、启动和重建，并写入审计记录。
- 验证 `241` 三个模型接口的连通性探测、模型清单读取和异常告警展示。
- 验证四类文档摄取路径：`PDF`、`DOCX`、`Markdown`、扫描件图片/PDF；要求都能形成文档记录、任务记录、索引记录和失败重试。
- 验证混合检索链路：同一问题可同时命中 `Elasticsearch` 与 `Milvus`，重排后返回稳定排序，并能切换两个不同的生成模型完成问答。
- 验证缓存与异步链路：重复查询命中 `Redis`，长任务通过 `Celery` 异步执行，`Kafka` 可追踪摄取事件流。
- 验证故障场景：远端模型不可达、`MinIO` 暂停、`Elasticsearch` 不健康、OCR 失败、单个文档解析异常；要求平台能告警、标记失败状态，并支持人工重试。
- 验证端到端验收流程：创建知识库、上传文档、完成索引、执行搜索调试、切换模型、查看任务与日志、重启应用侧服务后再次查询成功。

## Assumptions
- 应用服务器 `192.168.110.117` 视为“高规格、全新 Linux 主机”，按从零安装 `Docker Engine`、`Docker Compose`、目录结构和开机自启来规划。
- 所有持久化卷默认落在 `/opt/rag-platform/`，至少拆分为 `minio`、`postgres`、`redis`、`kafka`、`milvus`、`elasticsearch`、`logs` 七类目录。
- 部署边界为内网访问，v1 不做公网暴露和正式 HTTPS 证书；如后续需要外网访问，再单独补 TLS、WAF、密码策略和二次认证。
- `Elasticsearch`、`Milvus`、`Kafka` 都按单节点生产内网场景配置，不做高可用集群；本次目标是稳定可用和统一管理，不是多节点容灾。
- 图中“开 RDMA”不纳入 v1 实施，当前按现有 TCP/IP 内网直连模型服务；后续若用户提供 RDMA/NCCL 网络基础，再评估高吞吐优化。
- 文档与检索默认面向中文场景，OCR 与解析参数优先中文文本质量；英文/多语作为兼容能力而非调优重点。
