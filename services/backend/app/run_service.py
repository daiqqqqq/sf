from __future__ import annotations

import logging
import os
import socket
import sys
import time
from typing import Callable
from urllib.parse import urlparse

import httpx
import redis
from minio import Minio
from sqlalchemy import text

from app.core.config import Settings, get_settings
from app.core.logging_utils import configure_logging, log_event
from app.db.session import get_engine, get_session_factory, init_db
from app.services.platform_service import PlatformService

try:
    from pymilvus import connections, utility
except Exception:  # pragma: no cover - optional dependency behavior
    connections = utility = None  # type: ignore[assignment]


class StartupWaitError(RuntimeError):
    """Raised when a runtime dependency does not become available in time."""


def wait_for_dependencies(role: str, settings: Settings) -> None:
    checks: list[tuple[str, Callable[[], None]]] = []
    if role in {"db-migrate", "platform-api", "rag-engine", "celery-worker", "celery-beat"}:
        checks.append(("database", lambda: wait_for_database(settings)))
    if role in {"platform-api", "celery-worker", "celery-beat"}:
        checks.append(("redis", lambda: wait_for_redis(settings.redis_url)))
    if role in {"platform-api", "celery-worker"}:
        checks.append(("kafka", lambda: wait_for_tcp_from_url(settings.kafka_bootstrap_servers)))
    if role in {"platform-api", "rag-engine", "celery-worker"}:
        checks.append(("minio", lambda: wait_for_minio(settings)))
    if role in {"rag-engine", "celery-worker"}:
        checks.append(("elasticsearch", lambda: wait_for_elasticsearch(settings)))
        checks.append(("milvus", lambda: wait_for_milvus(settings)))
    if role == "rag-engine":
        checks.append(("reranker", lambda: wait_for_http(f"{settings.reranker_url}/healthz")))
    if role == "celery-worker":
        checks.append(("rag-engine", lambda: wait_for_http(f"{settings.rag_engine_url}/readyz")))
    if role == "ops-agent":
        checks.append(("docker-socket", wait_for_docker_socket))

    for name, checker in checks:
        wait_until(name=name, timeout=settings.startup_timeout_seconds, interval=settings.startup_poll_interval_seconds, check=checker)


def wait_until(*, name: str, timeout: int, interval: int, check: Callable[[], None]) -> None:
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            check()
            print(f"[startup] dependency ready: {name}")
            return
        except Exception as exc:  # pragma: no cover - runtime wait loop
            last_error = exc
            print(f"[startup] waiting for {name}: {exc}")
            time.sleep(interval)
    raise StartupWaitError(f"{name} not ready within {timeout}s: {last_error}")


def wait_for_database(settings: Settings) -> None:
    if settings.database_url.startswith("sqlite"):
        return
    engine = get_engine()
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))


def wait_for_redis(redis_url: str) -> None:
    client = redis.from_url(redis_url)
    if not client.ping():
        raise StartupWaitError("redis ping failed")


def wait_for_minio(settings: Settings) -> None:
    host, port = settings.minio_endpoint.rsplit(":", 1)
    client = Minio(
        f"{host}:{port}",
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )
    client.list_buckets()


def wait_for_elasticsearch(settings: Settings) -> None:
    response = httpx.get(f"{settings.elasticsearch_url}/_cluster/health", timeout=5.0)
    response.raise_for_status()


def wait_for_milvus(settings: Settings) -> None:
    if connections is None or utility is None:
        wait_for_http_or_tcp(settings.milvus_uri)
        return
    alias = "startup-check"
    connections.connect(alias=alias, uri=settings.milvus_uri, token=settings.milvus_token or None)
    try:
        utility.list_collections(using=alias)
    finally:
        connections.disconnect(alias=alias)


def wait_for_tcp(endpoint: str) -> None:
    host, port = endpoint.rsplit(":", 1)
    with socket.create_connection((host, int(port)), timeout=3):
        return


def wait_for_tcp_from_url(endpoint: str) -> None:
    candidates = [item.strip() for item in endpoint.split(",") if item.strip()]
    if not candidates:
        return
    wait_for_tcp(candidates[0])


def wait_for_http(url: str) -> None:
    response = httpx.get(url, timeout=5.0)
    response.raise_for_status()


def wait_for_http_or_tcp(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme in {"http", "https"}:
        try:
            wait_for_http(url)
            return
        except Exception:
            endpoint = f"{parsed.hostname}:{parsed.port or 80}"
            wait_for_tcp(endpoint)
            return
    wait_for_tcp(url)


def wait_for_docker_socket() -> None:
    if not os.path.exists("/var/run/docker.sock"):
        raise StartupWaitError("/var/run/docker.sock missing")


def bootstrap_api() -> None:
    init_db()
    db = get_session_factory()()
    try:
        PlatformService(db).bootstrap()
    finally:
        db.close()


def command_for_role(role: str, settings: Settings) -> list[str]:
    if role == "platform-api":
        return [
            "gunicorn",
            "app.main:app",
            "-k",
            "uvicorn.workers.UvicornWorker",
            "-b",
            "0.0.0.0:8000",
            "--workers",
            str(settings.api_workers),
            "--timeout",
            "300",
            "--access-logfile",
            "-",
            "--error-logfile",
            "-",
        ]
    if role == "rag-engine":
        return [
            "gunicorn",
            "app.rag_main:app",
            "-k",
            "uvicorn.workers.UvicornWorker",
            "-b",
            "0.0.0.0:8100",
            "--workers",
            str(settings.rag_workers),
            "--timeout",
            "300",
            "--access-logfile",
            "-",
            "--error-logfile",
            "-",
        ]
    if role == "ops-agent":
        return [
            "gunicorn",
            "app.ops_main:app",
            "-k",
            "uvicorn.workers.UvicornWorker",
            "-b",
            "0.0.0.0:8200",
            "--workers",
            "1",
            "--timeout",
            "120",
            "--access-logfile",
            "-",
            "--error-logfile",
            "-",
        ]
    if role == "reranker":
        return ["uvicorn", "app.reranker_main:app", "--host", "0.0.0.0", "--port", "8300"]
    if role == "celery-worker":
        return [
            "celery",
            "-A",
            "app.celery_app:celery_app",
            "worker",
            "--loglevel=INFO",
            "--concurrency",
            str(settings.celery_worker_concurrency),
        ]
    if role == "celery-beat":
        return ["celery", "-A", "app.celery_app:celery_app", "beat", "--loglevel=INFO"]
    raise SystemExit(f"Unsupported SERVICE_ROLE: {role}")


def main() -> None:
    configure_logging()
    settings = get_settings()
    role = os.getenv("SERVICE_ROLE", "platform-api")
    wait_for_dependencies(role, settings)

    if role == "db-migrate":
        init_db()
        print("[startup] database migrations completed")
        return
    if role == "platform-api":
        bootstrap_api()
    elif role in {"rag-engine", "celery-worker", "celery-beat"}:
        init_db()

    command = command_for_role(role, settings)
    log_event(logging.getLogger(__name__), "service_launch", role=role, command=command)
    print(f"[startup] launching {role}: {' '.join(command)}")
    os.execvp(command[0], command)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # pragma: no cover - runtime failure path
        print(f"[startup] fatal: {exc}", file=sys.stderr)
        raise
