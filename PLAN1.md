# 双机 RAG 平台生产化补强计划

## Summary
- 按 4 个阶段实施：1. 编码/错误处理/存储收口。2. 真正接通 `embedding + Milvus + Elasticsearch` 混合召回。3. 完整运维栈与本机备份。4. 三角色权限。
- 现有 `celery-worker` Compose 健康检查保留并纳入告警与验收，不重复重写。
- 检索方案固定为：`Elasticsearch` 词法召回 + `Milvus` 向量召回 + `RRF` 融合 + `reranker` 精排；运行时移除 `Haystack` 作为生产主路径。
- 运维方案固定为：在应用服务器本机新增 `Prometheus + Grafana + node-exporter + cAdvisor + postgres-exporter + redis-exporter`，所有自研 HTTP 服务新增 `/metrics`。
- 备份方案固定为：落到 `/opt/rag-platform/backups` 的本机定时备份，保留 `7` 份日备份和 `4` 份周备份。
- 权限模型固定为：`superadmin`、`operator`、`viewer` 三角色；本次继续沿用本地账号体系，不接 LDAP/OAuth。

## Key Changes
- 生产收口
  - 统一清理后端和部署文档的 UTF-8/乱码问题，范围包含 `rag_service`、鉴权依赖、平台服务、部署 README/RUNBOOK 等所有用户可见文本。
  - 把泛化 `except Exception` 改成分层异常：外部依赖错误、业务校验错误、内部系统错误分别返回明确 HTTP 状态码，并写结构化日志。
  - `StorageService` 改为显式策略：生产环境默认禁止本地静默降级，`MinIO` 不可用时上传/读取直接失败；仅在开发环境且 `STORAGE_LOCAL_FALLBACK_ENABLED=true` 时允许本地回退。
  - 引入 `Alembic` 作为后续 schema 变更入口，容器启动前执行 `alembic upgrade head`，不再依赖新增字段靠 `create_all()` 隐式补齐。
- 混合召回与索引
  - `rag-engine /ingest` 改为完整索引流水线：文本清洗和切块后，为每个 chunk 生成稳定 `chunk_key=<kb_id>:<document_id>:<chunk_index>`，写 Postgres、调用 Ollama `/api/embed` 生成向量、写 Milvus、写 Elasticsearch。
  - 重建索引策略固定为“先清旧再写新”：文档重试或重新索引时，先按 `document_id` 删除旧的 `DocumentChunk`、Milvus 向量和 Elasticsearch 文档，再写入新数据，避免重复召回。
  - 查询链路固定为：查询向量化后分别取 `Elasticsearch lexical_top_n` 与 `Milvus vector_top_n`，按 `chunk_key` 做 `RRF` 融合，再调用 `reranker` 输出最终 `top_k`；`debug` 返回每阶段命中数量、每个 chunk 的来源、融合分和重排分。
  - 可用性策略固定为：查询时若 `ES` 或 `Milvus` 单边不可用，允许退化到另一边并在 `debug.warnings` 和日志中明确标记；若两边都不可用，`rag-engine` 直接返回 `503`。索引时只要 `Postgres/ES/Milvus` 任一写入失败，就将 `Document`、`IngestJob`、`ChunkIndexTask` 标为失败并做最佳努力回滚外部索引。
  - `probe_services_task` 与 readiness/overview 一并纳入 `elasticsearch`、`milvus`、`postgres`、`redis`、`minio`、`kafka` 状态；`run_service` 为 `rag-engine` 和 `celery-worker` 增加 `ES/Milvus/MinIO` 就绪等待。
- 监控与备份
  - Compose 新增 `prometheus`、`grafana`、`node-exporter`、`cadvisor`、`postgres-exporter`、`redis-exporter`；Grafana 预置面板覆盖 API 延迟、RAG 检索耗时、模型调用耗时、任务成功/失败、容器资源、主机资源、数据库/Redis 指标。
  - `platform-api`、`rag-engine`、`reranker`、`ops-agent` 提供 `/metrics`；`platform-api` 汇总输出关键业务指标：文档上传数、索引成功/失败数、检索请求数、检索降级数、模型请求耗时、最近一次备份状态。
  - 现有 `celery-worker` 健康检查继续保留，新增 Prometheus 告警规则和 Grafana 面板，告警条件至少覆盖：worker unhealthy、服务 health 连续失败、备份超时/缺失、ES/Milvus 不健康、GPU 模型不可达。
  - 备份实现固定为本机脚本加定时器：Postgres 用 `pg_dump`，MinIO 用 `mc mirror` 到本地备份目录，Elasticsearch 用 snapshot repository 写到本地目录，Milvus/etcd 在夜间备份窗口内短暂停写并归档持久化目录；恢复脚本支持按时间戳恢复单个或整套组件。
