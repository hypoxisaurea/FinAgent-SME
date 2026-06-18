from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

from backend.rag.ingest_industry_docs import (
    add_chunks_without_duplicates,
    build_document_chunks,
    chunk_text,
    ingest_industry_docs,
    parse_industry_doc_filename,
)


class _FakeCollection:
    def __init__(self, existing_ids: set[str] | None = None) -> None:
        self.existing_ids = existing_ids or set()
        self.added: dict[str, Any] = {}

    def get(self, ids: list[str]) -> dict[str, list[str]]:
        return {"ids": [value for value in ids if value in self.existing_ids]}

    def add(
        self,
        *,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        self.added = {
            "ids": ids,
            "documents": documents,
            "metadatas": metadatas,
        }


def test_parse_industry_doc_filename_extracts_metadata() -> None:
    metadata = parse_industry_doc_filename(Path("2025 건설업 신용평가방법론.pdf"))

    assert metadata.year == 2025
    assert metadata.industry_name == "건설업"
    assert metadata.ksic_code == "F 건설업"
    assert metadata.sub_sector == "건설"


def test_parse_industry_doc_filename_handles_alias() -> None:
    metadata = parse_industry_doc_filename(Path("2025 의류(패션, 의류제조)업 신용평가방법론.pdf"))

    assert metadata.industry_name == "의류업"
    assert metadata.ksic_code == "C 제조업"
    assert metadata.sub_sector == "의류"


def test_chunk_text_uses_overlap() -> None:
    chunks = chunk_text("abcdefghij", chunk_size=5, overlap=2)

    assert chunks == ["abcde", "defgh", "ghij"]


def test_build_document_chunks_adds_source_metadata() -> None:
    metadata = parse_industry_doc_filename(Path("2025 철강업 신용평가방법론.pdf"))
    chunks = build_document_chunks(
        [(3, "철강 산업은 원재료 가격과 수요 변동에 민감합니다.")],
        metadata,
        chunk_size=20,
        overlap=5,
    )

    assert chunks
    assert chunks[0].metadata["filename"] == "2025 철강업 신용평가방법론.pdf"
    assert chunks[0].metadata["page"] == 3
    assert chunks[0].metadata["industry_name"] == "철강업"
    assert chunks[0].metadata["ksic_code"] == "C 제조업"
    assert chunks[0].metadata["sub_sector"] == "철강"


def test_add_chunks_without_duplicates_skips_existing_ids() -> None:
    metadata = parse_industry_doc_filename(Path("2025 호텔업 평가방법론.pdf"))
    chunks = build_document_chunks(
        [(1, "호텔업은 객실 가동률과 평균 객단가가 중요합니다.")],
        metadata,
        chunk_size=100,
        overlap=10,
    )
    collection = _FakeCollection(existing_ids={chunks[0].id})

    inserted, skipped = add_chunks_without_duplicates(collection, chunks)

    assert inserted == 0
    assert skipped == 1
    assert collection.added == {}


def test_ingest_industry_docs_continues_after_file_error() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / "2025 건설업 신용평가방법론.pdf").touch()
        (tmppath / "알수없는파일.pdf").touch()

        collection = _FakeCollection()

        with patch(
            "backend.rag.ingest_industry_docs.extract_pdf_pages",
            return_value=[(1, "건설업 신용평가 주요 내용 및 평가요소 기술입니다.")],
        ):
            stats = ingest_industry_docs(docs_dir=tmppath, collection=collection)

    assert stats["errors"] == 1
    assert stats["documents"] == 1
    assert stats["chunks"] >= 1
    assert stats["inserted"] >= 1
