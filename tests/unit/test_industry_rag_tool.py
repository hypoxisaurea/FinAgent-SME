from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any


def _load_industry_module() -> Any:
    module_path = Path(__file__).resolve().parents[2] / "backend" / "tools" / "industry.py"
    spec = importlib.util.spec_from_file_location("industry_tool_under_test", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("industry.py module spec could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


industry = _load_industry_module()


def _invoke_get_industry_outlook(ksic_code: str) -> dict[str, Any]:
    return industry.get_industry_outlook.invoke({"ksic_code": ksic_code})


def test_infer_sub_sector_by_induty_code() -> None:
    assert industry._infer_sub_sector_for_manufacturing("C 제조업", "26102", None) == "반도체"
    assert industry._infer_sub_sector_for_manufacturing("C 제조업", "30111", None) == "조선"
    assert industry._infer_sub_sector_for_manufacturing("C 제조업", "24110", None) == "철강"
    assert industry._infer_sub_sector_for_manufacturing("C 제조업", "23100", None) == "정유"
    assert industry._infer_sub_sector_for_manufacturing("C 제조업", "25910", None) == "방산"


def test_infer_sub_sector_by_company_name() -> None:
    assert industry._infer_sub_sector_for_manufacturing("C 제조업", None, "현대중공업") == "조선"
    assert industry._infer_sub_sector_for_manufacturing("C 제조업", None, "삼성전자 반도체") == "반도체"
    assert industry._infer_sub_sector_for_manufacturing("C 제조업", None, "POSCO 철강") == "철강"
    assert industry._infer_sub_sector_for_manufacturing("C 제조업", None, "한화 Defense Corp") == "방산"
    assert industry._infer_sub_sector_for_manufacturing("C 제조업", None, "스틸코리아") == "철강"


def test_infer_sub_sector_induty_code_takes_priority_over_company_name() -> None:
    assert (
        industry._infer_sub_sector_for_manufacturing("C 제조업", "24110", "삼성전자 반도체")
        == "철강"
    )


def test_infer_sub_sector_returns_none_for_non_manufacturing() -> None:
    assert industry._infer_sub_sector_for_manufacturing("F 건설업", "41012", "건설사") is None
    assert industry._infer_sub_sector_for_manufacturing("J 정보통신업", None, "SI업체") is None


def test_infer_sub_sector_returns_corporate_fallback_when_no_match() -> None:
    """코드·명칭 매칭 전부 실패하면 C 제조업 기본 폴백 "corporate_제조" 반환."""
    assert industry._infer_sub_sector_for_manufacturing("C 제조업", "9999", None) == "corporate_제조"
    assert industry._infer_sub_sector_for_manufacturing("C 제조업", None, "홍길동주식회사") == "corporate_제조"
    assert industry._infer_sub_sector_for_manufacturing("C 제조업", None, None) == "corporate_제조"


def test_infer_sub_sector_for_pharma_by_induty_code() -> None:
    """제약업 KSIC 표준 4자리 및 실제 DART 3/5자리 코드 매칭."""
    # KSIC 표준 (5자리 코드 전달 시 [:4] → "2110" / "2120")
    assert industry._infer_sub_sector_for_manufacturing("C 제조업", "21101", None) == "제약업"
    assert industry._infer_sub_sector_for_manufacturing("C 제조업", "21201", None) == "제약업"
    # 실제 DART 코드 (유한양행·고려제약: "212", 한미약품: "21212")
    assert industry._infer_sub_sector_for_manufacturing("C 제조업", "212",   None) == "제약업"
    assert industry._infer_sub_sector_for_manufacturing("C 제조업", "21212", None) == "제약업"


def test_infer_sub_sector_for_pharma_by_company_name() -> None:
    assert industry._infer_sub_sector_for_manufacturing("C 제조업", None, "한미제약") == "제약업"
    assert industry._infer_sub_sector_for_manufacturing("C 제조업", None, "바이오제약코리아") == "제약업"
    assert industry._infer_sub_sector_for_manufacturing("C 제조업", None, "원료의약품주식회사") == "제약업"
    assert industry._infer_sub_sector_for_manufacturing("C 제조업", None, "Pharma Solutions Inc") == "제약업"


def test_default_industry_outlook_includes_methodology_fields() -> None:
    import sys
    from unittest.mock import MagicMock

    stubs = {
        "backend.common.providers": MagicMock(),
        "backend.common.tool_runtime": MagicMock(),
    }
    original = {k: sys.modules.pop(k) for k in stubs if k in sys.modules}
    sys.modules.update(stubs)
    try:
        agent_path = (
            Path(__file__).resolve().parents[2]
            / "backend"
            / "agents"
            / "industry_analyst"
            / "agent.py"
        )
        spec = importlib.util.spec_from_file_location("_agent_under_test", agent_path)
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        for k in stubs:
            sys.modules.pop(k, None)
        sys.modules.update(original)

    fallback = mod._default_industry_outlook("C 제조업")

    assert "industry_methodology" in fallback
    assert "methodology_sources" in fallback
    methodology = fallback["industry_methodology"]
    assert methodology["unavailable"] is True
    assert methodology["source_count"] == 0
    assert methodology["summary"] == ""
    assert methodology["key_risk_factors"] == []
    assert methodology["credit_assessment_factors"] == []
    assert fallback["methodology_sources"] == []


def test_get_industry_outlook_adds_methodology_context(monkeypatch: Any) -> None:
    def fake_fetch_kosis_parameter_data(*_: Any, **__: Any) -> list[dict[str, Any]]:
        values = [100.0] * 12 + [103.0]
        rows = []
        for itm_id in ["T10", "T11", "T12"]:
            rows.extend({"ITM_ID": itm_id, "DT": value} for value in values)
        return rows

    rag_payload = {
        "industry_methodology": {
            "industry_name": "제조업",
            "summary": "제조업은 원재료 가격과 수요 변동이 업황 리스크입니다.",
            "key_risk_factors": [],
            "credit_assessment_factors": [],
            "source_count": 1,
            "unavailable": False,
            "error": None,
        },
        "methodology_sources": [
            {
                "filename": "2025 반도체업 신용평가방법론.pdf",
                "page": 3,
                "score": 0.9,
                "industry_name": "반도체업",
                "ksic_code": "C 제조업",
                "sub_sector": "반도체",
            }
        ],
    }

    monkeypatch.setattr(
        industry.economic_data_client,
        "fetch_kosis_parameter_data",
        fake_fetch_kosis_parameter_data,
    )
    monkeypatch.setattr(
        industry,
        "_retrieve_methodology_for_outlook",
        lambda ksic_code, induty_code=None, company_name=None: rag_payload,
    )

    result = _invoke_get_industry_outlook("C 제조업")

    assert result["production_index_yoy"] == 0.03
    assert result["inventory_index_yoy"] == 0.03
    assert result["shipment_index_yoy"] == 0.03
    assert result["outlook_score"] == "Low"
    assert result["source"] == "KOSIS 광공업생산지수"
    assert result["industry_methodology"] == rag_payload["industry_methodology"]
    assert result["methodology_sources"] == rag_payload["methodology_sources"]


def test_get_industry_outlook_keeps_outlook_when_rag_unavailable(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(
        industry,
        "_read_agri_yoy",
        lambda: -0.02,
    )
    monkeypatch.setattr(
        industry,
        "_retrieve_methodology_for_outlook",
        lambda ksic_code, induty_code=None, company_name=None: {
            "industry_methodology": {
                "industry_name": "",
                "summary": "",
                "key_risk_factors": [],
                "credit_assessment_factors": [],
                "source_count": 0,
                "unavailable": True,
                "error": "vector store unavailable",
            },
            "methodology_sources": [],
        },
    )

    result = _invoke_get_industry_outlook("A01 농업")

    assert result["production_index_yoy"] == -0.02
    assert result["outlook_score"] == "Medium"
    assert result["source"] == "농림업생산지수 CSV (농업총계)"
    assert result["industry_methodology"]["unavailable"] is True
    assert result["industry_methodology"]["error"] == "vector store unavailable"
    assert result["methodology_sources"] == []


def test_get_industry_outlook_survives_rag_helper_exception(
    monkeypatch: Any,
) -> None:
    def raise_rag_error(
        _: str,
        induty_code: str | None = None,
        company_name: str | None = None,
    ) -> dict[str, Any]:
        raise RuntimeError("rag down")

    monkeypatch.setattr(
        industry,
        "_retrieve_methodology_for_outlook",
        raise_rag_error,
    )

    result = _invoke_get_industry_outlook("A03 어업")

    assert result["outlook_score"] == "Medium"
    assert result["source"] == "N/A"
    assert result["note"] == "A03 어업 생산지수 데이터 없음 - 중립(Medium) 적용"
    assert result["industry_methodology"]["unavailable"] is True
    assert result["industry_methodology"]["error"] == "rag down"
    assert result["methodology_sources"] == []
