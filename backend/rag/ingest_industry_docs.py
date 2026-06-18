from __future__ import annotations

import hashlib
import logging
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.rag.chroma_client import get_industry_collection

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DOCS_DIR = BACKEND_DIR / "rag_docs" / "industry_methodology"
SOURCE_TYPE = "credit_rating_methodology"

INDUSTRY_METHODOLOGY_MAPPING: dict[str, dict[str, str]] = {
    "건설업": {"ksic_code": "F 건설업", "sub_sector": "건설"},
    "반도체업": {"ksic_code": "C 제조업", "sub_sector": "반도체"},
    "조선업": {"ksic_code": "C 제조업", "sub_sector": "조선"},
    "철강업": {"ksic_code": "C 제조업", "sub_sector": "철강"},
    "항공운송업": {"ksic_code": "H 운수 및 창고업", "sub_sector": "항공운송"},
    "정유업": {"ksic_code": "C 제조업", "sub_sector": "정유"},
    "호텔업": {"ksic_code": "I 숙박 및 음식점업", "sub_sector": "호텔"},
    "SI업": {"ksic_code": "J 정보통신업", "sub_sector": "SI"},
    "레미콘업": {"ksic_code": "C 제조업", "sub_sector": "레미콘"},
    "방산업": {"ksic_code": "C 제조업", "sub_sector": "방산"},
    "의류업": {"ksic_code": "C 제조업", "sub_sector": "의류"},
}

_FILENAME_ALIASES: tuple[tuple[str, str], ...] = (
    ("의류", "의류업"),
    ("SI", "SI업"),
)


@dataclass(frozen=True)
class IndustryDocumentMetadata:
    """업종 신용평가방법론 PDF 파일명에서 추출한 메타데이터."""

    filename: str
    year: int
    industry_name: str
    ksic_code: str
    sub_sector: str
    source_type: str = SOURCE_TYPE


@dataclass(frozen=True)
class DocumentChunk:
    """Chroma에 삽입할 준비가 완료된 단일 청크."""

    id: str
    text: str
    metadata: dict[str, Any]


def normalize_filename(filename: str) -> str:
    """파싱 전 한글 파일명을 NFC로 정규화한다."""
    return unicodedata.normalize("NFC", filename)


def parse_industry_doc_filename(path: Path | str) -> IndustryDocumentMetadata:
    """PDF 파일명에서 연도, 업종명, KSIC 코드, 세부 업종을 추출한다."""
    filename = normalize_filename(Path(path).name)
    year_match = re.search(r"(20\d{2})", filename)
    if year_match is None:
        raise ValueError(f"평가방법론 PDF 파일명에서 연도를 찾을 수 없습니다: {filename}")

    industry_name = _find_industry_name(filename)
    mapping = INDUSTRY_METHODOLOGY_MAPPING[industry_name]
    return IndustryDocumentMetadata(
        filename=filename,
        year=int(year_match.group(1)),
        industry_name=industry_name,
        ksic_code=mapping["ksic_code"],
        sub_sector=mapping["sub_sector"],
    )


def chunk_text(text: str, chunk_size: int = 1200, overlap: int = 200) -> list[str]:
    """추출된 PDF 텍스트를 오버랩 방식으로 분할한다."""
    normalized_text = re.sub(r"\s+", " ", text).strip()
    if not normalized_text:
        return []
    if chunk_size <= 0:
        raise ValueError("chunk_size는 1 이상이어야 합니다.")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap은 0 이상 chunk_size 미만이어야 합니다.")

    chunks: list[str] = []
    start = 0
    while start < len(normalized_text):
        end = min(start + chunk_size, len(normalized_text))
        chunks.append(normalized_text[start:end])
        if end == len(normalized_text):
            break
        start = end - overlap
    return chunks


def build_document_chunks(
    pages: list[tuple[int, str]],
    metadata: IndustryDocumentMetadata,
    *,
    chunk_size: int = 1200,
    overlap: int = 200,
) -> list[DocumentChunk]:
    """페이지 단위 PDF 텍스트로 결정론적 Chroma 문서를 생성한다."""
    document_chunks: list[DocumentChunk] = []
    for page_number, page_text in pages:
        for chunk_index, chunk in enumerate(
            chunk_text(page_text, chunk_size=chunk_size, overlap=overlap)
        ):
            chunk_hash = hashlib.sha256(chunk.encode("utf-8")).hexdigest()[:16]
            chunk_id = (
                f"{metadata.filename}:{page_number}:{chunk_index}:{chunk_hash}"
            )
            document_chunks.append(
                DocumentChunk(
                    id=chunk_id,
                    text=chunk,
                    metadata={
                        "filename": metadata.filename,
                        "page": page_number,
                        "chunk_index": chunk_index,
                        "industry_name": metadata.industry_name,
                        "year": metadata.year,
                        "ksic_code": metadata.ksic_code,
                        "sub_sector": metadata.sub_sector,
                        "source_type": metadata.source_type,
                    },
                )
            )
    return document_chunks


