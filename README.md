# 双机 RAG 平台与统一 Dashboard

这个仓库提供一套面向双机部署的 RAG 平台：

- `192.168.110.117` 作为应用服务器，承载 `nginx`、`platform-api`、`rag-engine`、`celery`、`ops-agent`、`MinIO`、`Milvus`、`Elasticsearch`、监控栈和 Dashboard。
- `192.168.110.241` 作为 GPU 模型服务器，继续使用已部署的 `Ollama` embedding 和 `vLLM` 生成模型。
- Dashboard 提供统一入口，用于查看平台健康、管理知识库与文档、调试 RAG、观察模型连通性，以及对白名单容器执行运维动作。

## 目录结构

- [deploy/two-server/app-node/docker-compose.yml](/d:/study/1/sf/deploy/two-server/app-node/docker-compose.yml)：应用服务器的主编排文件
- [deploy/two-server/app-node/README.md](/d:/study/1/sf/deploy/two-server/app-node/README.md)：117 服务器部署说明
- [deploy/two-server/app-node/RUNBOOK_117.md](/d:/study/1/sf/deploy/two-server/app-node/RUNBOOK_117.md)：上线核对清单
- [services/backend](/d:/study/1/sf/services/backend)：Python 后端工程
- [dashboard](/d:/study/1/sf/dashboard)：React + Vite 管理台

## 当前能力

- 本地账号登录，支持 `superadmin`、`operator`、`viewer` 三角色
- 文档上传后走异步解析、切块、混合索引和任务跟踪
- `Elasticsearch + Milvus + RRF + reranker` 的混合召回链路
- `ops-agent` 控制应用服务器白名单容器，GPU 服务器只读监测
- `Prometheus + Grafana + exporters` 的监控栈
- 本机定时备份，覆盖 `Postgres`、`MinIO`、`Elasticsearch`、`Milvus/etcd`

## 在 117 上部署

推荐在应用服务器执行：

```bash
cd /opt/rag-platform/app/deploy/two-server/app-node
cp .env.example .env
sudo ./bootstrap_host.sh
sudo ./preflight.sh
sudo ./deploy.sh
```

首次部署后访问：

- Dashboard: `http://192.168.110.117/`
- Prometheus: `http://192.168.110.117:9090/`
- Grafana: `http://192.168.110.117:3000/`

## 预置模型接入

- Embedding: `http://192.168.110.241:11434`，默认模型 `qwen3-embedding:latest`
- vLLM 27B: `http://192.168.110.241:12434/v1`
- vLLM 35B: `http://192.168.110.241:13434/v1`

## 建议上线顺序

1. 完成 `.env` 中的密码、JWT、internal token、Grafana 密码和模型配置。
2. 运行 `preflight.sh` 检查主机资源和模型服务器连通性。
3. 运行 `deploy.sh` 拉起整套 Compose。
4. 观察 `nginx`、`platform-api`、`rag-engine`、`celery-worker`、`prometheus`、`grafana` 日志。
5. 验证创建知识库、上传文档、完成索引、执行 RAG 查询和备份脚本。
