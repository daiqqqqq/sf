"""Add RBAC and hybrid retrieval metadata fields."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260421_02"
down_revision = "20260421_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "admin_users",
        sa.Column("role", sa.String(length=32), nullable=False, server_default="superadmin"),
    )
    op.add_column(
        "document_chunks",
        sa.Column("chunk_key", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "chunk_index_tasks",
        sa.Column("details_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )

    connection = op.get_bind()
    connection.execute(sa.text("UPDATE admin_users SET role = 'superadmin' WHERE role IS NULL OR role = ''"))
    connection.execute(
        sa.text(
            "UPDATE document_chunks "
            "SET chunk_key = CAST(kb_id AS TEXT) || ':' || CAST(document_id AS TEXT) || ':' || CAST(chunk_index AS TEXT) "
            "WHERE chunk_key IS NULL"
        )
    )

    op.alter_column("document_chunks", "chunk_key", existing_type=sa.String(length=128), nullable=False)
    op.create_index("ix_document_chunks_chunk_key", "document_chunks", ["chunk_key"], unique=True)
    op.create_index("ix_admin_users_role", "admin_users", ["role"])


def downgrade() -> None:
    op.drop_index("ix_admin_users_role", table_name="admin_users")
    op.drop_index("ix_document_chunks_chunk_key", table_name="document_chunks")
    op.drop_column("chunk_index_tasks", "details_json")
    op.drop_column("document_chunks", "chunk_key")
    op.drop_column("admin_users", "role")
