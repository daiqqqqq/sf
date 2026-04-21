from __future__ import annotations

from fastapi import Depends, FastAPI, Query

from app.api.dependencies import require_ops_token
from app.core.config import get_settings
from app.core.metrics import metrics_response
from app.core.web import install_common_handlers
from app.schemas.api import ContainerState, MessageResponse
from app.services.ops_service import OpsService

settings = get_settings()

app = FastAPI(
    title="Ops Agent",
    docs_url="/docs" if settings.app_env != "production" else None,
    redoc_url="/redoc" if settings.app_env != "production" else None,
    openapi_url="/openapi.json" if settings.app_env != "production" else None,
)
install_common_handlers(app, service_name="ops-agent")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/containers", response_model=list[ContainerState])
def list_containers(_: None = Depends(require_ops_token)) -> list[ContainerState]:
    return [ContainerState.model_validate(item) for item in OpsService().list_containers()]


@app.get("/containers/{service_name}/logs")
def get_logs(
    service_name: str,
    tail: int = Query(default=200, ge=10, le=1000),
    _: None = Depends(require_ops_token),
) -> dict[str, str]:
    return {"logs": OpsService().get_logs(service_name, tail)}


@app.post("/containers/{service_name}/actions/{action}", response_model=MessageResponse)
def container_action(
    service_name: str,
    action: str,
    _: None = Depends(require_ops_token),
) -> MessageResponse:
    result = OpsService().perform_action(service_name, action)
    return MessageResponse(message=result.get("message", "ok"))


@app.get("/metrics")
def metrics():
    return metrics_response()
