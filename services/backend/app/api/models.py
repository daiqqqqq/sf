from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import require_roles
from app.db.session import get_db_session
from app.models.entities import AdminUser, UserRole
from app.schemas.api import HealthSnapshotRead, ModelProviderRead
from app.services.health_service import HealthService
from app.services.platform_service import PlatformService

router = APIRouter(prefix="/api/models", tags=["models"])


@router.get("/providers", response_model=list[ModelProviderRead])
def list_model_providers(
    db: Session = Depends(get_db_session),
    _: AdminUser = Depends(
        require_roles(
            UserRole.superadmin.value,
            UserRole.operator.value,
            UserRole.viewer.value,
        )
    ),
) -> list[ModelProviderRead]:
    return [ModelProviderRead.model_validate(item, from_attributes=True) for item in PlatformService(db).list_model_providers()]


@router.get("/health", response_model=list[HealthSnapshotRead])
async def probe_models(
    db: Session = Depends(get_db_session),
    _: AdminUser = Depends(
        require_roles(
            UserRole.superadmin.value,
            UserRole.operator.value,
            UserRole.viewer.value,
        )
    ),
) -> list[HealthSnapshotRead]:
    items = await HealthService(db).probe_all()
    return [HealthSnapshotRead.model_validate(item, from_attributes=True) for item in items]

