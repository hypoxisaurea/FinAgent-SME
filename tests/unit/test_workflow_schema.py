from __future__ import annotations

from datetime import date

from backend.schemas.workflow import build_workflow_response


def test_build_workflow_response_accepts_structured_industry_context() -> None:
    response = build_workflow_response(
        {
            "request_id": "req-123",
            "company_name": "러셀",
            "status": "success",
            "context": {
                "company_name": "러셀",
                "industry_summary": {
                    "avg_op_margin": 0.0389,
                    "avg_debt_ratio": 1.24,
                    "sales_growth": "n/a",
                },
                "industry_outlook": {
                    "outlook_score": "Medium",
                    "note": "중립",
                },
                "macro_indicators": {
                    "base_rate": 3.5,
                    "usd_krw": 1380.0,
                },
                "financial_summary": {
                    "target_year": 2024,
                    "grade_cap": "BB+",
                },
            },
            "steps": [],
        }
    )

    assert response.context.industry_summary == {
        "avg_op_margin": 0.0389,
        "avg_debt_ratio": 1.24,
        "sales_growth": "n/a",
    }
    assert response.context.industry_outlook == {
        "outlook_score": "Medium",
        "note": "중립",
    }
    assert response.context.macro_indicators == {
        "base_rate": 3.5,
        "usd_krw": 1380.0,
    }
    assert response.context.financial_summary == {
        "target_year": 2024,
        "grade_cap": "BB+",
    }
    assert response.context.runtime.request_id == "req-123"
    assert response.context.runtime.company_name == "러셀"
    assert response.context.industry.industry_summary == {
        "avg_op_margin": 0.0389,
        "avg_debt_ratio": 1.24,
        "sales_growth": "n/a",
    }
    assert response.context.industry.industry_outlook == {
        "outlook_score": "Medium",
        "note": "중립",
    }
    assert response.context.financial.financial_summary == {
        "target_year": 2024,
        "grade_cap": "BB+",
    }


def test_build_workflow_response_serializes_decision_processed_at_date() -> None:
    response = build_workflow_response(
        {
            "request_id": "req-processed-at",
            "company_name": "케이씨피드",
            "status": "success",
            "context": {
                "company_name": "케이씨피드",
                "decision": "approve",
                "processed_at": date(2026, 6, 19),
            },
            "steps": [],
        }
    )

    serialized = response.model_dump(mode="json")

    assert serialized["context"]["processed_at"] == "2026-06-19"
    assert serialized["context"]["decisioning"]["processed_at"] == "2026-06-19"


def test_kr_financial_grades_accessible_via_industry_section() -> None:
    """kr_financial_grades가 context.industry.kr_financial_grades로 접근 가능해야 한다."""
    grades_payload = {
        "methodology": "제약업",
        "per_metric_grades": {
            "ebitda_margin": {"grade": "AAA", "value": 25.0, "weight": "7.5%"},
        },
        "scope_note": "사업항목(50%) 미반영",
    }
    response = build_workflow_response(
        {
            "request_id": "req-kr-grades",
            "company_name": "한미제약",
            "status": "success",
            "context": {
                "company_name": "한미제약",
                "kr_financial_grades": grades_payload,
            },
            "steps": [],
        }
    )

    # context 최상위 경로 (extra="allow", 기존 동작 유지)
    assert response.context.kr_financial_grades == grades_payload
    # industry 섹션 경로 (신규 노출)
    assert response.context.industry.kr_financial_grades == grades_payload


def test_kr_financial_grades_none_when_not_provided() -> None:
    """kr_financial_grades 미전달 시 context.industry.kr_financial_grades는 None."""
    response = build_workflow_response(
        {
            "request_id": "req-kr-grades-absent",
            "company_name": "테스트기업",
            "status": "success",
            "context": {"company_name": "테스트기업"},
            "steps": [],
        }
    )

    assert response.context.industry.kr_financial_grades is None
