"""IndustryAnalystAgent.run() → kr_financial_grades 연결 커버리지 테스트

6가지 케이스:
1. 제약업 + ratios 정상 → kr_financial_grades 포함
2. methodology_sources 비어있음 → kr_financial_grades 없음 (None 제외)
3. financial_ratios 없음 → kr_financial_grades 없음
4. JSON 파일 없는 sub_sector → kr_financial_grades 없음
5. 방산 오분류 → corporate_제조 폴백 (임시 처방)
6. 방산 외 미지원 sub_sector(철강 등) → 폴백 없이 None 유지
"""
from __future__ import annotations

import asyncio
from typing import Any

from backend.agents.industry_analyst.agent import IndustryAnalystAgent
from backend.agents.orchestrator.step_runner import run_agent_step

# ── 공통 픽스처 ──────────────────────────────────────────────────────────────

_VALID_RATIOS: dict[str, float] = {
    "ebitda_margin":       0.25,   # ×100=25% → AAA(≥20)
    "net_debt_to_ebitda":  0.30,   # 배수 그대로 → AAA(≤0.5)
    "ebitda_to_interest":  20.0,   # AAA(≥15)
    "debt_ratio":          0.40,   # ×100=40% → AAA(≤50)
    "borrow_dep":          0.15,   # ×100=15% → AAA(≤20)
}

_BASE_PAYLOAD: dict[str, Any] = {
    "company_name": "한미제약",
    "corp_code":    "00000001",
    "target_year":  2024,
}


class _MockIndustryProvider:
    """IndustryDataProvider 프로토콜 최소 구현 (픽스처용)."""

    def __init__(self, methodology_sources: list[dict[str, Any]] | None = None) -> None:
        self._sources = methodology_sources if methodology_sources is not None else []

    def map_corp_to_ksic(self, corp_code: str) -> dict[str, Any]:
        return {"ksic_code": "C 제조업", "induty_code": "21101", "corp_name": "한미제약"}

    def get_industry_avg_ratios(
        self,
        ksic_code: str,
        target_year: int,
        company_ratios: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "ksic_code": ksic_code,
            "year": target_year,
            "peer_comparison": None,
            "sector_note": "test",
        }

    def get_industry_outlook(
        self,
        ksic_code: str,
        induty_code: str | None = None,
        company_name: str | None = None,
    ) -> dict[str, Any]:
        return {
            "outlook_score": "Medium",
            "source": "test",
            "industry_methodology": {
                "industry_name": "제조업",
                "summary": "",
                "key_risk_factors": [],
                "credit_assessment_factors": [],
                "source_count": len(self._sources),
                "unavailable": False,
                "error": None,
            },
            "methodology_sources": self._sources,
        }

    def get_business_cycle(self) -> dict[str, Any]:
        return {
            "phase": "확장",
            "leading_trend": "rising",
            "coincident_trend": "rising",
            "leading_latest": 100.5,
            "coincident_latest": 100.3,
        }

    def get_macro_indicators(self, ksic_code: str) -> dict[str, Any]:
        return {"base_rate": 3.5, "usd_krw": 1300.0, "rate_trend": "stable"}


def _pharma_source() -> dict[str, Any]:
    return {"filename": "2024 제약업 평가방법론.pdf", "page": 1, "score": 0.9, "sub_sector": "제약업"}


def _unknown_source() -> dict[str, Any]:
    return {"filename": "dummy.pdf", "page": 1, "score": 0.9, "sub_sector": "존재하지않는업종"}


def _bangsan_source() -> dict[str, Any]:
    """induty_code[:4]="2591" 오매핑으로 삼미금속 같은 기업이 받게 되는 잘못된 sub_sector."""
    return {"filename": "2025 방산업 평가방법론.pdf", "page": 1, "score": 0.72, "sub_sector": "방산"}


def _cheolgang_source() -> dict[str, Any]:
    """방산 아닌 다른 미지원 sub_sector 대표 케이스."""
    return {"filename": "dummy_cheolgang.pdf", "page": 1, "score": 0.8, "sub_sector": "철강"}


# ── 테스트 케이스 ─────────────────────────────────────────────────────────────

