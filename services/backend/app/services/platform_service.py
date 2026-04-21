from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import UploadFile, status
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AuthAppError, ConflictAppError, NotFoundAppError, ValidationAppError
from app.core.metrics import BACKUP_LAST_SUCCESS_TIMESTAMP, DOCUMENT_UPLOADS_TOTAL
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
    UserRole,
)
from app.schemas.api import KnowledgeBaseCreate, LoginRequest, UserCreateRequest, UserPasswordResetRequest, UserUpdateRequest
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
                role=UserRole.superadmin.value,
            )
            self.db.add(admin)
        else:
            admin.role = admin.role or UserRole.superadmin.value
            admin.is_superuser = admin.role == UserRole.superadmin.value

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
            raise AuthAppError("用户名或密码错误。")
        if not user.is_active:
            raise AuthAppError("当前账号已被禁用。", status_code=status.HTTP_403_FORBIDDEN, code="inactive_user")

        user.last_login_at = datetime.now(UTC)
        self.db.commit()
        access = create_token(
            str(user.id),
            "access",
            self.settings.access_token_expire_minutes,
            {"username": user.username, "role": user.role},
        )
        refresh = create_token(
            str(user.id),
            "refresh",
            self.settings.refresh_token_expire_minutes,
            {"username": user.username, "role": user.role},
        )
        return user, {"access_token": access, "refresh_token": refresh, "token_type": "bearer"}

    def list_users(self) -> list[AdminUser]:
        return list(self.db.scalars(select(AdminUser).order_by(AdminUser.id)))

    def create_user(self, payload: UserCreateRequest) -> AdminUser:
        role = self._normalize_role(payload.role)
        existing = self.db.scalar(select(AdminUser).where(AdminUser.username == payload.username))
        if existing is not None:
            raise ConflictAppError(f"用户 {payload.username} 已存在。")
        user = AdminUser(
            username=payload.username,
            password_hash=hash_password(payload.password),
            is_active=payload.is_active,
            is_superuser=role == UserRole.superadmin.value,
            role=role,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def update_user(self, user_id: int, payload: UserUpdateRequest) -> AdminUser:
        user = self._get_user(user_id)
        if payload.role is not None:
            role = self._normalize_role(payload.role)
            user.role = role
            user.is_superuser = role == UserRole.superadmin.value
        if payload.is_active is not None:
            user.is_active = payload.is_active
        self.db.commit()
        self.db.refresh(user)
        return user

    def reset_user_password(self, user_id: int, payload: UserPasswordResetRequest) -> AdminUser:
        user = self._get_user(user_id)
        user.password_hash = hash_password(payload.password)
        self.db.commit()
        self.db.refresh(user)
        return user

    def list_kbs(self) -> list[KnowledgeBase]:
        return list(self.db.scalars(select(KnowledgeBase).order_by(KnowledgeBase.id)))

    def get_kb(self, kb_id: int) -> KnowledgeBase:
        kb = self.db.get(KnowledgeBase, kb_id)
        if kb is None:
            raise NotFoundAppError("知识库不存在。")
        return kb

    def create_kb(self, payload: KnowledgeBaseCreate) -> KnowledgeBase:
        existing = self.db.scalar(select(KnowledgeBase).where(KnowledgeBase.name == payload.name))
        if existing is not None:
            raise ConflictAppError(f"知识库 {payload.name} 已存在。")
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
                    DOCUMENT_UPLOADS_TOTAL.labels(status="failed").inc()
                    raise ValidationAppError("上传文件超过大小限制。")
                handle.write(chunk)
        await upload.close()

        object_key = f"{kb.id}/{uuid4().hex}/{original_name}"
        try:
            self.storage.save_file(object_key, content_type, temp_path)
        except Exception:
            DOCUMENT_UPLOADS_TOTAL.labels(status="failed").inc()
            raise
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

        job = self._create_ingest_job(document)
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
        DOCUMENT_UPLOADS_TOTAL.labels(status="success").inc()
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
        return list(self.db.scalars(select(ServiceHealthSnapshot).order_by(desc(ServiceHealthSnapshot.checked_at)).limit(50)))

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

    def get_backup_status(self) -> dict[str, Any]:
        path = self.settings.backup_status_file
        if not path.exists():
            return {"status": "missing", "message": "尚未生成备份状态文件。"}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            return {"status": "invalid", "message": f"备份状态文件读取失败：{exc}"}
        last_success = payload.get("last_success_ts")
        if isinstance(last_success, (int, float)):
            BACKUP_LAST_SUCCESS_TIMESTAMP.set(last_success)
        return payload

    def get_overview(self) -> dict[str, Any]:
        latest_snapshots = self.list_latest_health_snapshots()
        unhealthy = sum(1 for item in latest_snapshots if item.status != "healthy")
        metrics = {
            "knowledge_bases": int(self.db.scalar(select(func.count(KnowledgeBase.id))) or 0),
            "documents": int(self.db.scalar(select(func.count(Document.id))) or 0),
            "jobs_pending": int(self.db.scalar(select(func.count(IngestJob.id)).where(IngestJob.status == JobStatus.pending.value)) or 0),
            "jobs_running": int(self.db.scalar(select(func.count(IngestJob.id)).where(IngestJob.status == JobStatus.running.value)) or 0),
            "jobs_failed": int(self.db.scalar(select(func.count(IngestJob.id)).where(IngestJob.status == JobStatus.failed.value)) or 0),
            "jobs_succeeded": int(self.db.scalar(select(func.count(IngestJob.id)).where(IngestJob.status == JobStatus.succeeded.value)) or 0),
            "unhealthy_services": unhealthy,
        }
        return {
            "metrics": metrics,
            "service_health": latest_snapshots,
            "latest_jobs": self.list_jobs()[:10],
            "latest_audits": self.list_audits()[:10],
            "backup_status": self.get_backup_status(),
        }

    def retry_document(self, document_id: int) -> IngestJob:
        document = self.db.get(Document, document_id)
        if document is None:
            raise NotFoundAppError("文档不存在。")
        document.status = DocumentStatus.queued.value
        document.error_message = ""
        job = self._create_ingest_job(document)
        self.db.commit()
        self.db.refresh(job)
        self.events.publish(
            self.settings.kafka_topic_ingest,
            {
                "event": "document.retry",
                "document_id": document.id,
                "job_id": job.id,
                "kb_id": document.kb_id,
                "filename": document.filename,
            },
        )
        return job

    def _create_ingest_job(self, document: Document) -> IngestJob:
        job = IngestJob(
            document_id=document.id,
            kb_id=document.kb_id,
            status=JobStatus.pending.value,
            stage="queued",
        )
        self.db.add(job)
        self.db.flush()
        self.db.add(
            ChunkIndexTask(
                job_id=job.id,
                backend="hybrid",
                status=JobStatus.pending.value,
                details_json={"postgres": 0, "elasticsearch": 0, "milvus": 0},
            )
        )
        return job

    def _get_user(self, user_id: int) -> AdminUser:
        user = self.db.get(AdminUser, user_id)
        if user is None:
            raise NotFoundAppError("用户不存在。")
        return user

    @staticmethod
    def _normalize_role(role: str) -> str:
        valid_roles = {item.value for item in UserRole}
        if role not in valid_roles:
            raise ValidationAppError(f"无效角色：{role}")
        return role
