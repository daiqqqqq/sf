from __future__ import annotations

from datetime import UTC, datetime
import inspect
from time import perf_counter
from typing import Any, Callable

import httpx
import redis
from sqlalchemy import delete, desc, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import ServiceHealthSnapshot

try:
    from kafka import KafkaAdminClient
except Exception:  # pragma: no cover - optional dependency behavior
    KafkaAdminClient = None  # type: ignore[assignment]

try:
    from minio import Minio
except Exception:  # pragma: no cover - optional dependency behavior
    Minio = None  # type: ignore[assignment]

try:
    from pymilvus import connections, utility
except Exception:  # pragma: no cover - optional dependency behavior
    connections = utility = None  # type: ignore[assignment]


class HealthService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()

    async def probe_all(self) -> list[ServiceHealthSnapshot]:
        checks: list[tuple[str, str, str, Callable[[], Any]]] = [
            ("postgres", "infra", self.settings.database_url, self._probe_postgres),
            ("redis", "infra", self.settings.redis_url, self._probe_redis),
            ("kafka", "infra", self.settings.kafka_bootstrap_servers, self._probe_kafka),
            ("minio", "infra", self.settings.minio_endpoint, self._probe_minio),
            ("elasticsearch", "infra", self.settings.elasticsearch_url, self._probe_elasticsearch),
            ("milvus", "infra", self.settings.milvus_uri, self._probe_milvus),
            ("ollama", "embedding", f"{self.settings.ollama_base_url}/api/tags", lambda: self._probe_http(f"{self.settings.ollama_base_url}/api/tags")),
            ("qwen27", "generation", f"{self.settings.vllm_qwen27_base_url}/models", lambda: self._probe_http(f"{self.settings.vllm_qwen27_base_url}/models", {"Authorization": f"Bearer {self.settings.vllm_qwen27_api_key}"})),
            ("qwen35", "generation", f"{self.settings.vllm_qwen35_base_url}/models", lambda: self._probe_http(f"{self.settings.vllm_qwen35_base_url}/models", {"Authorization": f"Bearer {self.settings.vllm_qwen35_api_key}"})),
            ("rag-engine", "internal", f"{self.settings.rag_engine_url}/healthz", lambda: self._probe_http(f"{self.settings.rag_engine_url}/healthz", {"X-Internal-Token": self.settings.internal_service_token})),
            ("reranker", "internal", f"{self.settings.reranker_url}/healthz", lambda: self._probe_http(f"{self.settings.reranker_url}/healthz", {"X-Internal-Token": self.settings.internal_service_token})),
            ("ops-agent", "internal", f"{self.settings.ops_agent_url}/healthz", lambda: self._probe_http(f"{self.settings.ops_agent_url}/healthz", {"X-Internal-Token": self.settings.ops_agent_token})),
        ]

        results: list[ServiceHealthSnapshot] = []
        for name, service_type, host, probe in checks:
            started = perf_counter()
            status_text = "healthy"
            try:
                probe_result = probe()
                details = await probe_result if inspect.isawaitable(probe_result) else probe_result
            except Exception as exc:
                status_text = "unhealthy"
                details = {"error": str(exc)}
            snapshot = ServiceHealthSnapshot(
                service_name=name,
                service_type=service_type,
                host=host,
                status=status_text,
                response_ms=int((perf_counter() - started) * 1000),
                details_json=details,
                checked_at=datetime.now(UTC),
            )
            self.db.add(snapshot)
            results.append(snapshot)
        self._trim_history()
        self.db.commit()
        return results

    async def _probe_http(self, url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return {
                "code": response.status_code,
                "body": response.json() if response.headers.get("content-type", "").startswith("application/json") else response.text[:200],
            }

    def _probe_postgres(self) -> dict[str, Any]:
        self.db.execute(text("SELECT 1"))
        return {"status": "ok"}

    def _probe_redis(self) -> dict[str, Any]:
        client = redis.from_url(self.settings.redis_url)
        return {"ping": client.ping()}

    def _probe_kafka(self) -> dict[str, Any]:
        if KafkaAdminClient is None:
            raise RuntimeError("Kafka client unavailable")
        client = KafkaAdminClient(bootstrap_servers=self.settings.kafka_bootstrap_servers, request_timeout_ms=3000)
        try:
            topics = sorted(client.list_topics())
            return {"topics": topics[:20]}
        finally:
            client.close()

    def _probe_minio(self) -> dict[str, Any]:
        if Minio is None:
            raise RuntimeError("MinIO client unavailable")
        client = Minio(
            self.settings.minio_endpoint,
            access_key=self.settings.minio_access_key,
            secret_key=self.settings.minio_secret_key,
            secure=self.settings.minio_secure,
        )
        buckets = [bucket.name for bucket in client.list_buckets()]
        return {"buckets": buckets}

    async def _probe_elasticsearch(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{self.settings.elasticsearch_url}/_cluster/health")
            response.raise_for_status()
            return response.json()

    def _probe_milvus(self) -> dict[str, Any]:
        if connections is None or utility is None:
            raise RuntimeError("Milvus client unavailable")
        alias = "health-check"
        connections.connect(alias=alias, uri=self.settings.milvus_uri, token=self.settings.milvus_token or None)
        try:
            collections = utility.list_collections(using=alias)
            return {"collections": collections}
        finally:
            connections.disconnect(alias)

    def _trim_history(self) -> None:
        keep = max(self.settings.health_snapshot_keep_per_service, 1)
        service_names = [
            service_name
            for service_name in self.db.scalars(select(ServiceHealthSnapshot.service_name).distinct())
        ]
        for service_name in service_names:
            expired_ids = list(
                self.db.scalars(
                    select(ServiceHealthSnapshot.id)
                    .where(ServiceHealthSnapshot.service_name == service_name)
                    .order_by(desc(ServiceHealthSnapshot.checked_at))
                    .offset(keep)
                )
            )
            if expired_ids:
                self.db.execute(delete(ServiceHealthSnapshot).where(ServiceHealthSnapshot.id.in_(expired_ids)))
