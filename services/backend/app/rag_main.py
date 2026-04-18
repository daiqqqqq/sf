from __future__ import annotations

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.dependencies import require_internal_token
from app.core.config import get_settings
from app.db.session import get_db_session, init_db
from app.schemas.api import InternalIngestRequest, RagQueryRequest, RagQueryResponse
from app.services.rag_service import RagService

settings = get_settings()

app = FastAPI(
    title="RAG Engine",
    docs_url="/docs" if settings.app_env != "production" else None,
    redoc_url="/redoc" if settings.app_env != "production" else None,
    openapi_url="/openapi.json" if settings.app_env != "production" else None,
)


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
def readyz(db: Session = Depends(get_db_session)) -> dict[str, str]:
    db.execute(text("SELECT 1"))
    return {"status": "ready"}


@app.post("/ingest")
def ingest(
    payload: InternalIngestRequest,
    db: Session = Depends(get_db_session),
    _: None = Depends(require_internal_token),
) -> dict[str, int]:
    total = RagService(db).ingest_document(document_id=payload.document_id, kb_id=payload.kb_id, text=payload.text)
    return {"chunks": total}


@app.post("/query", response_model=RagQueryResponse)
async def query(
    payload: RagQueryRequest,
    db: Session = Depends(get_db_session),
    _: None = Depends(require_internal_token),
) -> RagQueryResponse:
    service = RagService(db)
    results, debug = service.search(kb_id=payload.kb_id, query=payload.query, top_k=payload.top_k)
    answer, used_model = await service.generate_answer(
        query=payload.query,
        contexts=results,
        model_provider_id=payload.model_provider_id,
    )
    return RagQueryResponse(answer=answer, results=results, used_model=used_model, debug=debug)
