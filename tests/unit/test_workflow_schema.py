from __future__ import annotations

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
