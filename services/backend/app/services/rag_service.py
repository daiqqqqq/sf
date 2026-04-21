from __future__ import annotations

import logging
from time import perf_counter
from typing import Any
from uuid import uuid4

import httpx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ExternalServiceAppError, NotFoundAppError, ValidationAppError
from app.core.logging_utils import log_event
from app.core.metrics import (
    MODEL_REQUESTS_TOTAL,
    MODEL_REQUEST_DURATION_SECONDS,
    RAG_CANDIDATE_RESULTS,
    RAG_DEGRADED_TOTAL,
    RAG_QUERIES_TOTAL,
)
from app.models.entities import Document, DocumentChunk, KnowledgeBase, ModelProvider
from app.schemas.api import RagChunkResult
from app.utils.text import chunk_text

try:
    from elasticsearch import Elasticsearch
    from elasticsearch.helpers import bulk as es_bulk
except Exception:  # pragma: no cover - optional dependency behavior
    Elasticsearch = None  # type: ignore[assignment]
    es_bulk = None  # type: ignore[assignment]

try:
    from pymilvus import Collection, CollectionSchema, DataType, FieldSchema, connections, utility
except Exception:  # pragma: no cover - optional dependency behavior
    Collection = CollectionSchema = DataType = FieldSchema = connections = utility = None  # type: ignore[assignment]


logger = logging.getLogger(__name__)


