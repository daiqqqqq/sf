from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import require_roles
from app.db.session import get_db_session
from app.models.entities import AdminUser, UserRole
from app.schemas.api import AuditListResponse, ContainerAuditRead
from app.services.platform_service import PlatformService

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("", response_model=AuditListResponse)
def audit_logs(
    db: Session = Depends(get_db_session),
    _: AdminUser = Depends(
        require_roles(
            UserRole.superadmin.value,
            UserRole.operator.value,
            UserRole.viewer.value,
        )
    ),
) -> AuditListResponse:
    items = [ContainerAuditRead.model_validate(item, from_attributes=True) for item in PlatformService(db).list_audits()]
    return AuditListResponse(items=items)

