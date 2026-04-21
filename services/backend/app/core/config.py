from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    app_name: str = "Dual Server RAG Platform"
    api_prefix: str = "/api"
    data_root: Path = Field(default=Path("/workspace/data"), validation_alias="APP_DATA_ROOT")
    logs_root: Path = Field(default=Path("/workspace/logs"))
    startup_timeout_seconds: int = 180
    startup_poll_interval_seconds: int = 2
    health_snapshot_keep_per_service: int = 20
    max_upload_bytes: int = 268435456
    api_workers: int = 2
    rag_workers: int = 2
    celery_worker_concurrency: int = 2
    storage_local_fallback_enabled: bool = False

    database_url: str = "sqlite:///./data/local.db"
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"
    task_execution_mode: str = "eager"

    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_topic_ingest: str = "rag-ingest"
    kafka_topic_audit: str = "rag-audit"

    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin123"
    minio_bucket: str = "rag-documents"
    minio_secure: bool = False

    elasticsearch_url: str = "http://localhost:9200"
    elasticsearch_index: str = "rag-documents"
    elasticsearch_candidate_count: int = 12

    milvus_uri: str = "http://localhost:19530"
    milvus_collection: str = "rag_chunks"
    milvus_token: str = ""
    milvus_candidate_count: int = 12

    tika_url: str = "http://localhost:9998"
    rag_engine_url: str = "http://localhost:8100"
    reranker_url: str = "http://localhost:8300"
    ops_agent_url: str = "http://localhost:8200"

    ollama_base_url: str = "http://192.168.110.241:11434"
    ollama_embedding_model: str = "qwen3-embedding:latest"

    vllm_qwen27_base_url: str = "http://192.168.110.241:12434/v1"
    vllm_qwen27_api_key: str = "qwen-241-12434"
    vllm_qwen27_model: str = "qwen3.5-27b-int8-128k"

    vllm_qwen35_base_url: str = "http://192.168.110.241:13434/v1"
    vllm_qwen35_api_key: str = "qwen-241-13434"
    vllm_qwen35_model: str = "qwen3.5-35b-a3b-int4-256k"

    admin_username: str = "admin"
    admin_password: str = "ChangeMeNow_123"
    jwt_secret: str = "please-change-this"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_minutes: int = 60 * 24 * 7

    internal_service_token: str = "internal-token"
    ops_agent_token: str = "ops-agent-token"
    docker_allowed_services: str = (
        "nginx,dashboard-web,platform-api,rag-engine,reranker,celery-worker,"
        "celery-beat,redis,kafka,minio,postgres,elasticsearch,milvus,tika,"
        "prometheus,grafana,node-exporter,cadvisor,postgres-exporter,redis-exporter"
    )
    docker_compose_file: str = "/workspace/deploy/two-server/app-node/docker-compose.yml"

    reranker_model_name: str = "BAAI/bge-reranker-v2-m3"
    haystack_candidate_multiplier: int = 3
    rrf_k: int = 60

    prometheus_port: int = 9090
    grafana_port: int = 3000
    backup_root: Path = Field(default=Path("/opt/rag-platform/backups"))
    backup_retention_daily: int = 7
    backup_retention_weekly: int = 4
    backup_window_cron: str = "0 2 * * *"
    backup_status_file: Path = Field(default=Path("/opt/rag-platform/backups/last_backup.json"))

    @property
    def allowed_service_names(self) -> list[str]:
        return [item.strip() for item in self.docker_allowed_services.split(",") if item.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.data_root.mkdir(parents=True, exist_ok=True)
    settings.logs_root.mkdir(parents=True, exist_ok=True)
    settings.backup_root.mkdir(parents=True, exist_ok=True)
    settings.backup_status_file.parent.mkdir(parents=True, exist_ok=True)
    return settings
