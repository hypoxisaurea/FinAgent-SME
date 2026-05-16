"""M-001 | PDF 텍스트 추출 핸들러

PyMuPDF(fitz)를 사용해 사업보고서 PDF에서 텍스트를 추출하고
섹션(사업개요·재무정보·위험요소 등)으로 분류한다.
"""

from __future__ import annotations

import re
from pathlib import Path

import fitz  # PyMuPDF

from ..models import DocumentSection, SectionType


# ─── 섹션 분류 패턴 ───────────────────────────────────────────────────────────

_SECTION_PATTERNS: list[tuple[SectionType, list[str]]] = [
    (SectionType.COVER,     ["표지", "사업보고서", "분기보고서", "반기보고서"]),
    (SectionType.TOC,       ["목차", "차례"]),
    (SectionType.BUSINESS,  ["사업의 내용", "회사의 개요", "사업 개요", "주요 사업"]),
    (SectionType.FINANCIAL, ["재무에 관한 사항", "재무제표", "연결재무제표", "손익계산서", "대차대조표"]),
    (SectionType.RISK,      ["위험 요소", "투자위험", "사업위험", "재무위험"]),
    (SectionType.AUDIT,     ["감사보고서", "독립된 감사인", "감사의견"]),
]


# ─── 핸들러 ──────────────────────────────────────────────────────────────────

def extract_pdf_text(
    pdf_source: bytes | str | Path,
) -> tuple[list[DocumentSection], int]:
    """PDF에서 텍스트를 추출하고 섹션으로 분류한다.

    Args:
        pdf_source: PDF 바이너리 또는 파일 경로

    Returns:
        (DocumentSection 목록, 전체 페이지 수)
    """
    doc = _open_pdf(pdf_source)
    total_pages = len(doc)

    # 페이지별 텍스트 추출
    pages: list[tuple[int, str]] = []
    for page_num in range(total_pages):
        text = doc[page_num].get_text("text")
        pages.append((page_num + 1, text))

    doc.close()

    sections = _classify_sections(pages)
    return sections, total_pages


# ─── 내부 헬퍼 ───────────────────────────────────────────────────────────────

def _open_pdf(source: bytes | str | Path) -> fitz.Document:
    if isinstance(source, bytes):
        return fitz.open(stream=source, filetype="pdf")
    return fitz.open(str(source))


def _classify_sections(pages: list[tuple[int, str]]) -> list[DocumentSection]:
    """페이지 텍스트를 섹션으로 묶는다."""
    sections: list[DocumentSection] = []

    current_type  = SectionType.OTHER
    current_start = 1
    current_texts: list[str] = []

    for page_num, text in pages:
        detected = _detect_section_type(text)
        if detected != current_type:
            # 이전 섹션 저장
            if current_texts:
                combined = "\n".join(current_texts)
                sections.append(DocumentSection(
                    section_type=current_type,
                    page_start=current_start,
                    page_end=page_num - 1,
                    text=combined,
                    char_count=len(combined),
                ))
            current_type  = detected
            current_start = page_num
            current_texts = [text]
        else:
            current_texts.append(text)

    # 마지막 섹션 저장
    if current_texts:
        combined = "\n".join(current_texts)
        sections.append(DocumentSection(
            section_type=current_type,
            page_start=current_start,
            page_end=pages[-1][0],
            text=combined,
            char_count=len(combined),
        ))

    return sections


def _detect_section_type(text: str) -> SectionType:
    """텍스트에서 섹션 타입을 감지한다."""
    # 앞 200자에서 제목 키워드 탐지
    header = text[:200]
    for section_type, keywords in _SECTION_PATTERNS:
        if any(kw in header for kw in keywords):
            return section_type
    return SectionType.OTHER
