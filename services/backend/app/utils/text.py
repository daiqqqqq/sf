from __future__ import annotations

from collections import Counter
from pathlib import Path
import re


TOKEN_RE = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(text or "")]


def lexical_score(query: str, content: str) -> float:
    query_tokens = tokenize(query)
    content_tokens = tokenize(content)
    if not query_tokens or not content_tokens:
        return 0.0
    query_counts = Counter(query_tokens)
    content_counts = Counter(content_tokens)
    overlap = 0
    lowered_content = content.lower()
    for token, count in query_counts.items():
        if token in content_counts:
            overlap += min(content_counts[token], count)
            continue
        if len(token) > 1 and token in lowered_content:
            overlap += count
    return overlap / max(len(query_tokens), 1)


def chunk_text(text: str, chunk_size: int = 800, chunk_overlap: int = 120) -> list[str]:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return []
    if chunk_size <= 0:
        return [cleaned]
    chunks: list[str] = []
    start = 0
    while start < len(cleaned):
        end = min(start + chunk_size, len(cleaned))
        chunks.append(cleaned[start:end])
        if end == len(cleaned):
            break
        start = max(end - chunk_overlap, start + 1)
    return chunks


def detect_parser_backend(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix in {".pdf", ".docx", ".doc", ".ppt", ".pptx"}:
        return "docling"
    if suffix in {".md", ".markdown"}:
        return "markdown"
    if suffix in {".png", ".jpg", ".jpeg"}:
        return "ocr"
    return "native"
