from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import create_token, hash_password, verify_password
from app.models.entities import (
    AdminUser,
    ChunkIndexTask,
    ContainerActionAudit,
    Document,
    DocumentStatus,
    IngestJob,
    JobStatus,
    KnowledgeBase,
    ModelProvider,
    ProviderKind,
    ServiceHealthSnapshot,
)
from app.schemas.api import KnowledgeBaseCreate, LoginRequest
from app.services.events import EventPublisher
from app.services.storage import StorageService
from app.utils.text import detect_parser_backend


class PlatformService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()
        self.storage = StorageService()
        self.events = EventPublisher()

    def bootstrap(self) -> None:
        admin = self.db.scalar(select(AdminUser).where(AdminUser.username == self.settings.admin_username))
        if admin is None:
            admin = AdminUser(
                username=self.settings.admin_username,
                password_hash=hash_password(self.settings.admin_password),
                is_active=True,
                is_superuser=True,
            )
            self.db.add(admin)

        if self.db.scalar(select(func.count(KnowledgeBase.id))) == 0:
            self.db.add(
                KnowledgeBase(
                    name="默认知识库",
                    description="初始知识库，可直接上传文档进行联调。",
                    chunk_size=800,
                    chunk_overlap=120,
                    retrieval_top_k=6,
                )
            )

        self._seed_model_provider(
            name="ollama-qwen3-embedding",
            kind=ProviderKind.embedding.value,
            protocol="ollama",
            base_url=self.settings.ollama_base_url,
            model_name=self.settings.ollama_embedding_model,
            priority=10,
            metadata_json={"role": "embedding"},
        )
        self._seed_model_provider(
            name="vllm-qwen27-chat",
            kind=ProviderKind.generation.value,
            protocol="openai",
            base_url=self.settings.vllm_qwen27_base_url,
            model_name=self.settings.vllm_qwen27_model,
            api_key=self.settings.vllm_qwen27_api_key,
            priority=20,
            metadata_json={"context_length": 131072, "role": "standard"},
        )
        self._seed_model_provider(
            name="vllm-qwen35-long",
            kind=ProviderKind.generation.value,
            protocol="openai",
            base_url=self.settings.vllm_qwen35_base_url,
            model_name=self.settings.vllm_qwen35_model,
            api_key=self.settings.vllm_qwen35_api_key,
            priority=30,
            metadata_json={"context_length": 262144, "role": "long-context"},
        )
        self.db.commit()

    def _seed_model_provider(
        self,
        *,
        name: str,
        kind: str,
        protocol: str,
        base_url: str,
        model_name: str,
        priority: int,
        api_key: str = "",
        metadata_json: dict[str, Any] | None = None,
    ) -> None:
        existing = self.db.scalar(select(ModelProvider).where(ModelProvider.name == name))
        if existing is None:
            self.db.add(
                ModelProvider(
                    name=name,
                    kind=kind,
                    protocol=protocol,
                    base_url=base_url,
                    model_name=model_name,
                    api_key=api_key,
                    enabled=True,
                    priority=priority,
                    metadata_json=metadata_json or {},
                )
            )

    def login(self, payload: LoginRequest) -> tuple[AdminUser, dict[str, str]]:
        user = self.db.scalar(select(AdminUser).where(AdminUser.username == payload.username))
        if user is None or not verify_password(payload.password, user.password_hash):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已禁用")
        user.last_login_at = datetime.now(UTC)
        self.db.commit()
        access = create_token(str(user.id), "access", self.settings.access_token_expire_minutes, {"username": user.username})
        refresh = create_token(str(user.id), "refresh", self.settings.refresh_token_expire_minutes, {"username": user.username})
        return user, {"access_token": access, "refresh_token": refresh, "token_type": "bearer"}

    def list_kbs(self) -> list[KnowledgeBase]:
        return list(self.db.scalars(select(KnowledgeBase).order_by(KnowledgeBase.id)))

    def get_kb(self, kb_id: int) -> KnowledgeBase:
        kb = self.db.get(KnowledgeBase, kb_id)
        if kb is None:
            raise HTTPException(status_code=404, detail="知识库不存在")
        return kb

    def create_kb(self, payload: KnowledgeBaseCreate) -> KnowledgeBase:
        kb = KnowledgeBase(**payload.model_dump())
        self.db.add(kb)
        self.db.commit()
        self.db.refresh(kb)
        return kb

    async def create_document(self, kb_id: int, upload: UploadFile) -> tuple[Document, IngestJob]:
        kb = self.get_kb(kb_id)
        original_name = Path(upload.filename or "document.bin").name
        content_type = upload.content_type or "application/octet-stream"
        temp_dir = self.settings.data_root / "tmp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_path = temp_dir / f"{uuid4().hex}.upload"
        size_bytes = 0
        with temp_path.open("wb") as handle:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                size_bytes += len(chunk)
                if size_bytes > self.settings.max_upload_bytes:
                    temp_path.unlink(missing_ok=True)
                    raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="上传文件超过限制")
                handle.write(chunk)
        await upload.close()

        object_key = f"{kb.id}/{uuid4().hex}/{original_name}"
        try:
            self.storage.save_file(object_key, content_type, temp_path)
        finally:
            temp_path.unlink(missing_ok=True)

        document = Document(
            kb_id=kb.id,
            filename=original_name,
            content_type=content_type,
            object_key=object_key,
            size_bytes=size_bytes,
            status=DocumentStatus.queued.value,
            parser_backend=detect_parser_backend(original_name),
        )
        self.db.add(document)
        self.db.flush()

        job = IngestJob(
            document_id=document.id,
            kb_id=kb.id,
            status=JobStatus.pending.value,
            stage="queued",
        )
        self.db.add(job)
        self.db.flush()

        task = ChunkIndexTask(job_id=job.id, backend="hybrid", status=JobStatus.pending.value)
        self.db.add(task)
        self.db.commit()
        self.db.refresh(document)
        self.db.refresh(job)

        self.events.publish(
            self.settings.kafka_topic_ingest,
            {
                "event": "document.queued",
                "document_id": document.id,
                "job_id": job.id,
                "kb_id": kb.id,
                "filename": document.filename,
            },
        )
        return document, job

    def list_documents(self, kb_id: int | None = None) -> list[Document]:
        stmt = select(Document).order_by(desc(Document.created_at))
        if kb_id is not None:
            stmt = stmt.where(Document.kb_id == kb_id)
        return list(self.db.scalars(stmt))

    def list_jobs(self) -> list[IngestJob]:
        return list(self.db.scalars(select(IngestJob).order_by(desc(IngestJob.created_at)).limit(100)))

    def list_model_providers(self) -> list[ModelProvider]:
        return list(self.db.scalars(select(ModelProvider).order_by(ModelProvider.priority, ModelProvider.id)))

    def list_health_snapshots(self) -> list[ServiceHealthSnapshot]:
        return list(self.db.scalars(select(ServiceHealthSnapshot).order_by(desc(ServiceHealthSnapshot.checked_at)).limit(20)))

    def list_latest_health_snapshots(self) -> list[ServiceHealthSnapshot]:
        ranked_snapshots = (
            select(
                ServiceHealthSnapshot.id.label("id"),
                func.row_number()
                .over(
                    partition_by=ServiceHealthSnapshot.service_name,
                    order_by=ServiceHealthSnapshot.checked_at.desc(),
                )
                .label("row_number"),
            )
            .subquery()
        )
        stmt = (
            select(ServiceHealthSnapshot)
            .join(ranked_snapshots, ServiceHealthSnapshot.id == ranked_snapshots.c.id)
            .where(ranked_snapshots.c.row_number == 1)
            .order_by(desc(ServiceHealthSnapshot.checked_at), ServiceHealthSnapshot.service_name)
        )
        return list(self.db.scalars(stmt))

    def list_audits(self) -> list[ContainerActionAudit]:
        return list(self.db.scalars(select(ContainerActionAudit).order_by(desc(ContainerActionAudit.created_at)).limit(200)))

    def add_container_audit(
        self,
        *,
        actor_username: str,
        target_service: str,
        action: str,
        status_value: str,
        details_json: dict[str, Any] | None = None,
    ) -> ContainerActionAudit:
        audit = ContainerActionAudit(
            actor_username=actor_username,
            target_service=target_service,
            action=action,
            status=status_value,
            details_json=details_json or {},
        )
        self.db.add(audit)
        self.db.commit()
        self.db.refresh(audit)
        self.events.publish(
            self.settings.kafka_topic_audit,
            {
                "event": "container.audit",
                "actor": actor_username,
                "target_service": target_service,
                "action": action,
                "status": status_value,
            },
        )
        return audit

    def get_overview(self) -> dict[str, Any]:
        metrics = {
            "knowledge_bases": int(self.db.scalar(select(func.count(KnowledgeBase.id))) or 0),
            "documents": int(self.db.scalar(select(func.count(Document.id))) or 0),
            "jobs_pending": int(self.db.scalar(select(func.count(IngestJob.id)).where(IngestJob.status == JobStatus.pending.value)) or 0),
            "jobs_running": int(self.db.scalar(select(func.count(IngestJob.id)).where(IngestJob.status == JobStatus.running.value)) or 0),
            "jobs_failed": int(self.db.scalar(select(func.count(IngestJob.id)).where(IngestJob.status == JobStatus.failed.value)) or 0),
        }
        return {
            "metrics": metrics,
            "service_health": self.list_latest_health_snapshots(),
            "latest_jobs": self.list_jobs()[:10],
            "latest_audits": self.list_audits()[:10],
        }

    def retry_document(self, document_id: int) -> IngestJob:
        document = self.db.get(Document, document_id)
        if document is None:
            raise HTTPException(status_code=404, detail="文档不存在")
        document.status = DocumentStatus.queued.value
        job = IngestJob(document_id=document.id, kb_id=document.kb_id, status=JobStatus.pending.value, stage="queued")
        self.db.add(job)
        self.db.flush()
        self.db.add(ChunkIndexTask(job_id=job.id, backend="hybrid", status=JobStatus.pending.value))
        self.db.commit()
        self.db.refresh(job)
        return job
