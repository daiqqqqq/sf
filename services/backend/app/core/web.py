from __future__ import annotations

import logging
from time import perf_counter

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.errors import AppError
from app.core.logging_utils import log_event
from app.core.metrics import record_http_metrics

logger = logging.getLogger(__name__)


def install_common_handlers(app: FastAPI, *, service_name: str) -> None:
    @app.middleware("http")
    async def metrics_middleware(request: Request, call_next):
        started = perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            record_http_metrics(service_name, request, 500, perf_counter() - started)
            raise
        record_http_metrics(service_name, request, response.status_code, perf_counter() - started)
        return response

    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        log_event(logger, "app_error", service=service_name, code=exc.code, status_code=exc.status_code, details=exc.details)
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.message, "code": exc.code, "details": exc.details},
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "detail": "请求参数校验失败。",
                "code": "request_validation_error",
                "details": {"errors": exc.errors()},
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, str) else "请求处理失败。"
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": detail, "code": "http_error", "details": {}},
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(_: Request, exc: Exception) -> JSONResponse:
        log_event(logger, "unhandled_error", service=service_name, error=str(exc))
        return JSONResponse(
            status_code=500,
            content={"detail": "服务内部发生未处理异常。", "code": "internal_error", "details": {}},
        )
