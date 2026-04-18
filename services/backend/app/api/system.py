from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db_session
from app.models.entities import AdminUser
from app.schemas.api import ContainerAuditRead, HealthSnapshotRead, IngestJobRead, OverviewResponse
from app.services.health_service import HealthService
from app.services.platform_service import PlatformService

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/overview", response_model=OverviewResponse)
def overview(
    db: Session = Depends(get_db_session),
    _: AdminUser = Depends(get_current_user),
) -> OverviewResponse:
    data = PlatformService(db).get_overview()
    return OverviewResponse(
        metrics=data["metrics"],
        service_health=[HealthSnapshotRead.model_validate(item, from_attributes=True) for item in data["service_health"]],
        latest_jobs=[IngestJobRead.model_validate(item, from_attributes=True) for item in data["latest_jobs"]],
        latest_audits=[ContainerAuditRead.model_validate(item, from_attributes=True) for item in data["latest_audits"]],
    )


@router.get("/health", response_model=list[HealthSnapshotRead])
async def health(
    db: Session = Depends(get_db_session),
    _: AdminUser = Depends(get_current_user),
) -> list[HealthSnapshotRead]:
    snapshots = await HealthService(db).probe_all()
    return [HealthSnapshotRead.model_validate(snapshot, from_attributes=True) for snapshot in snapshots]
