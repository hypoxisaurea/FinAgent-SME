from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal

from backend.schemas.state import (
    AltmanZ,
    BusinessCycle,
    FinancialRatios,
    FinancialResult,
    GrowthRatios,
    IndustryResult,
    MacroSignals,
    RiskFilter,
    TrendAnalysis,
)
from pydantic import BaseModel, ConfigDict, Field, model_validator

WorkflowStatus = Literal["not_started", "success", "partial", "failed", "not_target"]
AgentStepStatus = Literal["success", "partial", "failed", "skipped"]

_INTERNAL_CONTEXT_KEYS = frozenset({"_halt_workflow"})


class WorkflowStep(BaseModel):
    """오케스트레이터 단일 step 공개 계약."""

    agent_name: str
    ok: bool
    status: AgentStepStatus
    error_code: str
    fallback_used: bool = False
    latency_ms: int = 0
    output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class WorkflowContext(BaseModel):
    """워크플로우 실행 중 누적되는 공개 context 계약."""

    model_config = ConfigDict(extra="allow")

    request_id: str | None = None
    company_name: str | None = None
    company_found: bool | None = None
    workflow_code: str | None = None
    workflow_message: str | None = None
    corp_code: str | None = None
    corp_name: str | None = None
    company_profile: dict[str, Any] | None = None
    collect_sources: list[str] = Field(default_factory=list)
    news_data: list[dict[str, Any]] = Field(default_factory=list)
    news_result: dict[str, Any] | None = None
    news_tool_errors: list[dict[str, Any]] = Field(default_factory=list)
    financial_result: FinancialResult | dict[str, Any] | None = None
    financial_ratios: FinancialRatios | dict[str, Any] | None = None
    growth_ratios: GrowthRatios | dict[str, Any] | None = None
    altman_z: AltmanZ | dict[str, Any] | None = None
    trend_analysis: TrendAnalysis | dict[str, Any] | None = None
    risk_filter: RiskFilter | dict[str, Any] | None = None
    grade_cap: str | None = None
    industry_result: IndustryResult | dict[str, Any] | None = None
    peer_comparison: dict[str, Any] | None = None
    ksic_code: str | None = None
    outlook_score: str | None = None
    business_cycle: BusinessCycle | dict[str, Any] | None = None
    macro_signals: MacroSignals | dict[str, Any] | None = None
    industry_summary: str | None = None
    risk_event_result: dict[str, Any] | None = None
    document_result: dict[str, Any] | None = None
    overall_risk_level: str | None = None
    critical_count: int | None = None
    high_count: int | None = None
    medium_count: int | None = None
    low_count: int | None = None
    decision: str | None = None
    credit_grade: str | None = None
    credit_score: int | None = None
    decision_confidence: float | None = None
    decision_reasons: list[str] = Field(default_factory=list)
    recommended_limit: int | float | None = None
    explanation: dict[str, Any] | None = None
    report: dict[str, Any] | None = None
    validation_result: dict[str, Any] | None = None


class WorkflowResponse(BaseModel):
    """공개 워크플로우 성공/부분성공/실패/미대상 응답 계약."""

    request_id: str | None = None
    company_name: str | None = None
    status: WorkflowStatus
    code: str | None = None
    message: str | None = None
    context: WorkflowContext = Field(default_factory=WorkflowContext)
    steps: list[WorkflowStep] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_not_target_fields(self) -> WorkflowResponse:
        if self.status == "not_target":
            if not self.code:
                raise ValueError("status=not_target 응답에는 code가 필요합니다.")
            if not self.message:
                raise ValueError("status=not_target 응답에는 message가 필요합니다.")
        return self


class WorkflowErrorResponse(BaseModel):
    """API 계층 오류 응답 계약."""

    code: str
    message: str
    detail: dict[str, Any] = Field(default_factory=dict)
    request_id: str


def sanitize_workflow_context(
    payload: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """공개 응답에 노출하면 안 되는 내부 context 키를 제거한다."""
    return {
        key: value
        for key, value in dict(payload or {}).items()
        if key not in _INTERNAL_CONTEXT_KEYS
    }


def build_workflow_response(
    payload: Mapping[str, Any],
    *,
    request_id: str | None = None,
    company_name: str | None = None,
) -> WorkflowResponse:
    """dict 기반 워크플로우 결과를 공개 응답 스키마로 정규화한다."""
    normalized_payload = dict(payload)
    context = sanitize_workflow_context(normalized_payload.get("context"))

    resolved_request_id = request_id or normalized_payload.get("request_id") or context.get(
        "request_id"
    )
    resolved_company_name = (
        company_name
        or normalized_payload.get("company_name")
        or context.get("company_name")
    )

    if resolved_request_id is not None:
        normalized_payload["request_id"] = resolved_request_id
        context.setdefault("request_id", resolved_request_id)
    if resolved_company_name is not None:
        normalized_payload["company_name"] = resolved_company_name
        context.setdefault("company_name", resolved_company_name)

    normalized_payload["context"] = context
    normalized_payload.setdefault("steps", [])

    if normalized_payload.get("status") == "not_target":
        normalized_payload.setdefault(
            "code",
            context.get("workflow_code", "COMPANY_NOT_FOUND"),
        )
        normalized_payload.setdefault(
            "message",
            context.get("workflow_message", "대상 기업이 아닙니다."),
        )

    return WorkflowResponse.model_validate(normalized_payload)


def build_workflow_error_response(
    *,
    code: str,
    message: str,
    detail: dict[str, Any],
    request_id: str,
) -> WorkflowErrorResponse:
    """API 오류 응답을 공통 스키마로 생성한다."""
    return WorkflowErrorResponse(
        code=code,
        message=message,
        detail=detail,
        request_id=request_id,
    )


def derive_status_from_steps(steps: Sequence[WorkflowStep | Mapping[str, Any]]) -> str:
    """step 결과 목록에서 전체 워크플로우 상태를 계산한다."""
    if not steps:
        return "not_started"
    ok_count = sum(1 for step in steps if _read_step_value(step, "ok"))
    if ok_count == len(steps):
        return "success"
    if ok_count == 0:
        return "failed"
    return "partial"


def summarize_workflow_steps(
    steps: Sequence[WorkflowStep | Mapping[str, Any]],
) -> dict[str, int]:
    """step 목록을 상태별 카운트로 요약한다."""
    success_steps = sum(1 for step in steps if _read_step_value(step, "status") == "success")
    partial_steps = sum(1 for step in steps if _read_step_value(step, "status") == "partial")
    failed_steps = sum(1 for step in steps if _read_step_value(step, "status") == "failed")
    fallback_steps = sum(
        1 for step in steps if _read_step_value(step, "fallback_used") is True
    )
    return {
        "success": success_steps,
        "partial": partial_steps,
        "failed": failed_steps,
        "fallback": fallback_steps,
    }


def _read_step_value(step: WorkflowStep | Mapping[str, Any], key: str) -> Any:
    if isinstance(step, WorkflowStep):
        return getattr(step, key)
    return step.get(key)
