from __future__ import annotations

import math
from typing import Any

import httpx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import Document, DocumentChunk, KnowledgeBase, ModelProvider
from app.schemas.api import RagChunkResult
from app.utils.text import chunk_text, lexical_score

try:
    from elasticsearch import Elasticsearch
except Exception:  # pragma: no cover - optional dependency behavior
    Elasticsearch = None  # type: ignore[assignment]

try:
    from pymilvus import Collection, CollectionSchema, DataType, FieldSchema, connections, utility
except Exception:  # pragma: no cover - optional dependency behavior
    Collection = CollectionSchema = DataType = FieldSchema = connections = utility = None  # type: ignore[assignment]


class RagService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()

    def ingest_document(self, *, document_id: int, kb_id: int, text: str) -> int:
        kb = self.db.get(KnowledgeBase, kb_id)
        if kb is None:
            raise ValueError(f"Knowledge base {kb_id} not found")

        self.db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document_id))
        chunks = chunk_text(text, kb.chunk_size, kb.chunk_overlap)
        total = 0
        for index, chunk in enumerate(chunks):
            item = DocumentChunk(
                document_id=document_id,
                kb_id=kb_id,
                chunk_index=index,
                content=chunk,
                score_hint=len(chunk),
                metadata_json={"source": "database", "chunk_index": index},
            )
            self.db.add(item)
            total += 1
        self.db.commit()

        document = self.db.get(Document, document_id)
        if document is not None:
            document.extracted_text = text
            document.status = "indexed"
            self.db.commit()

        self._try_sync_elasticsearch(document_id=document_id, kb_id=kb_id)
        return total

    def _try_sync_elasticsearch(self, *, document_id: int, kb_id: int) -> None:
        if Elasticsearch is None:
            return
        try:
            client = Elasticsearch(self.settings.elasticsearch_url)
            if not client.indices.exists(index=self.settings.elasticsearch_index):
                client.indices.create(
                    index=self.settings.elasticsearch_index,
                    mappings={
                        "properties": {
                            "kb_id": {"type": "integer"},
                            "document_id": {"type": "integer"},
                            "chunk_index": {"type": "integer"},
                            "content": {"type": "text"},
                        }
                    },
                )
            rows = list(
                self.db.scalars(
                    select(DocumentChunk).where(DocumentChunk.document_id == document_id, DocumentChunk.kb_id == kb_id)
                )
            )
            for row in rows:
                client.index(
                    index=self.settings.elasticsearch_index,
                    id=f"{row.document_id}-{row.chunk_index}",
                    document={
                        "kb_id": row.kb_id,
                        "document_id": row.document_id,
                        "chunk_index": row.chunk_index,
                        "content": row.content,
                    },
                )
        except Exception:
            return

    def search(self, *, kb_id: int, query: str, top_k: int = 6) -> tuple[list[RagChunkResult], dict[str, Any]]:
        db_rows = list(self.db.scalars(select(DocumentChunk).where(DocumentChunk.kb_id == kb_id)))
        scored: list[RagChunkResult] = []
        for row in db_rows:
            score = lexical_score(query, row.content)
            if score <= 0:
                continue
            scored.append(
                RagChunkResult(
                    chunk_id=row.id,
                    document_id=row.document_id,
                    score=score,
                    source=row.metadata_json.get("source", "database"),
                    content=row.content,
                    metadata=row.metadata_json,
                )
            )
        scored.sort(key=lambda item: item.score, reverse=True)

        reranked = self._try_rerank(query=query, results=scored[: max(top_k * 2, 6)])
        return reranked[:top_k], {
            "db_candidates": len(scored),
            "reranked": len(reranked),
            "strategy": "db-lexical+reranker",
        }

    def _try_rerank(self, *, query: str, results: list[RagChunkResult]) -> list[RagChunkResult]:
        if not results:
            return []
        payload = {"query": query, "passages": [item.content for item in results]}
        try:
            response = httpx.post(
                f"{self.settings.reranker_url}/rerank",
                json=payload,
                headers={"X-Internal-Token": self.settings.internal_service_token},
                timeout=20.0,
            )
            response.raise_for_status()
            scores = response.json()["scores"]
            reranked = [
                item.model_copy(update={"score": float(score)})
                for item, score in zip(results, scores, strict=False)
            ]
            reranked.sort(key=lambda item: item.score, reverse=True)
            return reranked
        except Exception:
            return results

    async def generate_answer(
        self,
        *,
        query: str,
        contexts: list[RagChunkResult],
        model_provider_id: int | None = None,
    ) -> tuple[str, str | None]:
        provider = self._resolve_provider(model_provider_id)
        if provider is None:
            joined = "\n\n".join(item.content for item in contexts[:3])
            return f"未配置可用生成模型，以下为检索摘要：\n\n{joined}", None

        prompt = self._build_prompt(query, contexts)
        if provider.protocol == "openai":
            return await self._call_openai_compatible(provider, prompt)
        return f"当前 provider 协议 {provider.protocol} 暂未启用自动回答，请参考检索结果。", provider.name

    def _resolve_provider(self, provider_id: int | None) -> ModelProvider | None:
        stmt = select(ModelProvider).where(ModelProvider.kind == "generation", ModelProvider.enabled.is_(True))
        if provider_id is not None:
            stmt = stmt.where(ModelProvider.id == provider_id)
        else:
            stmt = stmt.order_by(ModelProvider.priority.asc(), ModelProvider.id.asc())
        return self.db.scalar(stmt)

    @staticmethod
    def _build_prompt(query: str, contexts: list[RagChunkResult]) -> str:
        joined = "\n\n".join(f"[片段{idx + 1}]\n{item.content}" for idx, item in enumerate(contexts[:6]))
        return (
            "你是企业知识库助手。请严格基于给定上下文回答，并在结尾说明是否存在信息不完整。\n\n"
            f"问题：{query}\n\n"
            f"上下文：\n{joined}\n\n"
            "回答："
        )

    async def _call_openai_compatible(self, provider: ModelProvider, prompt: str) -> tuple[str, str]:
        payload = {
            "model": provider.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        }
        headers = {}
        if provider.api_key:
            headers["Authorization"] = f"Bearer {provider.api_key}"
        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(f"{provider.base_url}/chat/completions", json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
        answer = data["choices"][0]["message"]["content"]
        return answer, provider.name