def test_kr_grades_present_when_pharma_sub_sector_and_ratios_available() -> None:
    """제약업 sub_sector + valid ratios → kr_financial_grades 포함, 5개 지표 모두 AAA."""
    agent = IndustryAnalystAgent(provider=_MockIndustryProvider([_pharma_source()]))
    payload = {**_BASE_PAYLOAD, "financial_ratios": _VALID_RATIOS}
    step = asyncio.run(run_agent_step(agent, payload))

    assert step.ok, f"agent failed: {step.error}"
    assert "kr_financial_grades" in step.output, "kr_financial_grades 키 없음"

    grades = step.output["kr_financial_grades"]
    assert grades["methodology"] == "제약업"
    assert "per_metric_grades" in grades
    per = grades["per_metric_grades"]
    assert set(per.keys()) == {"ebitda_margin", "net_debt_to_ebitda", "ebitda_to_interest", "debt_ratio", "borrow_dep"}
    for key, item in per.items():
        assert item["grade"] == "AAA", f"{key} 등급이 AAA가 아님: {item['grade']}"


def test_kr_grades_absent_when_methodology_sources_empty() -> None:
    """methodology_sources=[] → sub_sector 없음 → kr_financial_grades 미포함."""
    agent = IndustryAnalystAgent(provider=_MockIndustryProvider([]))
    payload = {**_BASE_PAYLOAD, "financial_ratios": _VALID_RATIOS}
    step = asyncio.run(run_agent_step(agent, payload))

    assert step.ok, f"agent failed: {step.error}"
    assert "kr_financial_grades" not in step.output, "kr_financial_grades가 있으면 안 됨"


def test_kr_grades_absent_when_financial_ratios_not_provided() -> None:
    """financial_ratios 미전달 → company_ratios=None → kr_financial_grades 미포함."""
    agent = IndustryAnalystAgent(provider=_MockIndustryProvider([_pharma_source()]))
    payload = {**_BASE_PAYLOAD}  # financial_ratios 없음
    step = asyncio.run(run_agent_step(agent, payload))

    assert step.ok, f"agent failed: {step.error}"
    assert "kr_financial_grades" not in step.output, "kr_financial_grades가 있으면 안 됨"


def test_kr_grades_absent_when_sub_sector_json_missing() -> None:
    """JSON 캐시 없는 sub_sector → calc_kr_financial_grades None 반환 → 미포함."""
    agent = IndustryAnalystAgent(provider=_MockIndustryProvider([_unknown_source()]))
    payload = {**_BASE_PAYLOAD, "financial_ratios": _VALID_RATIOS}
    step = asyncio.run(run_agent_step(agent, payload))

    assert step.ok, f"agent failed: {step.error}"
    assert "kr_financial_grades" not in step.output, "kr_financial_grades가 있으면 안 됨"


def test_kr_grades_fallback_to_corporate_when_bangsan_misclassified() -> None:
    """방산 오분류 케이스(삼미금속 등) → corporate_제조로 폴백 → kr_financial_grades 포함.

    임시 처방: induty_code[:4]="2591" 매핑이 틀렸기 때문에 생기는 문제.
    근본 수정 전까지 방산 한정으로만 corporate_제조 폴백 적용.
    """
    agent = IndustryAnalystAgent(provider=_MockIndustryProvider([_bangsan_source()]))
    payload = {**_BASE_PAYLOAD, "financial_ratios": _VALID_RATIOS}
    step = asyncio.run(run_agent_step(agent, payload))

    assert step.ok, f"agent failed: {step.error}"
    assert "kr_financial_grades" in step.output, "방산 폴백 후 kr_financial_grades가 없음"
    grades = step.output["kr_financial_grades"]
    assert grades["methodology"] == "corporate_제조", (
        f"폴백 결과가 corporate_제조가 아님: {grades['methodology']}"
    )


def test_kr_grades_absent_when_non_bangsan_unsupported_sub_sector() -> None:
    """방산 외 미지원 sub_sector(철강 등)는 폴백 없이 None 유지 — 조용히 오분류 방지."""
    agent = IndustryAnalystAgent(provider=_MockIndustryProvider([_cheolgang_source()]))
    payload = {**_BASE_PAYLOAD, "financial_ratios": _VALID_RATIOS}
    step = asyncio.run(run_agent_step(agent, payload))

    assert step.ok, f"agent failed: {step.error}"
    assert "kr_financial_grades" not in step.output, (
        "철강(미지원) sub_sector가 corporate_제조로 오변환되면 안 됨"
    )
