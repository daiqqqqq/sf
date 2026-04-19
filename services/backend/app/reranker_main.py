from __future__ import annotations

from typing import Any

from fastapi import Depends, FastAPI

from app.api.dependencies import require_internal_token
from app.core.config import get_settings
from app.schemas.api import RerankRequest, RerankResponse
from app.utils.text import lexical_score

settings = get_settings()

app = FastAPI(
    title="Reranker",
    docs_url="/docs" if settings.app_env != "production" else None,
    redoc_url="/redoc" if settings.app_env != "production" else None,
    openapi_url="/openapi.json" if settings.app_env != "production" else None,
)

try:
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    import torch
except Exception:  # pragma: no cover - optional dependency behavior
    AutoModelForSequenceClassification = AutoTokenizer = torch = None  # type: ignore[assignment]

MODEL_CACHE: dict[str, Any] = {}


def get_model():
    if AutoTokenizer is None or AutoModelForSequenceClassification is None or torch is None:
        return None
    if MODEL_CACHE:
        return MODEL_CACHE
    model_name = settings.reranker_model_name
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSequenceClassification.from_pretrained(model_name)
    model.eval()
    MODEL_CACHE["tokenizer"] = tokenizer
    MODEL_CACHE["model"] = model
    MODEL_CACHE["torch"] = torch
    return MODEL_CACHE


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/rerank", response_model=RerankResponse)
def rerank(payload: RerankRequest, _: None = Depends(require_internal_token)) -> RerankResponse:
    loaded = get_model()
    if loaded is None:
        scores = [lexical_score(payload.query, passage) for passage in payload.passages]
        return RerankResponse(scores=scores)

    tokenizer = loaded["tokenizer"]
    model = loaded["model"]
    torch_lib = loaded["torch"]

    pairs = [[payload.query, passage] for passage in payload.passages]
    batch = tokenizer(pairs, padding=True, truncation=True, return_tensors="pt", max_length=512)
    with torch_lib.no_grad():
        logits = model(**batch).logits.view(-1).float().tolist()
    return RerankResponse(scores=logits)
