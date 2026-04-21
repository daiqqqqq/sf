from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends

from app.api.dependencies import require_roles
from app.core.config import get_settings
from app.core.errors import ExternalServiceAppError
from app.models.entities import AdminUser, UserRole
from app.schemas.api import RagQueryRequest, RagQueryResponse

router = APIRouter(prefix="/api/rag", tags=["rag"])


@router.post("/query", response_model=RagQueryResponse)
async def rag_query(
    payload: RagQueryRequest,
    _: AdminUser = Depends(require_roles(UserRole.superadmin.value, UserRole.operator.value)),
) -> RagQueryResponse:
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{settings.rag_engine_url}/query",
                json=payload.model_dump(),
                headers={"X-Internal-Token": settings.internal_service_token},
            )
            response.raise_for_status()
    except Exception as exc:
        raise ExternalServiceAppError("RAG 引擎不可用，无法执行查询。", service="rag-engine") from exc
    return RagQueryResponse(**response.json())


@router.post("/debug", response_model=RagQueryResponse)
async def rag_debug(
    payload: RagQueryRequest,
    _: AdminUser = Depends(require_roles(UserRole.superadmin.value, UserRole.operator.value)),
) -> RagQueryResponse:
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{settings.rag_engine_url}/query",
                json=payload.model_dump(),
                headers={"X-Internal-Token": settings.internal_service_token},
            )
            response.raise_for_status()
    except Exception as exc:
        raise ExternalServiceAppError("RAG 引擎不可用，无法读取调试结果。", service="rag-engine") from exc
    return RagQueryResponse(**response.json())

