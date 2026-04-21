"""Create the legacy application schema baseline."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260421_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admin_users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("password_hash", sa.String(length=256), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_superuser", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("username"),
    )
    op.create_index("ix_admin_users_username", "admin_users", ["username"])

    op.create_table(
        "knowledge_bases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("chunk_size", sa.Integer(), nullable=False, server_default="800"),
        sa.Column("chunk_overlap", sa.Integer(), nullable=False, server_default="120"),
        sa.Column("retrieval_top_k", sa.Integer(), nullable=False, server_default="6"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_knowledge_bases_name", "knowledge_bases", ["name"])

    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kb_id", sa.Integer(), sa.ForeignKey("knowledge_bases.id"), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False, server_default="application/octet-stream"),
        sa.Column("object_key", sa.String(length=512), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("parser_backend", sa.String(length=64), nullable=False, server_default="auto"),
        sa.Column("extracted_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("error_message", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("object_key"),
    )
    op.create_index("ix_documents_kb_id", "documents", ["kb_id"])

    op.create_table(
        "document_chunks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("kb_id", sa.Integer(), sa.ForeignKey("knowledge_bases.id"), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("score_hint", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"])
    op.create_index("ix_document_chunks_kb_id", "document_chunks", ["kb_id"])

    op.create_table(
        "ingest_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("kb_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("stage", sa.String(length=64), nullable=False, server_default="queued"),
        sa.Column("retries", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_ingest_jobs_document_id", "ingest_jobs", ["document_id"])
    op.create_index("ix_ingest_jobs_kb_id", "ingest_jobs", ["kb_id"])

    op.create_table(
        "chunk_index_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("ingest_jobs.id"), nullable=False),
        sa.Column("backend", sa.String(length=64), nullable=False, server_default="hybrid"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("item_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_message", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_chunk_index_tasks_job_id", "chunk_index_tasks", ["job_id"])

    op.create_table(
        "model_providers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("protocol", sa.String(length=32), nullable=False),
        sa.Column("base_url", sa.String(length=255), nullable=False),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("api_key", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "service_health_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("service_name", sa.String(length=128), nullable=False),
        sa.Column("service_type", sa.String(length=64), nullable=False),
        sa.Column("host", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="unknown"),
        sa.Column("response_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("details_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_service_health_snapshots_service_name", "service_health_snapshots", ["service_name"])

    op.create_table(
        "container_action_audits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor_username", sa.String(length=64), nullable=False),
        sa.Column("target_service", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("details_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_container_action_audits_actor_username", "container_action_audits", ["actor_username"])


def downgrade() -> None:
    op.drop_index("ix_container_action_audits_actor_username", table_name="container_action_audits")
    op.drop_table("container_action_audits")
    op.drop_index("ix_service_health_snapshots_service_name", table_name="service_health_snapshots")
    op.drop_table("service_health_snapshots")
    op.drop_table("model_providers")
    op.drop_index("ix_chunk_index_tasks_job_id", table_name="chunk_index_tasks")
    op.drop_table("chunk_index_tasks")
    op.drop_index("ix_ingest_jobs_kb_id", table_name="ingest_jobs")
    op.drop_index("ix_ingest_jobs_document_id", table_name="ingest_jobs")
    op.drop_table("ingest_jobs")
    op.drop_index("ix_document_chunks_kb_id", table_name="document_chunks")
    op.drop_index("ix_document_chunks_document_id", table_name="document_chunks")
    op.drop_table("document_chunks")
    op.drop_index("ix_documents_kb_id", table_name="documents")
    op.drop_table("documents")
    op.drop_index("ix_knowledge_bases_name", table_name="knowledge_bases")
    op.drop_table("knowledge_bases")
    op.drop_index("ix_admin_users_username", table_name="admin_users")
    op.drop_table("admin_users")
