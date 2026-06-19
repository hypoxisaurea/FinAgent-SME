from __future__ import annotations

import logging
from datetime import date
from time import perf_counter
from typing import Any

from backend.common.contracts import (
    AGENT_PARTIAL_STATUS,
    AGENT_SUCCESS_STATUS,
    build_agent_output,
    elapsed_ms,
)
from backend.common.langfuse import score_current_trace
from backend.common.logging import request_id_context
from backend.schemas.agent_contracts import ValidationInput, ValidationOutput

logger = logging.getLogger(__name__)

VALID_DECISIONS = {"approve", "review", "reject"}


class ValidationAgent:
    """최종 심사 결과의 계약 및 정합성을 검증하는 에이전트."""

    name = "validation"
    input_model = ValidationInput
    output_model = ValidationOutput

    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Decision/Report 결과를 검증하고 Langfuse score를 기록한다."""
        started_at = perf_counter()
        request_id = payload.get("request_id")
        with request_id_context(request_id):
            validation_result = _validate_payload(payload)
            _record_validation_scores(validation_result)

            logger.info(
                (
                    "validation_agent_finished company_name=%s passed_checks=%s "
                    "total_checks=%s validation_passed=%s"
                ),
                payload.get("company_name"),
                validation_result["passed_checks"],
                validation_result["total_checks"],
                validation_result["validation_passed"],
            )

            status = (
                AGENT_SUCCESS_STATUS
                if validation_result["validation_passed"]
                else AGENT_PARTIAL_STATUS
            )
            error_code = "OK" if validation_result["validation_passed"] else "VALIDATION_WARNING"
            return build_agent_output(
                {"validation_result": validation_result},
                status=status,
                error_code=error_code,
                latency_ms=elapsed_ms(started_at),
            )


def _validate_payload(payload: dict[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    report = payload.get("report")
    decision = payload.get("decision")
    credit_grade = payload.get("credit_grade")
    decision_confidence = payload.get("decision_confidence")
    decision_reasons = payload.get("decision_reasons")
    explanation = payload.get("explanation")
    recommended_limit = payload.get("recommended_limit")
    company_name = payload.get("company_name")
    corp_name = payload.get("corp_name")
    corp_code = payload.get("corp_code")

    _append_check(
        checks,
        "decision_present",
        isinstance(decision, str) and decision in VALID_DECISIONS,
        f"decision={decision!r}",
    )
    _append_check(
        checks,
        "credit_grade_present",
        isinstance(credit_grade, str) and bool(credit_grade.strip()),
        f"credit_grade={credit_grade!r}",
    )
    _append_check(
        checks,
        "report_present",
        isinstance(report, dict),
        f"report_type={type(report).__name__}",
    )
    _append_check(
        checks,
        "decision_confidence_range",
        _is_probability(decision_confidence),
        f"decision_confidence={decision_confidence!r}",
    )

    if isinstance(report, dict):
        _append_check(
            checks,
            "report_generated_at_valid",
            _is_iso_date(report.get("generated_at")),
            f"report.generated_at={report.get('generated_at')!r}",
        )
        _append_check(
            checks,
            "report_company_matches",
            report.get("company_name") == company_name,
            f"report.company_name={report.get('company_name')!r}",
        )
        if corp_name is not None:
            _append_check(
                checks,
                "report_corp_name_matches",
                report.get("corp_name") == corp_name,
                f"report.corp_name={report.get('corp_name')!r}",
            )
        if corp_code is not None:
            _append_check(
                checks,
                "report_corp_code_matches",
                report.get("corp_code") == corp_code,
                f"report.corp_code={report.get('corp_code')!r}",
            )
        _append_check(
            checks,
            "report_decision_matches",
            report.get("decision") == decision,
            f"report.decision={report.get('decision')!r}",
        )
        _append_check(
            checks,
            "report_grade_matches",
            report.get("credit_grade") == credit_grade,
            f"report.credit_grade={report.get('credit_grade')!r}",
        )
        _append_check(
            checks,
            "report_summary_present",
            isinstance(report.get("summary"), str) and bool(report.get("summary", "").strip()),
            f"report.summary={report.get('summary')!r}",
        )
        _append_check(
            checks,
            "report_recommendation_present",
            isinstance(report.get("recommendation"), str)
            and bool(report.get("recommendation", "").strip()),
            f"report.recommendation={report.get('recommendation')!r}",
        )
        _append_check(
            checks,
            "report_recommended_limit_matches",
            report.get("recommended_limit") == recommended_limit,
            f"report.recommended_limit={report.get('recommended_limit')!r}",
        )

        if _is_probability(decision_confidence):
            _append_check(
                checks,
                "report_confidence_matches",
                report.get("confidence") == decision_confidence,
                f"report.confidence={report.get('confidence')!r}",
            )

        if isinstance(decision_reasons, list):
            _append_check(
                checks,
                "report_key_risks_matches",
                report.get("key_risks") == decision_reasons[:3],
                f"report.key_risks={report.get('key_risks')!r}",
            )

        if isinstance(explanation, dict) and _has_text(explanation.get("summary")):
            _append_check(
                checks,
                "report_summary_matches_explanation",
                report.get("summary") == explanation.get("summary"),
                f"report.summary={report.get('summary')!r}",
            )
        if isinstance(explanation, dict) and _has_text(explanation.get("recommendation")):
            _append_check(
                checks,
                "report_recommendation_matches_explanation",
                report.get("recommendation") == explanation.get("recommendation"),
                f"report.recommendation={report.get('recommendation')!r}",
            )

    is_non_negative_limit = isinstance(recommended_limit, (int, float)) and recommended_limit >= 0
    _append_check(
        checks,
        "recommended_limit_non_negative",
        is_non_negative_limit,
        f"recommended_limit={recommended_limit!r}",
    )

    reject_limit_valid = decision != "reject" or recommended_limit == 0
    _append_check(
        checks,
        "reject_limit_rule",
        reject_limit_valid,
        f"decision={decision!r}, recommended_limit={recommended_limit!r}",
    )

    passed_checks = sum(1 for check in checks if check["passed"])
    total_checks = len(checks)
    failed_checks = [check["name"] for check in checks if not check["passed"]]
    pass_rate = passed_checks / total_checks if total_checks else 0.0

    return {
        "validation_passed": passed_checks == total_checks,
        "pass_rate": pass_rate,
        "passed_checks": passed_checks,
        "total_checks": total_checks,
        "failed_checks": failed_checks,
        "checks": checks,
    }


def _append_check(
    checks: list[dict[str, Any]],
    name: str,
    passed: bool,
    detail: str,
) -> None:
    checks.append(
        {
            "name": name,
            "passed": passed,
            "detail": detail,
        }
    )


def _has_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_iso_date(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _is_probability(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return 0.0 <= float(value) <= 1.0


def _record_validation_scores(validation_result: dict[str, Any]) -> None:
    failed_checks = validation_result.get("failed_checks", [])
    comment = (
        "All validation checks passed."
        if not failed_checks
        else f"Failed checks: {', '.join(str(name) for name in failed_checks)}"
    )

    score_current_trace(
        name="validation_pass_rate",
        value=float(validation_result["pass_rate"]),
        data_type="NUMERIC",
        comment=comment,
    )
    score_current_trace(
        name="workflow_contract_valid",
        value=1 if validation_result["validation_passed"] else 0,
        data_type="BOOLEAN",
        comment=comment,
    )
    score_current_trace(
        name="failed_check_count",
        value=float(len(failed_checks)),
        data_type="NUMERIC",
        comment=comment,
    )
