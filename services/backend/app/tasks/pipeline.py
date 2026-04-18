from __future__ import annotations

from datetime import UTC, datetime
from io import BytesIO
import os

import httpx
from celery import shared_task
from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.core.config import Settings, get_settings
from app.db.session import get_session_factory, init_db
from app.models.entities import ChunkIndexTask, Document, DocumentStatus, IngestJob, JobStatus
from app.services.health_service import HealthService
from app.services.storage import StorageService
from app.utils.text import detect_parser_backend

try:
    from docx import Document as DocxDocument
except Exception:  # pragma: no cover - optional dependency behavior
    DocxDocument = None  # type: ignore[assignment]

try:
    from markdown import markdown
except Exception:  # pragma: no cover - optional dependency behavior
    markdown = None  # type: ignore[assignment]

try:
    from pypdf import PdfReader
except Exception:  # pragma: no cover - optional dependency behavior
    PdfReader = None  # type: ignore[assignment]


def _extract_with_tika(filename: str, payload: bytes, settings: Settings) -> tuple[str, str]:
    try:
        response = httpx.put(
            f"{settings.tika_url}/tika",
            content=payload,
            headers={
                "Accept": "text/plain",
                "Content-Disposition": f'attachment; filename="{os.path.basename(filename)}"',
            },
            timeout=90.0,
        )
        response.raise_for_status()
        return response.text, "tika"
    except Exception:
        return payload.decode("utf-8", errors="ignore"), "native"


def _extract_text(filename: str, payload: bytes, settings: Settings) -> tuple[str, str]:
    backend = detect_parser_backend(filename)
    suffix = filename.lower()
    if suffix.endswith(".pdf") and PdfReader is not None:
        reader = PdfReader(BytesIO(payload))
        extracted = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
        if extracted:
            return extracted, "pypdf"
        return _extract_with_tika(filename, payload, settings)
    if suffix.endswith(".docx") and DocxDocument is not None:
        doc = DocxDocument(BytesIO(payload))
        extracted = "\n".join(paragraph.text for paragraph in doc.paragraphs).strip()
        if extracted:
            return extracted, "python-docx"
        return _extract_with_tika(filename, payload, settings)
    if suffix.endswith((".md", ".markdown")):
        text = payload.decode("utf-8", errors="ignore")
        rendered = markdown(text) if markdown is not None else text
        return rendered, "markdown"
    if backend == "tika":
        return _extract_with_tika(filename, payload, settings)
    return payload.decode("utf-8", errors="ignore"), backend


def _run_ingest(job_id: int) -> None:
    init_db()
    settings = get_settings()
    session_factory = get_session_factory()
    db: Session = session_factory()
    try:
        job = db.get(IngestJob, job_id)
        if job is None:
            return
        document = db.get(Document, job.document_id)
        if document is None:
            return

        job.status = JobStatus.running.value
        job.stage = "parsing"
        job.started_at = datetime.now(UTC)
        document.status = DocumentStatus.processing.value
        db.commit()

        payload = StorageService().read_bytes(document.object_key)
        extracted_text, parser_backend = _extract_text(document.filename, payload, settings)

        document.extracted_text = extracted_text
        document.parser_backend = parser_backend
        job.stage = "indexing"
        db.commit()

        response = httpx.post(
            f"{settings.rag_engine_url}/ingest",
            json={"document_id": document.id, "kb_id": document.kb_id, "text": extracted_text},
            headers={"X-Internal-Token": settings.internal_service_token},
            timeout=120.0,
        )
        response.raise_for_status()
        chunks = response.json().get("chunks", 0)

        index_task = db.query(ChunkIndexTask).filter(ChunkIndexTask.job_id == job.id).first()
        if index_task is not None:
            index_task.status = JobStatus.succeeded.value
            index_task.item_count = chunks
            index_task.last_message = "indexed"

        job.status = JobStatus.succeeded.value
        job.stage = "completed"
        job.finished_at = datetime.now(UTC)
        document.status = DocumentStatus.indexed.value
        db.commit()
    except Exception as exc:
        job = db.get(IngestJob, job_id)
        if job is not None:
            job.status = JobStatus.failed.value
            job.error_message = str(exc)
            job.finished_at = datetime.now(UTC)
        document = db.get(Document, job.document_id) if job is not None else None
        if document is not None:
            document.status = DocumentStatus.failed.value
            document.error_message = str(exc)
        db.commit()
        raise
    finally:
        db.close()


def dispatch_ingest_job(job_id: int) -> None:
    settings = get_settings()
    if settings.task_execution_mode == "eager":
        _run_ingest(job_id)
    else:
        ingest_document_task.delay(job_id)


@shared_task(name="app.tasks.pipeline.ingest_document_task")
def ingest_document_task(job_id: int) -> None:
    _run_ingest(job_id)


@celery_app.task(name="app.tasks.pipeline.probe_services_task")
def probe_services_task() -> None:
    init_db()
    db = get_session_factory()()
    try:
        import asyncio

        asyncio.run(HealthService(db).probe_all())
    finally:
        db.close()
