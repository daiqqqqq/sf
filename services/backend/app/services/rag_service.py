from __future__ import annotations

import logging
from typing import Any

import httpx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import Document, DocumentChunk, KnowledgeBase, ModelProvider
from app.schemas.api import RagChunkResult
from app.utils.text import chunk_text, lexical_score

try:
    from haystack import Document as HaystackDocument
    from haystack import Pipeline
    from haystack.components.preprocessors import DocumentCleaner
    from haystack.components.retrievers.in_memory import InMemoryBM25Retriever
    from haystack.document_stores.in_memory import InMemoryDocumentStore
except Exception:  # pragma: no cover - optional dependency behavior
    HaystackDocument = Pipeline = DocumentCleaner = InMemoryBM25Retriever = InMemoryDocumentStore = None  # type: ignore[assignment]


logger = logging.getLogger(__name__)


class RagService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()

    def ingest_document(self, *, document_id: int, kb_id: int, text: str) -> int:
        kb = self.db.get(KnowledgeBase, kb_id)
        if kb is None:
            raise ValueError(f"Knowledge base {kb_id} not found")

        prepared_text = self._clean_text_with_haystack(text)
        self.db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document_id))
        chunks = chunk_text(prepared_text, kb.chunk_size, kb.chunk_overlap)

        total = 0
        for index, chunk in enumerate(chunks):
            item = DocumentChunk(
                document_id=document_id,
                kb_id=kb_id,
                chunk_index=index,
                content=chunk,
                score_hint=len(chunk),
                metadata_json={"source": "haystack", "chunk_index": index},
            )
            self.db.add(item)
            total += 1
        self.db.commit()

        document = self.db.get(Document, document_id)
        if document is not None:
            document.extracted_text = prepared_text
            document.status = "indexed"
            self.db.commit()

        return total

    def search(self, *, kb_id: int, query: str, top_k: int = 6) -> tuple[list[RagChunkResult], dict[str, Any]]:
        db_rows = list(self.db.scalars(select(DocumentChunk).where(DocumentChunk.kb_id == kb_id)))
        if not db_rows:
            return [], {"db_candidates": 0, "reranked": 0, "strategy": "haystack-bm25+reranker"}

        haystack_results = self._search_with_haystack(query=query, rows=db_rows, top_k=top_k)
        candidates = haystack_results if haystack_results else self._fallback_lexical_results(query=query, rows=db_rows)
        reranked = self._try_rerank(
            query=query,
            results=candidates[: max(top_k * self.settings.haystack_candidate_multiplier, 6)],
        )
        strategy = "haystack-bm25+reranker" if haystack_results else "db-lexical+reranker"
        return reranked[:top_k], {
            "db_candidates": len(db_rows),
            "reranked": len(reranked),
            "strategy": strategy,
        }

    def _clean_text_with_haystack(self, text: str) -> str:
        cleaned = " ".join((text or "").split()).strip()
        if not cleaned or DocumentCleaner is None or HaystackDocument is None:
            return cleaned
        try:
            cleaner = DocumentCleaner()
            result = cleaner.run(documents=[HaystackDocument(content=cleaned)])
            documents = result.get("documents", [])
            if documents and documents[0].content:
                return documents[0].content.strip()
        except Exception:
            logger.exception("Haystack cleaning failed, falling back to basic normalization")
        return cleaned

    def _search_with_haystack(self, *, query: str, rows: list[DocumentChunk], top_k: int) -> list[RagChunkResult]:
        if (
            HaystackDocument is None
            or InMemoryDocumentStore is None
            or InMemoryBM25Retriever is None
            or Pipeline is None
        ):
            return []
        try:
            document_store = InMemoryDocumentStore()
            candidate_count = max(top_k * self.settings.haystack_candidate_multiplier, 6)
            haystack_documents = [
                HaystackDocument(
                    id=str(row.id),
                    content=row.content,
                    meta={
                        "chunk_id": row.id,
                        "document_id": row.document_id,
                        "source": row.metadata_json.get("source", "haystack"),
                        **row.metadata_json,
                    },
                )
                for row in rows
            ]
            document_store.write_documents(haystack_documents)

            retriever = InMemoryBM25Retriever(document_store=document_store, top_k=candidate_count)
            pipeline = Pipeline()
            pipeline.add_component("retriever", retriever)
            response = pipeline.run({"retriever": {"query": query}})
            documents = response.get("retriever", {}).get("documents", [])

            results: list[RagChunkResult] = []
            for item in documents:
                metadata = dict(item.meta or {})
                chunk_id = int(metadata.get("chunk_id", item.id))
                score = float(item.score or 0.0)
                metadata["haystack_score"] = score
                results.append(
                    RagChunkResult(
                        chunk_id=chunk_id,
                        document_id=int(metadata.get("document_id", 0)),
                        score=score,
                        source=str(metadata.get("source", "haystack")),
                        content=item.content,
                        metadata=metadata,
                    )
                )
            return results
        except Exception:
            logger.exception("Haystack retrieval failed, falling back to lexical search")
            return []

    def _fallback_lexical_results(self, *, query: str, rows: list[DocumentChunk]) -> list[RagChunkResult]:
        scored: list[RagChunkResult] = []
        for row in rows:
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
        return scored

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
            logger.exception("Reranker unavailable, returning retriever ordering")
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
