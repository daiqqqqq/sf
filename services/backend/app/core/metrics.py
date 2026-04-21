from __future__ import annotations

from contextlib import contextmanager
from time import perf_counter
from typing import Iterator

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from starlette.requests import Request
from starlette.responses import Response


HTTP_REQUESTS_TOTAL = Counter(
    "rag_platform_http_requests_total",
    "Total HTTP requests handled by the service.",
    ["service", "method", "path", "status"],
)
HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "rag_platform_http_request_duration_seconds",
    "HTTP request duration in seconds.",
    ["service", "method", "path"],
    buckets=(0.01, 0.05, 0.1, 0.3, 0.5, 1, 3, 5, 10, 30),
)
DOCUMENT_UPLOADS_TOTAL = Counter(
    "rag_platform_document_uploads_total",
    "Document upload attempts.",
    ["status"],
)
INGEST_JOBS_TOTAL = Counter(
    "rag_platform_ingest_jobs_total",
    "Ingest job outcomes.",
    ["status"],
)
RAG_QUERIES_TOTAL = Counter(
    "rag_platform_rag_queries_total",
    "RAG query executions.",
    ["status"],
)
RAG_DEGRADED_TOTAL = Counter(
    "rag_platform_rag_degraded_total",
    "RAG degraded retrieval events.",
    ["backend"],
)
RAG_CANDIDATE_RESULTS = Histogram(
    "rag_platform_rag_candidates",
    "Candidate counts produced by retrieval stages.",
    ["stage"],
    buckets=(1, 3, 5, 10, 20, 50, 100),
)
MODEL_REQUESTS_TOTAL = Counter(
    "rag_platform_model_requests_total",
    "Generation model requests.",
    ["provider", "status"],
)
MODEL_REQUEST_DURATION_SECONDS = Histogram(
    "rag_platform_model_request_duration_seconds",
    "Generation model request duration in seconds.",
    ["provider"],
    buckets=(0.1, 0.3, 0.5, 1, 3, 5, 10, 30, 60, 120),
)
BACKUP_LAST_SUCCESS_TIMESTAMP = Gauge(
    "rag_platform_backup_last_success_timestamp",
    "Unix timestamp for the latest successful backup known to the platform.",
)


def metrics_response() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


def record_http_metrics(service: str, request: Request, status_code: int, elapsed_seconds: float) -> None:
    route = request.scope.get("route")
    path = getattr(route, "path", request.url.path)
    HTTP_REQUESTS_TOTAL.labels(service=service, method=request.method, path=path, status=str(status_code)).inc()
    HTTP_REQUEST_DURATION_SECONDS.labels(service=service, method=request.method, path=path).observe(elapsed_seconds)


@contextmanager
def observe_histogram(histogram: Histogram, *label_values: str) -> Iterator[None]:
    started = perf_counter()
    try:
        yield
    finally:
        histogram.labels(*label_values).observe(perf_counter() - started)
