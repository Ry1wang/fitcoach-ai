"""PDF parsing, chunking, and chunk-type classification."""
import re
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF
import pdfplumber
from langchain_text_splitters import RecursiveCharacterTextSplitter

# Patterns that indicate an exercise description chunk
_EXERCISE_PATTERNS = [
    re.compile(r"\d+\s*[组套]\s*[×x×]\s*\d+"),   # e.g. "3组×10次"
    re.compile(r"第[一二三四五六七八九十百\d]+步"),   # "第三步"
    re.compile(r"动作\s*[一二三四五六七八九十\d]"),  # "动作一"
    re.compile(r"^\s*\d+[\.\)、]\s+\S"),             # numbered list item
    re.compile(r"(俯卧撑|引体向上|深蹲|硬拉|卧推|倒立|桥式|举腿)"),
]

# Patterns that indicate a definition chunk
_DEFINITION_PATTERNS = [
    re.compile(r"^[\u4e00-\u9fffA-Za-z\s]{2,20}[：:]"),  # "术语：..."
    re.compile(r"定义[：:]"),
    re.compile(r"是指"),
    re.compile(r"指的是"),
]


def classify_chunk(text: str, is_table: bool = False) -> str:
    """Return chunk_type: 'table' | 'exercise' | 'definition' | 'text'."""
    if is_table:
        return "table"
    sample = text[:300]
    for pat in _EXERCISE_PATTERNS:
        if pat.search(sample):
            return "exercise"
    for pat in _DEFINITION_PATTERNS:
        if pat.search(sample):
            return "definition"
    return "text"


def _extract_pages(file_path: str) -> list[dict[str, Any]]:
    """Extract per-page text (PyMuPDF) and tables (pdfplumber)."""
    text_by_page: dict[int, str] = {}
    with fitz.open(file_path) as pdf:
        for page_num, page in enumerate(pdf):
            text_by_page[page_num] = page.get_text()

    tables_by_page: dict[int, list[str]] = {}
    with pdfplumber.open(file_path) as pdf:
        for page_num, page in enumerate(pdf.pages):
            raw_tables = page.extract_tables()
            if not raw_tables:
                continue
            formatted = []
            for table in raw_tables:
                rows = [
                    " | ".join(str(cell) if cell else "" for cell in row)
                    for row in table
                    if row
                ]
                if rows:
                    formatted.append("\n".join(rows))
            if formatted:
                tables_by_page[page_num] = formatted

    pages = []
    for page_num in sorted(text_by_page.keys()):
        pages.append(
            {
                "page_num": page_num,
                "text": text_by_page[page_num],
                "tables": tables_by_page.get(page_num, []),
            }
        )
    return pages


def chunk_document(
    file_path: str,
    filename: str,
    domain: str | None,
) -> list[dict[str, Any]]:
    """Parse a PDF and return a list of chunk dicts ready for DB insertion.

    Each dict has keys: content, chunk_index, chunk_type, chunk_metadata.
    """
    pages = _extract_pages(file_path)
    source_book = Path(filename).stem

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=200,
        length_function=len,
        separators=["\n\n", "\n", "。", "！", "？", ".", "!", "?", " ", ""],
    )

    chunks: list[dict[str, Any]] = []
    chunk_index = 0

    for page in pages:
        page_num = page["page_num"]
        base_metadata = {
            "source_book": source_book,
            "page_start": page_num + 1,
            "page_end": page_num + 1,
            "content_domain": domain,
        }

        # Table chunks — preserved whole, not split further
        for table_text in page["tables"]:
            if not table_text.strip():
                continue
            chunks.append(
                {
                    "content": table_text,
                    "chunk_index": chunk_index,
                    "chunk_type": "table",
                    "chunk_metadata": {**base_metadata},
                }
            )
            chunk_index += 1

        # Text chunks — split with RecursiveCharacterTextSplitter
        text = page["text"].strip()
        if not text:
            continue

        for chunk_text in splitter.split_text(text):
            if not chunk_text.strip():
                continue
            chunks.append(
                {
                    "content": chunk_text,
                    "chunk_index": chunk_index,
                    "chunk_type": classify_chunk(chunk_text),
                    "chunk_metadata": {**base_metadata},
                }
            )
            chunk_index += 1

    return chunks