class RagService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()

    def ingest_document(self, *, document_id: int, kb_id: int, text: str) -> tuple[int, dict[str, int]]:
        kb = self.db.get(KnowledgeBase, kb_id)
        if kb is None:
            raise NotFoundAppError(f"知识库 {kb_id} 不存在。")
        document = self.db.get(Document, document_id)
        if document is None:
            raise NotFoundAppError(f"文档 {document_id} 不存在。")

        prepared_text = self._clean_text(text)
        chunks = chunk_text(prepared_text, kb.chunk_size, kb.chunk_overlap)
        if not chunks:
            raise ExternalServiceAppError("文档解析结果为空，无法建立索引。", service="rag-engine")

        embeddings = self._embed_texts(chunks)
        if len(embeddings) != len(chunks):
            raise ExternalServiceAppError("向量化返回数量与切块数量不一致。", service="embedding")

        old_chunk_keys = list(self.db.scalars(select(DocumentChunk.chunk_key).where(DocumentChunk.document_id == document_id)))

        self._delete_elasticsearch_document(document_id)
        self._delete_milvus_by_document(document_id)
        self.db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document_id))
        self.db.flush()

        indexed_backends = {"postgres": 0, "elasticsearch": 0, "milvus": 0}
        chunk_rows: list[DocumentChunk] = []
        try:
            for index, chunk in enumerate(chunks):
                chunk_key = self._chunk_key(kb_id, document_id, index)
                row = DocumentChunk(
                    document_id=document_id,
                    kb_id=kb_id,
                    chunk_key=chunk_key,
                    chunk_index=index,
                    content=chunk,
                    score_hint=len(chunk),
                    metadata_json={
                        "source": "hybrid",
                        "document_id": document_id,
                        "kb_id": kb_id,
                        "chunk_index": index,
                        "es_doc_id": chunk_key,
                        "milvus_pk": chunk_key,
                    },
                )
                self.db.add(row)
                chunk_rows.append(row)
            self.db.flush()
            indexed_backends["postgres"] = len(chunk_rows)

            self._index_elasticsearch(chunk_rows)
            indexed_backends["elasticsearch"] = len(chunk_rows)

            self._upsert_milvus(chunk_rows, embeddings)
            indexed_backends["milvus"] = len(chunk_rows)

            document.extracted_text = prepared_text
            document.status = "indexed"
            document.error_message = ""
            self.db.commit()
            return len(chunk_rows), indexed_backends
        except Exception as exc:
            self.db.rollback()
            self._cleanup_failed_external_index(
                chunk_keys=[self._chunk_key(kb_id, document_id, idx) for idx in range(len(chunks))],
                document_id=document_id,
                old_chunk_keys=old_chunk_keys,
            )
            if isinstance(exc, ExternalServiceAppError):
                raise
            raise ExternalServiceAppError(
                "混合索引写入失败，已终止本次文档入库。",
                service="hybrid-index",
                details={"document_id": document_id, "error": str(exc)},
            ) from exc

    def search(self, *, kb_id: int, query: str, top_k: int = 6) -> tuple[list[RagChunkResult], dict[str, Any]]:
        if not query.strip():
            raise ValidationAppError("查询内容不能为空。")
        if self.db.get(KnowledgeBase, kb_id) is None:
            raise NotFoundAppError(f"知识库 {kb_id} 不存在。")
        warnings: list[str] = []
        used_backends: list[str] = []

        lexical_results: list[RagChunkResult] = []
        vector_results: list[RagChunkResult] = []

        try:
            lexical_results = self._search_elasticsearch(query=query, kb_id=kb_id, limit=self.settings.elasticsearch_candidate_count)
            used_backends.append("elasticsearch")
        except Exception as exc:
            warnings.append(f"Elasticsearch 检索降级：{exc}")
            RAG_DEGRADED_TOTAL.labels(backend="elasticsearch").inc()

        try:
            vector_results = self._search_milvus(query=query, kb_id=kb_id, limit=self.settings.milvus_candidate_count)
            used_backends.append("milvus")
        except Exception as exc:
            warnings.append(f"Milvus 检索降级：{exc}")
            RAG_DEGRADED_TOTAL.labels(backend="milvus").inc()

        if not lexical_results and not vector_results:
            RAG_QUERIES_TOTAL.labels(status="failed").inc()
            raise ExternalServiceAppError("词法检索和向量检索均不可用。", service="hybrid-retrieval")

        RAG_CANDIDATE_RESULTS.labels(stage="lexical").observe(len(lexical_results))
        RAG_CANDIDATE_RESULTS.labels(stage="vector").observe(len(vector_results))

        fused = self._rrf_fuse(lexical_results, vector_results)
        if not fused:
            RAG_QUERIES_TOTAL.labels(status="failed").inc()
            raise ExternalServiceAppError("当前知识库没有可用召回结果。", service="hybrid-retrieval")
        RAG_CANDIDATE_RESULTS.labels(stage="fusion").observe(len(fused))

        reranked = self._try_rerank(query=query, results=fused[: max(top_k * 3, 10)])
        RAG_CANDIDATE_RESULTS.labels(stage="rerank").observe(len(reranked))
        RAG_QUERIES_TOTAL.labels(status="degraded" if warnings else "success").inc()

        debug = {
            "lexical_hits": len(lexical_results),
            "vector_hits": len(vector_results),
            "fusion_scores": {item.metadata.get("chunk_key", str(item.chunk_id)): item.metadata.get("fusion_score", item.score) for item in fused[:20]},
            "rerank_scores": {item.metadata.get("chunk_key", str(item.chunk_id)): item.score for item in reranked[:20]},
            "warnings": warnings,
            "used_backends": used_backends,
        }
        return reranked[:top_k], debug

    def readiness(self) -> dict[str, str]:
        self._es_client().info()
        alias = self._milvus_alias()
        if connections is None or utility is None:
            raise ExternalServiceAppError("Milvus 客户端不可用。", service="milvus")
        connections.connect(alias=alias, uri=self.settings.milvus_uri, token=self.settings.milvus_token or None)
        try:
            utility.list_collections(using=alias)
        finally:
            connections.disconnect(alias=alias)
        return {"status": "ready"}

    async def generate_answer(
        self,
        *,
        query: str,
        contexts: list[RagChunkResult],
        model_provider_id: int | None = None,
    ) -> tuple[str, str | None]:
        provider = self._resolve_provider(model_provider_id, kind="generation")
        if provider is None:
            joined = "\n\n".join(item.content for item in contexts[:3])
            return f"当前没有可用的生成模型，以下为检索摘要：\n\n{joined}", None

        prompt = self._build_prompt(query, contexts)
        if provider.protocol == "openai":
            return await self._call_openai_compatible(provider, prompt)
        return f"当前 provider 协议 {provider.protocol} 暂未启用自动回答，请参考检索结果。", provider.name

    def _clean_text(self, text: str) -> str:
        return " ".join((text or "").split()).strip()

    def _resolve_provider(self, provider_id: int | None, *, kind: str) -> ModelProvider | None:
        stmt = select(ModelProvider).where(ModelProvider.kind == kind, ModelProvider.enabled.is_(True))
        if provider_id is not None:
            stmt = stmt.where(ModelProvider.id == provider_id)
        else:
            stmt = stmt.order_by(ModelProvider.priority.asc(), ModelProvider.id.asc())
        return self.db.scalar(stmt)

    def _embed_texts(self, texts: list[str]) -> list[list[float]]:
        provider = self._resolve_provider(None, kind="embedding")
        if provider is None:
            raise ExternalServiceAppError("未配置可用的 embedding provider。", service="embedding")
        if provider.protocol != "ollama":
            raise ExternalServiceAppError(
                f"当前 embedding provider 协议 {provider.protocol} 暂不支持。",
                service="embedding",
            )

        payload = {"model": provider.model_name, "input": texts}
        try:
            response = httpx.post(f"{provider.base_url}/api/embed", json=payload, timeout=120.0)
            response.raise_for_status()
            data = response.json()
        except Exception:
            embeddings: list[list[float]] = []
            for item in texts:
                response = httpx.post(
                    f"{provider.base_url}/api/embeddings",
                    json={"model": provider.model_name, "prompt": item},
                    timeout=120.0,
                )
                response.raise_for_status()
                fallback_data = response.json()
                vector = fallback_data.get("embedding")
                if not vector:
                    raise ExternalServiceAppError("Embedding 接口没有返回向量结果。", service="embedding")
                embeddings.append(list(map(float, vector)))
            return embeddings
        embeddings = data.get("embeddings")
        if not embeddings:
            raise ExternalServiceAppError("Embedding 接口没有返回向量结果。", service="embedding")
        if embeddings and isinstance(embeddings[0], (int, float)):
            return [list(map(float, embeddings))]
        return [list(map(float, vector)) for vector in embeddings]

    def _es_client(self):
        if Elasticsearch is None:
            raise ExternalServiceAppError("Elasticsearch 客户端不可用。", service="elasticsearch")
        return Elasticsearch(self.settings.elasticsearch_url)

    def _ensure_es_index(self) -> None:
        client = self._es_client()
        if client.indices.exists(index=self.settings.elasticsearch_index):
            return
        client.indices.create(
            index=self.settings.elasticsearch_index,
            mappings={
                "properties": {
                    "chunk_key": {"type": "keyword"},
                    "chunk_id": {"type": "integer"},
                    "kb_id": {"type": "integer"},
                    "document_id": {"type": "integer"},
                    "chunk_index": {"type": "integer"},
                    "content": {"type": "text"},
                }
            },
        )

    def _index_elasticsearch(self, rows: list[DocumentChunk]) -> None:
        self._ensure_es_index()
        client = self._es_client()
        if es_bulk is None:
            raise ExternalServiceAppError("Elasticsearch bulk helper 不可用。", service="elasticsearch")
        actions = [
            {
                "_index": self.settings.elasticsearch_index,
                "_id": row.chunk_key,
                "_source": {
                    "chunk_key": row.chunk_key,
                    "chunk_id": row.id,
                    "kb_id": row.kb_id,
                    "document_id": row.document_id,
                    "chunk_index": row.chunk_index,
                    "content": row.content,
                },
            }
            for row in rows
        ]
        success, errors = es_bulk(client, actions, refresh="wait_for", raise_on_error=False)
        if errors:
            raise ExternalServiceAppError(
                "Elasticsearch bulk 索引存在失败项。",
                service="elasticsearch",
                details={"success": success, "errors": errors[:3]},
            )

    def _search_elasticsearch(self, *, query: str, kb_id: int, limit: int) -> list[RagChunkResult]:
        self._ensure_es_index()
        client = self._es_client()
        response = client.search(
            index=self.settings.elasticsearch_index,
            size=limit,
            query={
                "bool": {
                    "must": [{"multi_match": {"query": query, "fields": ["content"]}}],
                    "filter": [{"term": {"kb_id": kb_id}}],
                }
            },
        )
        results: list[RagChunkResult] = []
        for hit in response.get("hits", {}).get("hits", []):
            source = hit.get("_source", {})
            score = float(hit.get("_score") or 0.0)
            results.append(
                RagChunkResult(
                    chunk_id=int(source["chunk_id"]),
                    document_id=int(source["document_id"]),
                    score=score,
                    source="elasticsearch",
                    content=source["content"],
                    metadata={
                        "chunk_key": source["chunk_key"],
                        "chunk_index": source["chunk_index"],
                        "lexical_score": score,
                    },
                )
            )
        return results

    def _delete_elasticsearch_document(self, document_id: int) -> None:
        try:
            client = self._es_client()
            if not client.indices.exists(index=self.settings.elasticsearch_index):
                return
            client.delete_by_query(
                index=self.settings.elasticsearch_index,
                body={"query": {"term": {"document_id": document_id}}},
                refresh=True,
                conflicts="proceed",
            )
        except ExternalServiceAppError:
            raise
        except Exception as exc:
            raise ExternalServiceAppError("删除 Elasticsearch 旧索引失败。", service="elasticsearch", details={"error": str(exc)}) from exc

    def _milvus_alias(self) -> str:
        return f"rag-{uuid4().hex[:8]}"

    def _ensure_milvus_collection(self, vector_dim: int) -> None:
        if Collection is None or connections is None or utility is None or FieldSchema is None or CollectionSchema is None or DataType is None:
            raise ExternalServiceAppError("Milvus 客户端不可用。", service="milvus")
        alias = self._milvus_alias()
        connections.connect(alias=alias, uri=self.settings.milvus_uri, token=self.settings.milvus_token or None)
        try:
            if utility.has_collection(self.settings.milvus_collection, using=alias):
                return
            schema = CollectionSchema(
                fields=[
                    FieldSchema(name="chunk_key", dtype=DataType.VARCHAR, is_primary=True, max_length=128),
                    FieldSchema(name="chunk_id", dtype=DataType.INT64),
                    FieldSchema(name="kb_id", dtype=DataType.INT64),
                    FieldSchema(name="document_id", dtype=DataType.INT64),
                    FieldSchema(name="chunk_index", dtype=DataType.INT64),
                    FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=vector_dim),
                ],
                description="RAG chunk embeddings",
            )
            collection = Collection(name=self.settings.milvus_collection, schema=schema, using=alias)
            collection.create_index("embedding", {"index_type": "AUTOINDEX", "metric_type": "COSINE", "params": {}})
        finally:
            connections.disconnect(alias)

    def _upsert_milvus(self, rows: list[DocumentChunk], embeddings: list[list[float]]) -> None:
        if not rows:
            return
        self._ensure_milvus_collection(len(embeddings[0]))
        alias = self._milvus_alias()
        connections.connect(alias=alias, uri=self.settings.milvus_uri, token=self.settings.milvus_token or None)
        try:
            collection = Collection(self.settings.milvus_collection, using=alias)
            collection.insert(
                [
                    [row.chunk_key for row in rows],
                    [row.id for row in rows],
                    [row.kb_id for row in rows],
                    [row.document_id for row in rows],
                    [row.chunk_index for row in rows],
                    embeddings,
                ]
            )
            collection.flush()
        except Exception as exc:
            raise ExternalServiceAppError("写入 Milvus 向量索引失败。", service="milvus", details={"error": str(exc)}) from exc
        finally:
            connections.disconnect(alias)

    def _search_milvus(self, *, query: str, kb_id: int, limit: int) -> list[RagChunkResult]:
        query_embedding = self._embed_texts([query])[0]
        alias = self._milvus_alias()
        connections.connect(alias=alias, uri=self.settings.milvus_uri, token=self.settings.milvus_token or None)
        try:
            if not utility.has_collection(self.settings.milvus_collection, using=alias):
                return []
            collection = Collection(self.settings.milvus_collection, using=alias)
            collection.load()
            hits = collection.search(
                data=[query_embedding],
                anns_field="embedding",
                param={"metric_type": "COSINE", "params": {}},
                limit=limit,
                expr=f"kb_id == {kb_id}",
                output_fields=["chunk_key", "chunk_id", "document_id", "chunk_index"],
            )
            hit_rows = hits[0] if hits else []
            if not hit_rows:
                return []
            chunk_ids = [int(hit.entity.get("chunk_id")) for hit in hit_rows]
            db_rows = {
                row.id: row
                for row in self.db.scalars(select(DocumentChunk).where(DocumentChunk.id.in_(chunk_ids)))
            }
            results: list[RagChunkResult] = []
            for hit in hit_rows:
                chunk_id = int(hit.entity.get("chunk_id"))
                row = db_rows.get(chunk_id)
                if row is None:
                    continue
                score = float(hit.score)
                results.append(
                    RagChunkResult(
                        chunk_id=row.id,
                        document_id=row.document_id,
                        score=score,
                        source="milvus",
                        content=row.content,
                        metadata={
                            "chunk_key": row.chunk_key,
                            "chunk_index": row.chunk_index,
                            "vector_score": score,
                        },
                    )
                )
            return results
        except Exception as exc:
            raise ExternalServiceAppError("Milvus 检索失败。", service="milvus", details={"error": str(exc)}) from exc
        finally:
            connections.disconnect(alias)

    def _delete_milvus_by_document(self, document_id: int) -> None:
        if Collection is None or connections is None or utility is None:
            raise ExternalServiceAppError("Milvus 客户端不可用。", service="milvus")
        alias = self._milvus_alias()
        connections.connect(alias=alias, uri=self.settings.milvus_uri, token=self.settings.milvus_token or None)
        try:
            if not utility.has_collection(self.settings.milvus_collection, using=alias):
                return
            collection = Collection(self.settings.milvus_collection, using=alias)
            collection.delete(expr=f"document_id == {document_id}")
        except Exception as exc:
            raise ExternalServiceAppError("删除 Milvus 旧索引失败。", service="milvus", details={"error": str(exc)}) from exc
        finally:
            connections.disconnect(alias)

    def _cleanup_failed_external_index(self, *, chunk_keys: list[str], document_id: int, old_chunk_keys: list[str]) -> None:
        try:
            self._delete_elasticsearch_document(document_id)
        except Exception as exc:  # pragma: no cover - cleanup best effort
            log_event(logger, "cleanup_failed", backend="elasticsearch", error=str(exc))
        try:
            self._delete_milvus_by_document(document_id)
        except Exception as exc:  # pragma: no cover - cleanup best effort
            log_event(logger, "cleanup_failed", backend="milvus", error=str(exc))
        if old_chunk_keys:
            log_event(logger, "legacy_chunks_replaced", chunk_keys=old_chunk_keys[:5], total=len(old_chunk_keys))

    def _rrf_fuse(self, lexical_results: list[RagChunkResult], vector_results: list[RagChunkResult]) -> list[RagChunkResult]:
        merged: dict[str, RagChunkResult] = {}
        for source_results in (lexical_results, vector_results):
            for rank, item in enumerate(source_results, start=1):
                chunk_key = str(item.metadata.get("chunk_key", item.chunk_id))
                fusion_score = 1.0 / (self.settings.rrf_k + rank)
                existing = merged.get(chunk_key)
                if existing is None:
                    metadata = dict(item.metadata)
                    metadata["fusion_score"] = fusion_score
                    merged[chunk_key] = item.model_copy(update={"score": fusion_score, "source": "hybrid", "metadata": metadata})
                    continue
                metadata = dict(existing.metadata)
                metadata.update(item.metadata)
                metadata["fusion_score"] = float(metadata.get("fusion_score", 0.0)) + fusion_score
                merged[chunk_key] = existing.model_copy(update={"score": metadata["fusion_score"], "metadata": metadata})
        fused = list(merged.values())
        fused.sort(key=lambda item: item.score, reverse=True)
        return fused

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
            reranked = []
            for item, score in zip(results, scores, strict=False):
                metadata = dict(item.metadata)
                metadata["rerank_score"] = float(score)
                reranked.append(item.model_copy(update={"score": float(score), "metadata": metadata}))
            reranked.sort(key=lambda item: item.score, reverse=True)
            return reranked
        except Exception as exc:
            log_event(logger, "reranker_degraded", error=str(exc))
            RAG_DEGRADED_TOTAL.labels(backend="reranker").inc()
            return results

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
        started = perf_counter()
        try:
            async with httpx.AsyncClient(timeout=90.0) as client:
                response = await client.post(f"{provider.base_url}/chat/completions", json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
            answer = data["choices"][0]["message"]["content"]
            MODEL_REQUESTS_TOTAL.labels(provider=provider.name, status="success").inc()
            MODEL_REQUEST_DURATION_SECONDS.labels(provider=provider.name).observe(perf_counter() - started)
            return answer, provider.name
        except Exception as exc:
            MODEL_REQUESTS_TOTAL.labels(provider=provider.name, status="failed").inc()
            MODEL_REQUEST_DURATION_SECONDS.labels(provider=provider.name).observe(perf_counter() - started)
            raise ExternalServiceAppError(
                "生成模型调用失败。",
                service=provider.name,
                details={"error": str(exc)},
            ) from exc

    @staticmethod
    def _chunk_key(kb_id: int, document_id: int, chunk_index: int) -> str:
        return f"{kb_id}:{document_id}:{chunk_index}"
