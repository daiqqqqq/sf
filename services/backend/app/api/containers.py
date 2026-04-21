from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import require_roles
from app.core.config import get_settings
from app.core.errors import ExternalServiceAppError
from app.db.session import get_db_session
from app.models.entities import AdminUser, UserRole
from app.schemas.api import ContainerState, MessageResponse
from app.services.platform_service import PlatformService

router = APIRouter(prefix="/api/containers", tags=["containers"])


@router.get("", response_model=list[ContainerState])
async def list_containers(
    _: AdminUser = Depends(require_roles(UserRole.superadmin.value, UserRole.operator.value)),
) -> list[ContainerState]:
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(
                f"{settings.ops_agent_url}/containers",
                headers={"X-Internal-Token": settings.ops_agent_token},
            )
            response.raise_for_status()
    except Exception as exc:
        raise ExternalServiceAppError("运维代理不可用，无法读取容器状态。", service="ops-agent") from exc
    return [ContainerState.model_validate(item) for item in response.json()]


@router.get("/{service_name}/logs")
async def get_container_logs(
    service_name: str,
    tail: int = Query(default=200, ge=10, le=1000),
    _: AdminUser = Depends(require_roles(UserRole.superadmin.value, UserRole.operator.value)),
) -> dict[str, str]:
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(
                f"{settings.ops_agent_url}/containers/{service_name}/logs",
                params={"tail": tail},
                headers={"X-Internal-Token": settings.ops_agent_token},
            )
            response.raise_for_status()
    except Exception as exc:
        raise ExternalServiceAppError("运维代理不可用，无法读取容器日志。", service="ops-agent") from exc
    return response.json()


@router.post("/{service_name}/actions/{action}", response_model=MessageResponse)
async def container_action(
    service_name: str,
    action: str,
    current_user: AdminUser = Depends(require_roles(UserRole.superadmin.value, UserRole.operator.value)),
    db: Session = Depends(get_db_session),
) -> MessageResponse:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{settings.ops_agent_url}/containers/{service_name}/actions/{action}",
            headers={"X-Internal-Token": settings.ops_agent_token},
        )
    service = PlatformService(db)
    if response.is_success:
        service.add_container_audit(
            actor_username=current_user.username,
            target_service=service_name,
            action=action,
            status_value="success",
            details_json=response.json(),
        )
        return MessageResponse(message=response.json().get("message", "ok"))
    service.add_container_audit(
        actor_username=current_user.username,
        target_service=service_name,
        action=action,
        status_value="failed",
        details_json={"status_code": response.status_code, "body": response.text},
    )
    raise ExternalServiceAppError(
        "运维代理执行容器动作失败。",
        service="ops-agent",
        status_code=response.status_code,
        details={"body": response.text},
    )

