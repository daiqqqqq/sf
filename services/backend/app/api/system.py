from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import require_roles
from app.db.session import get_db_session
from app.models.entities import AdminUser, UserRole
from app.schemas.api import ContainerAuditRead, HealthSnapshotRead, IngestJobRead, OverviewResponse
from app.services.health_service import HealthService
from app.services.platform_service import PlatformService

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/overview", response_model=OverviewResponse)
def overview(
    db: Session = Depends(get_db_session),
    _: AdminUser = Depends(
        require_roles(
            UserRole.superadmin.value,
            UserRole.operator.value,
            UserRole.viewer.value,
        )
    ),
) -> OverviewResponse:
    data = PlatformService(db).get_overview()
    return OverviewResponse(
        metrics=data["metrics"],
        service_health=[HealthSnapshotRead.model_validate(item, from_attributes=True) for item in data["service_health"]],
        latest_jobs=[IngestJobRead.model_validate(item, from_attributes=True) for item in data["latest_jobs"]],
        latest_audits=[ContainerAuditRead.model_validate(item, from_attributes=True) for item in data["latest_audits"]],
        backup_status=data["backup_status"],
    )


@router.get("/health", response_model=list[HealthSnapshotRead])
async def health(
    db: Session = Depends(get_db_session),
    _: AdminUser = Depends(
        require_roles(
            UserRole.superadmin.value,
            UserRole.operator.value,
            UserRole.viewer.value,
        )
    ),
) -> list[HealthSnapshotRead]:
    snapshots = await HealthService(db).probe_all()
    return [HealthSnapshotRead.model_validate(snapshot, from_attributes=True) for snapshot in snapshots]
