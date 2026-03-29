"""Unit tests for PDF chunking and classification logic."""
from unittest.mock import MagicMock, patch

import pytest

from app.services.pdf_processor import chunk_document, classify_chunk


# ---------------------------------------------------------------------------
# classify_chunk tests
# ---------------------------------------------------------------------------


def test_classify_chunk_table():
    assert classify_chunk("任意文字", is_table=True) == "table"


def test_classify_chunk_exercise_sets_reps():
    text = "做3组×10次的俯卧撑，每组之间休息60秒。"
    assert classify_chunk(text) == "exercise"


def test_classify_chunk_exercise_numbered_step():
    text = "第三步：双手握杠，缓慢下降至手臂完全伸展。"
    assert classify_chunk(text) == "exercise"


def test_classify_chunk_exercise_keyword():
    text = "引体向上是背部和二头肌的复合训练动作，能有效增强上肢拉力。"
    assert classify_chunk(text) == "exercise"


def test_classify_chunk_definition():
    text = "最大力量：肌肉在单次收缩中所能产生的最大输出力量。"
    assert classify_chunk(text) == "definition"


def test_classify_chunk_definition_shizhi():
    text = "超量恢复是指训练后肌肉能力超过原水平的现象。"
    assert classify_chunk(text) == "definition"


def test_classify_chunk_plain_text():
    text = "本书分为六个部分，每个部分介绍一种基本动作的完整进阶体系。"
    assert classify_chunk(text) == "text"


# ---------------------------------------------------------------------------
# chunk_document tests (mocked file I/O)
# ---------------------------------------------------------------------------


def _make_fake_pages(text: str, page_num: int = 0):
    """Return fake _extract_pages output for one page of text."""
    return [{"page_num": page_num, "text": text, "tables": []}]


def test_chunk_document_returns_list_of_dicts():
    """chunk_document should return a non-empty list of dicts with required keys."""
    long_text = "这是一段训练相关的内容。" * 100  # ~1400 chars, will be split

    with patch("app.services.pdf_processor._extract_pages", return_value=_make_fake_pages(long_text)):
        chunks = chunk_document("/fake/path.pdf", "convict_conditioning.pdf", "training")

    assert isinstance(chunks, list)
    assert len(chunks) > 0
    for chunk in chunks:
        assert "content" in chunk
        assert "chunk_index" in chunk
        assert "chunk_type" in chunk
        assert "chunk_metadata" in chunk


def test_chunk_document_metadata_fields():
    """Each chunk's metadata should include source_book, page_start, content_domain."""
    text = "深蹲是下肢力量训练的核心动作，涉及股四头肌、臀大肌和腘绳肌。" * 20

    with patch("app.services.pdf_processor._extract_pages", return_value=_make_fake_pages(text)):
        chunks = chunk_document("/fake/path.pdf", "training_book.pdf", "training")

    meta = chunks[0]["chunk_metadata"]
    assert meta["source_book"] == "training_book"
    assert meta["page_start"] == 1
    assert meta["content_domain"] == "training"


def test_chunk_document_indices_are_sequential():
    """chunk_index values should be 0, 1, 2, ... with no gaps."""
    text = "内容段落。" * 200  # force multiple chunks

    with patch("app.services.pdf_processor._extract_pages", return_value=_make_fake_pages(text)):
        chunks = chunk_document("/fake/path.pdf", "book.pdf", None)

    indices = [c["chunk_index"] for c in chunks]
    assert indices == list(range(len(chunks)))


def test_chunk_document_table_chunks_classified_as_table():
    """Table content should produce chunks with chunk_type='table'."""
    table_text = "姓名 | 组数 | 次数\n张三 | 3 | 10\n李四 | 4 | 8"
    pages = [{"page_num": 0, "text": "", "tables": [table_text]}]

    with patch("app.services.pdf_processor._extract_pages", return_value=pages):
        chunks = chunk_document("/fake/path.pdf", "book.pdf", "training")

    assert len(chunks) == 1
    assert chunks[0]["chunk_type"] == "table"
    assert chunks[0]["content"] == table_text


def test_chunk_document_empty_pdf_returns_empty_list():
    """A PDF with no extractable text should return an empty list."""
    pages = [{"page_num": 0, "text": "", "tables": []}]

    with patch("app.services.pdf_processor._extract_pages", return_value=pages):
        chunks = chunk_document("/fake/path.pdf", "empty.pdf", None)

    assert chunks == []
