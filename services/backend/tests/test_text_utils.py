from app.utils.text import chunk_text, detect_parser_backend, lexical_score, tokenize


def test_tokenize_supports_chinese_and_ascii() -> None:
    tokens = tokenize("RAG 平台 supports 中文 tokens")
    assert "rag" in tokens
    assert "平台" in tokens
    assert "supports" in tokens


def test_chunk_text_respects_overlap() -> None:
    text = "abcdefghij" * 120
    chunks = chunk_text(text, chunk_size=100, chunk_overlap=20)
    assert len(chunks) > 1
    assert chunks[0][-20:] == chunks[1][:20]


def test_lexical_score_rewards_overlap() -> None:
    high = lexical_score("容器 管理 平台", "这是一个容器管理平台")
    low = lexical_score("容器 管理 平台", "这里讨论向量数据库")
    assert high > low


def test_detect_parser_backend() -> None:
    assert detect_parser_backend("report.pdf") == "tika"
    assert detect_parser_backend("notes.md") == "markdown"
    assert detect_parser_backend("scan.jpg") == "ocr"
    assert detect_parser_backend("plain.txt") == "native"