def extract_pdf_pages(pdf_path: Path | str) -> list[tuple[int, str]]:
    """PDF에서 1-indexed 페이지 번호와 텍스트 튜플 목록을 추출한다."""
    try:
        import pdfplumber
    except ImportError as exc:
        raise RuntimeError("pdfplumber is required for industry PDF ingest") from exc

    pages: list[tuple[int, str]] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for index, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if text.strip():
                pages.append((index, text))
    return pages


def ingest_industry_docs(
    docs_dir: Path | str = DEFAULT_DOCS_DIR,
    *,
    collection: Any | None = None,
    chunk_size: int = 1200,
    overlap: int = 200,
) -> dict[str, int]:
    """업종 신용평가방법론 PDF를 Chroma industry_knowledge 컬렉션에 적재한다."""
    resolved_docs_dir = Path(docs_dir)
    if not resolved_docs_dir.exists():
        raise FileNotFoundError(f"RAG 문서 디렉토리를 찾을 수 없습니다: {resolved_docs_dir}")

    target_collection = collection or get_industry_collection()
    stats = {
        "documents": 0,
        "chunks": 0,
        "inserted": 0,
        "skipped": 0,
        "errors": 0,
    }

    for pdf_path in sorted(resolved_docs_dir.glob("*.pdf")):
        try:
            metadata = parse_industry_doc_filename(pdf_path)
            pages = extract_pdf_pages(pdf_path)
            chunks = build_document_chunks(
                pages,
                metadata,
                chunk_size=chunk_size,
                overlap=overlap,
            )
            inserted, skipped = add_chunks_without_duplicates(target_collection, chunks)
            stats["documents"] += 1
            stats["chunks"] += len(chunks)
            stats["inserted"] += inserted
            stats["skipped"] += skipped
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "industry_rag_ingest_file_skipped path=%s error=%s",
                pdf_path.name,
                exc,
            )
            stats["errors"] += 1

    logger.info(
        (
            "industry_rag_ingest_completed documents=%s chunks=%s "
            "inserted=%s skipped=%s errors=%s"
        ),
        stats["documents"],
        stats["chunks"],
        stats["inserted"],
        stats["skipped"],
        stats["errors"],
    )
    return stats


def add_chunks_without_duplicates(
    collection: Any,
    chunks: list[DocumentChunk],
) -> tuple[int, int]:
    """결정론적 ID 기준으로 중복이 없는 청크만 삽입한다."""
    if not chunks:
        return 0, 0

    existing_ids = _get_existing_ids(collection, [chunk.id for chunk in chunks])
    new_chunks = [chunk for chunk in chunks if chunk.id not in existing_ids]
    if not new_chunks:
        return 0, len(chunks)

    collection.add(
        ids=[chunk.id for chunk in new_chunks],
        documents=[chunk.text for chunk in new_chunks],
        metadatas=[chunk.metadata for chunk in new_chunks],
    )
    return len(new_chunks), len(chunks) - len(new_chunks)


def main() -> None:
    """`python -m backend.rag.ingest_industry_docs` CLI 진입점."""
    logging.basicConfig(level=logging.INFO)
    ingest_industry_docs()


def _find_industry_name(filename: str) -> str:
    for industry_name in INDUSTRY_METHODOLOGY_MAPPING:
        if industry_name in filename:
            return industry_name
    for alias, industry_name in _FILENAME_ALIASES:
        if alias in filename:
            return industry_name
    raise ValueError(f"지원하지 않는 업종 평가방법론 파일입니다: {filename}")


def _get_existing_ids(collection: Any, ids: list[str]) -> set[str]:
    existing = collection.get(ids=ids)
    values = existing.get("ids", []) if isinstance(existing, dict) else []
    return {str(value) for value in values}


if __name__ == "__main__":
    main()
