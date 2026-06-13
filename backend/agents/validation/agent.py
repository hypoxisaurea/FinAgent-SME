from __future__ import annotations

import logging
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

logger = logging.getLogger(__name__)

VALID_DECISIONS = {"approve", "review", "reject"}


class ValidationAgent:
    """최종 심사 결과의 계약 및 정합성을 검증하는 에이전트."""

    name = "validation"

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
    recommended_limit = payload.get("recommended_limit")
    company_name = payload.get("company_name")

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

    if isinstance(report, dict):
        _append_check(
            checks,
            "report_company_matches",
            report.get("company_name") == company_name,
            f"report.company_name={report.get('company_name')!r}",
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
