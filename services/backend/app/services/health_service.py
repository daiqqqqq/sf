from __future__ import annotations

from datetime import UTC, datetime
from time import perf_counter
from typing import Any

import httpx
from sqlalchemy import delete, desc, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import ServiceHealthSnapshot


class HealthService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()

    async def probe_all(self) -> list[ServiceHealthSnapshot]:
        checks = [
            ("ollama", "embedding", f"{self.settings.ollama_base_url}/api/tags", None),
            ("qwen27", "generation", f"{self.settings.vllm_qwen27_base_url}/models", {"Authorization": f"Bearer {self.settings.vllm_qwen27_api_key}"}),
            ("qwen35", "generation", f"{self.settings.vllm_qwen35_base_url}/models", {"Authorization": f"Bearer {self.settings.vllm_qwen35_api_key}"}),
            ("rag-engine", "internal", f"{self.settings.rag_engine_url}/healthz", {"X-Internal-Token": self.settings.internal_service_token}),
            ("reranker", "internal", f"{self.settings.reranker_url}/healthz", {"X-Internal-Token": self.settings.internal_service_token}),
            ("ops-agent", "internal", f"{self.settings.ops_agent_url}/healthz", {"X-Internal-Token": self.settings.ops_agent_token}),
        ]

        results: list[ServiceHealthSnapshot] = []
        async with httpx.AsyncClient(timeout=10.0) as client:
            for name, service_type, url, headers in checks:
                started = perf_counter()
                status_text = "healthy"
                details: dict[str, Any]
                try:
                    response = await client.get(url, headers=headers)
                    response.raise_for_status()
                    details = {"code": response.status_code, "body": response.json() if response.headers.get("content-type", "").startswith("application/json") else response.text[:200]}
                except Exception as exc:
                    status_text = "unhealthy"
                    details = {"error": str(exc)}
                response_ms = int((perf_counter() - started) * 1000)
                snapshot = ServiceHealthSnapshot(
                    service_name=name,
                    service_type=service_type,
                    host=url,
                    status=status_text,
                    response_ms=response_ms,
                    details_json=details,
                    checked_at=datetime.now(UTC),
                )
                self.db.add(snapshot)
                results.append(snapshot)
        self._trim_history()
        self.db.commit()
        return results

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
