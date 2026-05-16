"""M-004 | 비정형 문서 요약 핸들러

추출된 섹션 텍스트를 Claude API로 전달해
사업 개요·재무 현황·위험 요소 요약을 생성한다.
"""

from __future__ import annotations

import json
import os

import httpx

from ..models import DocumentSection, DocumentSummary, SectionType


ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-sonnet-4-20250514"
MAX_TEXT_CHARS = 8000  # 섹션당 최대 전달 텍스트 길이

_SYSTEM_PROMPT = """
당신은 기업 사업보고서 분석 전문가입니다.
제공된 사업보고서 텍스트를 읽고 아래 JSON 형식으로만 응답하세요.
{
  "report_year": 2024,
  "business_summary": "사업 개요 2~3문장 요약",
  "financial_summary": "재무 현황 2~3문장 요약 (주요 수치 포함)",
  "risk_summary": "핵심 위험 요소 2~3문장 요약",
  "key_points": ["핵심 포인트1", "핵심 포인트2", "핵심 포인트3"]
}
"""


# ─── 핸들러 ──────────────────────────────────────────────────────────────────

async def summarize_document(
    company_name: str,
    sections: list[DocumentSection],
) -> DocumentSummary | None:
    """추출된 섹션 텍스트를 Claude API로 요약한다.

    Args:
        company_name: 기업명
        sections:     M-001에서 추출된 섹션 목록

    Returns:
        DocumentSummary 또는 None (실패 시)
    """
    # 주요 섹션 텍스트 수집
    section_texts = _collect_section_texts(sections)
    if not section_texts:
        return None

    prompt = _build_prompt(company_name, section_texts)

    async with httpx.AsyncClient(timeout=60) as client:
        result = await _call_claude(client, prompt)

    if not result:
        return None

    return DocumentSummary(
        company_name=company_name,
        report_year=result.get("report_year"),
        business_summary=result.get("business_summary", "요약 실패"),
        financial_summary=result.get("financial_summary", "요약 실패"),
        risk_summary=result.get("risk_summary", "요약 실패"),
        key_points=result.get("key_points", []),
    )


# ─── 내부 헬퍼 ───────────────────────────────────────────────────────────────

_PRIORITY_SECTIONS = [
    SectionType.BUSINESS,
    SectionType.FINANCIAL,
    SectionType.RISK,
    SectionType.AUDIT,
]


def _collect_section_texts(sections: list[DocumentSection]) -> dict[str, str]:
    """우선순위 섹션 텍스트를 수집하고 길이를 제한한다."""
    result: dict[str, str] = {}
    for section_type in _PRIORITY_SECTIONS:
        matched = [s for s in sections if s.section_type == section_type]
        if matched:
            combined = " ".join(s.text for s in matched)
            result[section_type.value] = combined[:MAX_TEXT_CHARS]
    return result


def _build_prompt(company_name: str, section_texts: dict[str, str]) -> str:
    parts = [f"기업명: {company_name}\n"]
    label_map = {
        "business":  "사업 개요",
        "financial": "재무 정보",
        "risk":      "위험 요소",
        "audit":     "감사 보고서",
    }
    for key, text in section_texts.items():
        label = label_map.get(key, key)
        parts.append(f"[{label}]\n{text}\n")
    return "\n".join(parts)


async def _call_claude(client: httpx.AsyncClient, prompt: str) -> dict | None:
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
                "max_tokens": 1500,
                "system": _SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        resp.raise_for_status()
        raw = resp.json()["content"][0]["text"]
        clean = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        return json.loads(clean)
    except Exception:
        return None
