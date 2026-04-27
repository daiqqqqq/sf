from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.dependencies import require_roles
from app.models.entities import AdminUser, UserRole
from app.schemas.api import GpuOverviewResponse
from app.services.gpu_service import GpuMonitorService

router = APIRouter(prefix="/api/gpu", tags=["gpu"])


@router.get("/overview", response_model=GpuOverviewResponse)
async def gpu_overview(
    _: AdminUser = Depends(
        require_roles(
            UserRole.superadmin.value,
            UserRole.operator.value,
            UserRole.viewer.value,
        )
    ),
) -> GpuOverviewResponse:
    return await GpuMonitorService().build_overview()
