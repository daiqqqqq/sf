from __future__ import annotations

from collections.abc import Generator
from functools import lru_cache
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


@lru_cache(maxsize=1)
def get_engine():
    settings = get_settings()
    connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
    return create_engine(settings.database_url, future=True, pool_pre_ping=True, connect_args=connect_args)


@lru_cache(maxsize=1)
def get_session_factory():
    return sessionmaker(bind=get_engine(), autoflush=False, autocommit=False, expire_on_commit=False, class_=Session)


def _alembic_config() -> Config:
    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "app" / "db" / "migrations"))
    config.set_main_option("sqlalchemy.url", get_settings().database_url)
    return config


def _stamp_legacy_schema_if_needed() -> None:
    engine = get_engine()
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "alembic_version" in tables or not tables:
        return
    legacy_tables = {
        "admin_users",
        "knowledge_bases",
        "documents",
        "document_chunks",
        "ingest_jobs",
        "chunk_index_tasks",
        "model_providers",
        "service_health_snapshots",
        "container_action_audits",
    }
    if not legacy_tables.issubset(tables):
        return
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)"))
        connection.execute(text("DELETE FROM alembic_version"))
        connection.execute(text("INSERT INTO alembic_version (version_num) VALUES ('20260421_01')"))


def init_db() -> None:
    _stamp_legacy_schema_if_needed()
    command.upgrade(_alembic_config(), "head")


def get_db_session() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()

