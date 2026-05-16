"""M-002 | 재무표 파싱 핸들러

PDF 페이지를 이미지로 변환한 뒤 Claude Vision API로
재무 테이블을 구조화된 JSON으로 변환한다.
"""

from __future__ import annotations

import base64
import json
import os

import fitz
import httpx

from ..models import ExtractedTable, TableType


ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-sonnet-4-20250514"

_SYSTEM_PROMPT = """
당신은 재무제표 파싱 전문가입니다.
이미지 속 재무 테이블을 읽고 아래 JSON 형식으로만 응답하세요.
{
  "table_type": "income_statement" | "balance_sheet" | "cash_flow" | "unknown",
  "headers": ["컬럼1", "컬럼2", ...],
  "rows": [{"항목": "매출액", "2022": "100억", "2023": "120억"}, ...]
}
테이블이 없으면 {"table_type": "unknown", "headers": [], "rows": []} 로 응답하세요.
"""


# ─── 핸들러 ──────────────────────────────────────────────────────────────────

async def parse_financial_tables(
    pdf_source: bytes | str,
    target_section_pages: list[int],  # 재무 섹션 페이지 번호 목록
) -> list[ExtractedTable]:
    """재무 섹션 페이지들을 이미지로 변환해 Claude Vision으로 파싱한다.

    Args:
        pdf_source:           PDF 바이너리 또는 경로
        target_section_pages: 재무 섹션에 해당하는 페이지 번호 목록

    Returns:
        ExtractedTable 목록
    """
    doc = _open_pdf(pdf_source)
    tables: list[ExtractedTable] = []

    async with httpx.AsyncClient(timeout=60) as client:
        for page_num in target_section_pages:
            if page_num < 1 or page_num > len(doc):
                continue

            # 페이지 → PNG 이미지 변환
            page = doc[page_num - 1]
            image_bytes = _page_to_image(page)
            raw_text = page.get_text("text")

            result = await _call_claude_vision(client, image_bytes, raw_text)
            if result:
                tables.append(ExtractedTable(
                    table_type=TableType(result.get("table_type", "unknown")),
                    page_number=page_num,
                    headers=result.get("headers", []),
                    rows=result.get("rows", []),
                    raw_text=raw_text,
                    confidence=0.9 if result.get("headers") else 0.3,
                ))

    doc.close()
    return [t for t in tables if t.table_type != TableType.UNKNOWN]


# ─── 내부 헬퍼 ───────────────────────────────────────────────────────────────

def _open_pdf(source: bytes | str) -> fitz.Document:
    if isinstance(source, bytes):
        return fitz.open(stream=source, filetype="pdf")
    return fitz.open(str(source))


def _page_to_image(page: fitz.Page, dpi: int = 150) -> bytes:
    """PDF 페이지를 PNG 바이너리로 변환한다."""
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat)
    return pix.tobytes("png")


async def _call_claude_vision(
    client: httpx.AsyncClient,
    image_bytes: bytes,
    raw_text: str,
) -> dict | None:
    """Claude Vision API로 이미지 속 테이블을 파싱한다."""
    image_b64 = base64.standard_b64encode(image_bytes).decode()

    try:
        resp = await client.post(
            ANTHROPIC_API_URL,
            headers={
                "x-api-key": os.environ.get("ANTHROPIC_API_KEY", ""),
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": MODEL,
                "max_tokens": 2000,
                "system": _SYSTEM_PROMPT,
                "messages": [{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": image_b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": f"위 이미지의 재무 테이블을 JSON으로 변환해주세요.\n참고 텍스트:\n{raw_text[:500]}",
                        },
                    ],
                }],
            },
        )
        resp.raise_for_status()
        raw = resp.json()["content"][0]["text"]
        # JSON 펜스 제거 후 파싱
        clean = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        return json.loads(clean)

    except Exception:
        return None
