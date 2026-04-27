import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import gpu
from app.api.dependencies import get_current_user
from app.core.config import Settings
from app.core.web import install_common_handlers
from app.db.session import get_db_session
from app.models.entities import AdminUser
from app.schemas.api import GpuDeviceRead, GpuOverviewResponse, GpuServiceStatusRead
from app.services.gpu_service import GpuMonitorService, PrometheusQueryError


def build_test_app() -> FastAPI:
    app = FastAPI()
    install_common_handlers(app, service_name="platform-api")
    app.include_router(gpu.router)

    def override_db_session():
        yield object()

    app.dependency_overrides[get_db_session] = override_db_session
    return app


def sample_overview() -> GpuOverviewResponse:
    return GpuOverviewResponse(
        node_host="192.168.110.241",
        node_status="healthy",
        exporter_status="healthy",
        prometheus_status="healthy",
        sampled_at=None,
        gpu_count=1,
        total_memory_mb=24576.0,
        used_memory_mb=8192.0,
        average_utilization_percent=52.5,
        max_temperature_celsius=67.0,
        total_power_watts=220.0,
        grafana_url="http://192.168.110.117:3000/d/rag-platform-gpu",
        warnings=[],
        devices=[
            GpuDeviceRead(
                id="0",
                label="GPU 0",
                uuid="GPU-1234",
                model_name="NVIDIA L40S",
                status="healthy",
                utilization_percent=52.5,
                memory_used_mb=8192.0,
                memory_total_mb=24576.0,
                memory_utilization_percent=33.3,
                temperature_celsius=67.0,
                power_watts=220.0,
            )
        ],
        model_services=[
            GpuServiceStatusRead(
                name="ollama",
                base_url="http://192.168.110.241:11434/api/tags",
                status="healthy",
                response_ms=21,
                detail="reachable",
            )
        ],
    )


def make_user(role: str) -> AdminUser:
    return AdminUser(
        id=1,
        username=f"{role}-user",
        password_hash="not-used",
        is_active=True,
        is_superuser=role == "superadmin",
        role=role,
    )


def test_gpu_overview_requires_auth(monkeypatch) -> None:
    app = build_test_app()

    async def fake_overview(_: GpuMonitorService) -> GpuOverviewResponse:
        return sample_overview()

    monkeypatch.setattr(GpuMonitorService, "build_overview", fake_overview)

    client = TestClient(app)
    response = client.get("/api/gpu/overview")
    assert response.status_code == 401


def test_gpu_overview_allows_read_roles(monkeypatch) -> None:
    async def fake_overview(_: GpuMonitorService) -> GpuOverviewResponse:
        return sample_overview()

    monkeypatch.setattr(GpuMonitorService, "build_overview", fake_overview)

    for role in ("viewer", "operator", "superadmin"):
        app = build_test_app()
        app.dependency_overrides[get_current_user] = lambda role=role: make_user(role)
        client = TestClient(app)

        response = client.get("/api/gpu/overview")
        assert response.status_code == 200
        payload = response.json()
        assert payload["node_host"] == "192.168.110.241"
        assert payload["gpu_count"] == 1
        assert payload["prometheus_status"] == "healthy"


def test_gpu_service_degrades_when_prometheus_unavailable(monkeypatch) -> None:
    service = GpuMonitorService(Settings(_env_file=None))

    async def broken_collect():
        raise PrometheusQueryError("Prometheus query failed for `up`: timeout")

    async def fake_probe():
        return [
            GpuServiceStatusRead(
                name="ollama",
                base_url="http://192.168.110.241:11434/api/tags",
                status="healthy",
                response_ms=12,
                detail="reachable",
            )
        ]

    monkeypatch.setattr(service, "_collect_gpu_samples", broken_collect)
    monkeypatch.setattr(service, "_probe_model_services", fake_probe)

    overview = asyncio.run(service.build_overview())

    assert overview.prometheus_status == "degraded"
    assert overview.exporter_status == "unknown"
    assert overview.node_status == "degraded"
    assert overview.gpu_count == 0
    assert overview.warnings
