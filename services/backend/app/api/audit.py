from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db_session
from app.models.entities import AdminUser
from app.schemas.api import AuditListResponse, ContainerAuditRead
from app.services.platform_service import PlatformService

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("", response_model=AuditListResponse)
def audit_logs(
    db: Session = Depends(get_db_session),
    _: AdminUser = Depends(get_current_user),
) -> AuditListResponse:
    items = [ContainerAuditRead.model_validate(item, from_attributes=True) for item in PlatformService(db).list_audits()]
    return AuditListResponse(items=items)

