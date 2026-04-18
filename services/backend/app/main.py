from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api import audit, auth, containers, documents, jobs, knowledge, models, rag, system
from app.db.session import get_db_session, init_db, get_session_factory
from app.core.config import get_settings
from app.services.platform_service import PlatformService


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    db = get_session_factory()()
    try:
        PlatformService(db).bootstrap()
    finally:
        db.close()
    yield


settings = get_settings()

app = FastAPI(
    title="Dual Server RAG Platform API",
    lifespan=lifespan,
    docs_url="/docs" if settings.app_env != "production" else None,
    redoc_url="/redoc" if settings.app_env != "production" else None,
    openapi_url="/openapi.json" if settings.app_env != "production" else None,
)

app.include_router(auth.router)
app.include_router(system.router)
app.include_router(containers.router)
app.include_router(knowledge.router)
app.include_router(documents.router)
app.include_router(jobs.router)
app.include_router(models.router)
app.include_router(rag.router)
app.include_router(audit.router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
def readyz(db: Session = Depends(get_db_session)) -> dict[str, str]:
    db.execute(text("SELECT 1"))
    return {"status": "ready"}
