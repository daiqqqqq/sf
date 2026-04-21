from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import require_roles
from app.db.session import get_db_session
from app.models.entities import AdminUser, UserRole
from app.schemas.api import KnowledgeBaseCreate, KnowledgeBaseRead
from app.services.platform_service import PlatformService

router = APIRouter(prefix="/api/kb", tags=["knowledge-base"])


@router.get("", response_model=list[KnowledgeBaseRead])
def list_kb(
    db: Session = Depends(get_db_session),
    _: AdminUser = Depends(
        require_roles(
            UserRole.superadmin.value,
            UserRole.operator.value,
            UserRole.viewer.value,
        )
    ),
) -> list[KnowledgeBaseRead]:
    items = PlatformService(db).list_kbs()
    return [KnowledgeBaseRead.model_validate(item, from_attributes=True) for item in items]


@router.post("", response_model=KnowledgeBaseRead)
def create_kb(
    payload: KnowledgeBaseCreate,
    db: Session = Depends(get_db_session),
    _: AdminUser = Depends(require_roles(UserRole.superadmin.value, UserRole.operator.value)),
) -> KnowledgeBaseRead:
    item = PlatformService(db).create_kb(payload)
    return KnowledgeBaseRead.model_validate(item, from_attributes=True)


@router.get("/{kb_id}", response_model=KnowledgeBaseRead)
def get_kb(
    kb_id: int,
    db: Session = Depends(get_db_session),
    _: AdminUser = Depends(
        require_roles(
            UserRole.superadmin.value,
            UserRole.operator.value,
            UserRole.viewer.value,
        )
    ),
) -> KnowledgeBaseRead:
    item = PlatformService(db).get_kb(kb_id)
    return KnowledgeBaseRead.model_validate(item, from_attributes=True)

