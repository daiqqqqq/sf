from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.config import get_settings
from app.db.session import get_db_session
from app.models.entities import AdminUser
from app.schemas.api import RagQueryRequest, RagQueryResponse

router = APIRouter(prefix="/api/rag", tags=["rag"])


@router.post("/query", response_model=RagQueryResponse)
async def rag_query(
    payload: RagQueryRequest,
    _: AdminUser = Depends(get_current_user),
) -> RagQueryResponse:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{settings.rag_engine_url}/query",
            json=payload.model_dump(),
            headers={"X-Internal-Token": settings.internal_service_token},
        )
        response.raise_for_status()
    return RagQueryResponse(**response.json())


@router.post("/debug", response_model=RagQueryResponse)
async def rag_debug(
    payload: RagQueryRequest,
    _: AdminUser = Depends(get_current_user),
) -> RagQueryResponse:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{settings.rag_engine_url}/query",
            json=payload.model_dump(),
            headers={"X-Internal-Token": settings.internal_service_token},
        )
        response.raise_for_status()
    return RagQueryResponse(**response.json())