- 角色与权限
  - `AdminUser` 增加 `role` 字段并以枚举存储；保留 `is_active`，移除“登录即全权”的默认假设。
  - `superadmin` 拥有全部权限，并负责用户/角色/密码重置、系统设置、模型配置和容器运维。
  - `operator` 可查看系统/模型/审计，管理知识库和文档，重试任务，执行 RAG 调试，查看容器日志并对白名单容器执行现有运维动作，但不能管理用户、角色、JWT/internal token 或系统密钥。
  - `viewer` 只读查看系统、模型、知识库、文档列表、任务和审计；不能上传、重试、RAG 查询、容器动作或系统配置修改。
  - Dashboard 依据角色隐藏或禁用按钮；后端路由用角色依赖做硬约束，不只做前端控制。

## Public APIs / Interfaces / Types
- 新增环境变量与部署接口
  - `STORAGE_LOCAL_FALLBACK_ENABLED`、`PROMETHEUS_PORT`、`GRAFANA_PORT`、`BACKUP_ROOT`、`BACKUP_RETENTION_DAILY`、`BACKUP_RETENTION_WEEKLY`、`BACKUP_WINDOW_CRON`。
  - Compose 暴露 `Grafana` 管理端口和 `Prometheus` 采集端口，但默认只绑定应用服务器内网。
- 扩展 HTTP 接口
  - `platform-api`、`rag-engine`、`reranker`、`ops-agent` 新增 `GET /metrics`。
  - 新增用户管理接口：`GET /api/auth/users`、`POST /api/auth/users`、`PATCH /api/auth/users/{id}`、`POST /api/auth/users/{id}/reset-password`，仅 `superadmin` 可用。
  - `GET /api/system/overview` 扩展返回 `service_health` 与 `metrics` 的监控字段，包含索引成功/失败、检索降级、最近备份状态。
  - `POST /api/rag/query` 和 `/api/rag/debug` 的 `debug` 固定返回 `lexical_hits`、`vector_hits`、`fusion_scores`、`rerank_scores`、`warnings`、`used_backends`。
  - `POST /ingest` 的内部返回改为 `{chunks, indexed_backends}`，其中 `indexed_backends` 至少包含 `postgres`、`elasticsearch`、`milvus` 的写入数量。
- 数据模型调整
  - `AdminUser` 增加 `role`。
  - `DocumentChunk` 增加稳定 `chunk_key`，`metadata_json` 固定包含 `document_id`、`kb_id`、`chunk_index`、`es_doc_id`、`milvus_pk`。
  - `ChunkIndexTask` 增加 `details_json`，用于记录各后端索引状态和失败原因。
  - 不在 Postgres 持久化整段向量，只存主键和索引关联信息，向量数据只保存在 Milvus。

## Test Plan
- 编码与错误处理
  - 登录失败、无 token、用户不存在、知识库不存在、上传超限、外部依赖异常时，接口返回正常中文 UTF-8 文案和正确状态码。
  - 在 `APP_ENV=production` 下停掉 MinIO，上传和读取必须显式失败且不落本地；在开发模式显式开启回退时，本地回退才允许生效。
- 混合召回
  - 同一文档 ingest 后，Postgres、Elasticsearch、Milvus 都能查到对应 chunk；重试 ingest 时不会生成重复向量或重复 ES 文档。
  - 查询时能同时命中 lexical/vector 两条召回链，`debug` 能看到融合前后分数；单边后端异常时返回退化结果并有 warning；双边异常时返回 `503`。
  - 生成模型调用仍保持当前 `vLLM` 双 provider 逻辑，回答结果能引用最终 rerank 后的片段。
- 运维与监控
  - `celery-worker` 的现有 healthcheck 在 Compose、Prometheus、Grafana 三处状态一致；worker 停掉后能触发 unhealthy 和告警。
  - Prometheus 能抓到所有 `/metrics` 和 exporter 指标；Grafana 预置面板首次启动即可导入并展示数据。
  - `probe_services_task` 能记录 `ES/Milvus/MinIO/Kafka/GPU 模型` 的最新状态，`/api/system/overview` 正常展示。
- 备份与恢复
  - 备份脚本能生成按时间戳命名的目录，包含 Postgres dump、MinIO mirror、ES snapshot、Milvus/etcd 归档；超过保留数的备份会被清理。
  - 在干净环境中按恢复脚本恢复后，能登录、看到历史知识库/文档、重放检索并命中已恢复索引。
- 角色权限
  - `superadmin`、`operator`、`viewer` 三类账号分别验证页面可见性、接口授权、容器动作、文档上传、任务重试、RAG 查询和用户管理边界。
  - 前端按钮隐藏和后端权限拒绝必须同时成立，不能只靠前端控制。

## Assumptions / Defaults
- 这轮把“编码修复”范围从 `rag_service.py` 扩展到所有用户可见文本和部署文档，因为仓库当前仍存在多处乱码。
- 现有 `celery-worker` Compose healthcheck 视为已接入，本轮只做保留、校验、监控接线和文档补齐，不重复设计第二套机制。
- 混合召回的主路径直接替换当前 `haystack` 主检索；`haystack` 最多保留为开发期临时兜底，不再作为生产默认。
- 监控、备份和 Grafana/Prometheus 数据全部先部署在 `192.168.110.117` 本机，不依赖外部 observability 平台。
- 备份窗口默认设为夜间维护时段，Milvus/etcd 备份允许短暂停写；如果后续要求零停机备份，再单独扩展为远端归档或在线快照方案。
