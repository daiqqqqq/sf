from __future__ import annotations

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.orm import Session

from app.api.dependencies import require_roles
from app.db.session import get_db_session
from app.models.entities import AdminUser, UserRole
from app.schemas.api import DocumentRead, IngestJobRead, MessageResponse
from app.services.platform_service import PlatformService
from app.tasks.pipeline import dispatch_ingest_job

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.post("/upload")
async def upload_document(
    kb_id: int = Query(..., ge=1),
    file: UploadFile = File(...),
    db: Session = Depends(get_db_session),
    _: AdminUser = Depends(require_roles(UserRole.superadmin.value, UserRole.operator.value)),
) -> dict[str, object]:
    service = PlatformService(db)
    document, job = await service.create_document(kb_id, file)
    dispatch_ingest_job(job.id)
    return {
        "document": DocumentRead.model_validate(document, from_attributes=True),
        "job": IngestJobRead.model_validate(job, from_attributes=True),
    }


@router.get("", response_model=list[DocumentRead])
def list_documents(
    kb_id: int | None = Query(default=None),
    db: Session = Depends(get_db_session),
    _: AdminUser = Depends(
        require_roles(
            UserRole.superadmin.value,
            UserRole.operator.value,
            UserRole.viewer.value,
        )
    ),
) -> list[DocumentRead]:
    items = PlatformService(db).list_documents(kb_id)
    return [DocumentRead.model_validate(item, from_attributes=True) for item in items]


@router.post("/{document_id}/retry", response_model=IngestJobRead)
def retry_document(
    document_id: int,
    db: Session = Depends(get_db_session),
    _: AdminUser = Depends(require_roles(UserRole.superadmin.value, UserRole.operator.value)),
) -> IngestJobRead:
    job = PlatformService(db).retry_document(document_id)
    dispatch_ingest_job(job.id)
    return IngestJobRead.model_validate(job, from_attributes=True)

