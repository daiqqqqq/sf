from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class TokenPayload(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    username: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class UserRead(BaseModel):
    id: int
    username: str
    is_active: bool
    is_superuser: bool
    role: str
    last_login_at: datetime | None = None


class UserCreateRequest(BaseModel):
    username: str
    password: str = Field(min_length=8)
    role: str = "viewer"
    is_active: bool = True


class UserUpdateRequest(BaseModel):
    role: str | None = None
    is_active: bool | None = None


class UserPasswordResetRequest(BaseModel):
    password: str = Field(min_length=8)


class KnowledgeBaseCreate(BaseModel):
    name: str
    description: str = ""
    chunk_size: int = 800
    chunk_overlap: int = 120
    retrieval_top_k: int = 6


class KnowledgeBaseRead(KnowledgeBaseCreate):
    id: int
    created_at: datetime
    updated_at: datetime


class DocumentRead(BaseModel):
    id: int
    kb_id: int
    filename: str
    content_type: str
    size_bytes: int
    status: str
    parser_backend: str
    error_message: str
    created_at: datetime
    updated_at: datetime


class IngestJobRead(BaseModel):
    id: int
    document_id: int
    kb_id: int
    status: str
    stage: str
    retries: int
    error_message: str
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class ModelProviderRead(BaseModel):
    id: int
    name: str
    kind: str
    protocol: str
    base_url: str
    model_name: str
    enabled: bool
    priority: int
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class HealthSnapshotRead(BaseModel):
    service_name: str
    service_type: str
    host: str
    status: str
    response_ms: int
    details_json: dict[str, Any]
    checked_at: datetime


class ContainerState(BaseModel):
    name: str
    status: str
    image: str | None = None
    started_at: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


class ContainerActionRequest(BaseModel):
    action: str


class ContainerAuditRead(BaseModel):
    id: int
    actor_username: str
    target_service: str
    action: str
    status: str
    details_json: dict[str, Any]
    created_at: datetime


class RagQueryRequest(BaseModel):
    kb_id: int
    query: str
    top_k: int = 6
    model_provider_id: int | None = None


class RagChunkResult(BaseModel):
    chunk_id: int
    document_id: int
    score: float
    source: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class RagQueryResponse(BaseModel):
    answer: str
    results: list[RagChunkResult]
    used_model: str | None = None
    debug: dict[str, Any] = Field(default_factory=dict)


class OverviewResponse(BaseModel):
    metrics: dict[str, int]
    service_health: list[HealthSnapshotRead]
    latest_jobs: list[IngestJobRead]
    latest_audits: list[ContainerAuditRead]
    backup_status: dict[str, Any] = Field(default_factory=dict)


class AuditListResponse(BaseModel):
    items: list[ContainerAuditRead]


class MessageResponse(BaseModel):
    message: str


class InternalIngestRequest(BaseModel):
    document_id: int
    kb_id: int
    text: str


class InternalIngestResponse(BaseModel):
    chunks: int
    indexed_backends: dict[str, int] = Field(default_factory=dict)


class RerankRequest(BaseModel):
    query: str
    passages: list[str]


class RerankResponse(BaseModel):
    scores: list[float]

