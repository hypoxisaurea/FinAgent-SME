"""M-003 | 차트·그래프 해석 핸들러

PDF 페이지 이미지를 Claude Vision으로 분석해
차트·그래프의 제목, 수치, 추세를 추출한다.
"""

from __future__ import annotations

import base64
import json
import os

import fitz
import httpx

from ..models import ExtractedChart


ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-sonnet-4-20250514"

_SYSTEM_PROMPT = """
당신은 재무 차트 분석 전문가입니다.
이미지 속 차트나 그래프를 분석하고 아래 JSON 형식으로만 응답하세요.
{
  "has_chart": true | false,
  "chart_title": "차트 제목",
  "description": "차트가 보여주는 내용 한두 문장 설명",
  "data_points": [{"label": "2022", "value": 100}, ...],
  "raw_caption": "차트 하단 캡션 텍스트 (있는 경우)"
}
차트가 없으면 {"has_chart": false} 로 응답하세요.
"""


# ─── 핸들러 ──────────────────────────────────────────────────────────────────

async def interpret_charts(
    pdf_source: bytes | str,
    target_pages: list[int],
) -> list[ExtractedChart]:
    """지정 페이지에서 차트·그래프를 탐지하고 해석한다.

    Args:
        pdf_source:    PDF 바이너리 또는 경로
        target_pages:  분석할 페이지 번호 목록

    Returns:
        ExtractedChart 목록 (차트가 있는 페이지만)
    """
    doc = _open_pdf(pdf_source)
    charts: list[ExtractedChart] = []

    async with httpx.AsyncClient(timeout=60) as client:
        for page_num in target_pages:
            if page_num < 1 or page_num > len(doc):
                continue

            page = doc[page_num - 1]

            # 이미지가 포함된 페이지만 처리 (성능 최적화)
            if not _has_image(page):
                continue

            image_bytes = _page_to_image(page)
            result = await _call_claude_vision(client, image_bytes)

            if result and result.get("has_chart"):
                charts.append(ExtractedChart(
                    page_number=page_num,
                    chart_title=result.get("chart_title", ""),
                    description=result.get("description", ""),
                    data_points=result.get("data_points", []),
                    raw_caption=result.get("raw_caption"),
                ))

    doc.close()
    return charts


# ─── 내부 헬퍼 ───────────────────────────────────────────────────────────────

def _open_pdf(source: bytes | str) -> fitz.Document:
    if isinstance(source, bytes):
        return fitz.open(stream=source, filetype="pdf")
    return fitz.open(str(source))


def _has_image(page: fitz.Page) -> bool:
    """페이지에 이미지 객체가 있는지 확인한다."""
    return len(page.get_images()) > 0


def _page_to_image(page: fitz.Page, dpi: int = 150) -> bytes:
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat)
    return pix.tobytes("png")


async def _call_claude_vision(
    client: httpx.AsyncClient,
    image_bytes: bytes,
) -> dict | None:
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
                "max_tokens": 1000,
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
                        {"type": "text", "text": "이 페이지에 차트나 그래프가 있으면 분석해주세요."},
                    ],
                }],
            },
        )
        resp.raise_for_status()
        raw = resp.json()["content"][0]["text"]
        clean = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        return json.loads(clean)

    except Exception:
        return None
