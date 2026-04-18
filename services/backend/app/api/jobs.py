from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db_session
from app.models.entities import AdminUser
from app.schemas.api import IngestJobRead
from app.services.platform_service import PlatformService

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("", response_model=list[IngestJobRead])
def list_jobs(
    db: Session = Depends(get_db_session),
    _: AdminUser = Depends(get_current_user),
) -> list[IngestJobRead]:
    return [IngestJobRead.model_validate(item, from_attributes=True) for item in PlatformService(db).list_jobs()]

