from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal

from backend.schemas.agent_contracts import (
    ValidationResultPayload,
    WorkflowReportPayload,
)
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
WorkflowJobStatus = Literal["queued", "running", "succeeded", "failed"]

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


class WorkflowRuntimeSection(BaseModel):
    """요청/실행 메타데이터 섹션."""

    request_id: str | None = None
    company_name: str | None = None
    collect_sources: list[str] = Field(default_factory=list)


class WorkflowCompanySection(BaseModel):
    """기업 식별/대상 여부 섹션."""

    company_found: bool | None = None
    workflow_code: str | None = None
    workflow_message: str | None = None
    corp_code: str | None = None
    corp_name: str | None = None
    company_profile: dict[str, Any] | None = None
    company_resolution: dict[str, Any] | None = None


class WorkflowCollectionSection(BaseModel):
    """수집 단계 산출물 섹션."""

    news_data: list[dict[str, Any]] = Field(default_factory=list)
    news_result: dict[str, Any] | None = None
    news_collector_config: dict[str, Any] | None = None
    news_tool_runs: list[dict[str, Any]] = Field(default_factory=list)
    news_tool_errors: list[dict[str, Any]] = Field(default_factory=list)


class WorkflowFinancialSection(BaseModel):
    """재무 분석 산출물 섹션."""

    financial_statements: dict[str, Any] | None = None
    financial_result: FinancialResult | dict[str, Any] | None = None
    financial_ratios: FinancialRatios | dict[str, Any] | None = None
    company_ratios: dict[str, Any] | None = None
    growth_ratios: GrowthRatios | dict[str, Any] | None = None
    altman_z: AltmanZ | dict[str, Any] | None = None
    financial_trend: dict[str, Any] | None = None
    trend_analysis: TrendAnalysis | dict[str, Any] | None = None
    financial_flags: list[str] = Field(default_factory=list)
    financial_summary: dict[str, Any] | None = None
    risk_filters: dict[str, Any] | None = None
    risk_filter: RiskFilter | dict[str, Any] | None = None
    grade_cap: str | None = None
    total_assets: int | float | None = None
    total_assets_statement: int | float | None = None
    revenue: int | float | None = None
    avg_revenue_last_3y: int | float | None = None
    operating_income: int | float | None = None
    net_income: int | float | None = None
    financial_tool_runs: list[dict[str, Any]] = Field(default_factory=list)
    financial_tool_errors: list[dict[str, Any]] = Field(default_factory=list)


class WorkflowIndustrySection(BaseModel):
    """산업 분석 산출물 섹션."""

    industry_result: IndustryResult | dict[str, Any] | None = None
    industry_outlook: dict[str, Any] | None = None
    peer_comparison: dict[str, Any] | None = None
    ksic_code: str | None = None
    outlook_score: str | None = None
    business_cycle: BusinessCycle | dict[str, Any] | None = None
    macro_indicators: dict[str, Any] | None = None
    macro_signals: MacroSignals | dict[str, Any] | None = None
    industry_summary: dict[str, Any] | str | None = None
    industry_tool_runs: list[dict[str, Any]] = Field(default_factory=list)
    industry_tool_errors: list[dict[str, Any]] = Field(default_factory=list)


class WorkflowRiskSection(BaseModel):
    """리스크 이벤트 산출물 섹션."""

    risk_event_result: dict[str, Any] | None = None
    overall_risk_level: str | None = None
    critical_count: int | None = None
    high_count: int | None = None
    medium_count: int | None = None
    low_count: int | None = None
    latest_debt_ratio: float | None = None
    latest_op_margin: float | None = None
    is_net_income_negative: bool | None = None
    all_events: list[dict[str, Any]] = Field(default_factory=list)
    classified_events: list[dict[str, Any]] = Field(default_factory=list)
    timeline: list[dict[str, Any]] = Field(default_factory=list)


class WorkflowDecisionSection(BaseModel):
    """의사결정 산출물 섹션."""

    decision: str | None = None
    credit_grade: str | None = None
    credit_score: int | None = None
    decision_confidence: float | None = None
    decision_reasons: list[str] = Field(default_factory=list)
    recommended_limit: int | float | None = None
    limit_range: str | None = None
    limit_basis: str | None = None
    explanation: dict[str, Any] | None = None
    grade_detail: dict[str, Any] | None = None
    processed_at: str | None = None


class WorkflowArtifactSection(BaseModel):
    """최종 산출물 및 문서 처리 결과 섹션."""

    report: WorkflowReportPayload | dict[str, Any] | None = None
    validation_result: ValidationResultPayload | dict[str, Any] | None = None
    document_result: dict[str, Any] | None = None
    pdf_path: str | None = None
    output_dir: str | None = None
    texts: list[str] = Field(default_factory=list)
    chart_images: list[Any] = Field(default_factory=list)
    page_count: int | None = None


class WorkflowContext(BaseModel):
    """워크플로우 실행 중 누적되는 공개 context 계약."""

    model_config = ConfigDict(extra="allow")

    request_id: str | None = None
    company_name: str | None = None
    collect_sources: list[str] = Field(default_factory=list)
    company_found: bool | None = None
    workflow_code: str | None = None
    workflow_message: str | None = None
    corp_code: str | None = None
    corp_name: str | None = None
    company_profile: dict[str, Any] | None = None
    company_resolution: dict[str, Any] | None = None
    news_data: list[dict[str, Any]] = Field(default_factory=list)
    news_result: dict[str, Any] | None = None
    news_collector_config: dict[str, Any] | None = None
    news_tool_runs: list[dict[str, Any]] = Field(default_factory=list)
    news_tool_errors: list[dict[str, Any]] = Field(default_factory=list)
    financial_statements: dict[str, Any] | None = None
    financial_result: FinancialResult | dict[str, Any] | None = None
    financial_ratios: FinancialRatios | dict[str, Any] | None = None
    company_ratios: dict[str, Any] | None = None
    growth_ratios: GrowthRatios | dict[str, Any] | None = None
    altman_z: AltmanZ | dict[str, Any] | None = None
    financial_trend: dict[str, Any] | None = None
    trend_analysis: TrendAnalysis | dict[str, Any] | None = None
    financial_flags: list[str] = Field(default_factory=list)
    financial_summary: dict[str, Any] | None = None
    risk_filters: dict[str, Any] | None = None
    risk_filter: RiskFilter | dict[str, Any] | None = None
    grade_cap: str | None = None
    total_assets: int | float | None = None
    total_assets_statement: int | float | None = None
    revenue: int | float | None = None
    avg_revenue_last_3y: int | float | None = None
    operating_income: int | float | None = None
    net_income: int | float | None = None
    financial_tool_runs: list[dict[str, Any]] = Field(default_factory=list)
    financial_tool_errors: list[dict[str, Any]] = Field(default_factory=list)
    industry_result: IndustryResult | dict[str, Any] | None = None
    industry_outlook: dict[str, Any] | None = None
    peer_comparison: dict[str, Any] | None = None
    ksic_code: str | None = None
    outlook_score: str | None = None
    business_cycle: BusinessCycle | dict[str, Any] | None = None
    macro_indicators: dict[str, Any] | None = None
    macro_signals: MacroSignals | dict[str, Any] | None = None
    industry_summary: dict[str, Any] | str | None = None
    industry_tool_runs: list[dict[str, Any]] = Field(default_factory=list)
    industry_tool_errors: list[dict[str, Any]] = Field(default_factory=list)
    risk_event_result: dict[str, Any] | None = None
    document_result: dict[str, Any] | None = None
    overall_risk_level: str | None = None
    critical_count: int | None = None
    high_count: int | None = None
    medium_count: int | None = None
    low_count: int | None = None
    latest_debt_ratio: float | None = None
    latest_op_margin: float | None = None
    is_net_income_negative: bool | None = None
    all_events: list[dict[str, Any]] = Field(default_factory=list)
    classified_events: list[dict[str, Any]] = Field(default_factory=list)
    timeline: list[dict[str, Any]] = Field(default_factory=list)
    decision: str | None = None
    credit_grade: str | None = None
    credit_score: int | None = None
    decision_confidence: float | None = None
    decision_reasons: list[str] = Field(default_factory=list)
    recommended_limit: int | float | None = None
    limit_range: str | None = None
    limit_basis: str | None = None
    explanation: dict[str, Any] | None = None
    grade_detail: dict[str, Any] | None = None
    processed_at: str | None = None
    report: WorkflowReportPayload | dict[str, Any] | None = None
    validation_result: ValidationResultPayload | dict[str, Any] | None = None
    pdf_path: str | None = None
    output_dir: str | None = None
    texts: list[str] = Field(default_factory=list)
    chart_images: list[Any] = Field(default_factory=list)
    page_count: int | None = None

    runtime: WorkflowRuntimeSection = Field(default_factory=WorkflowRuntimeSection)
    company: WorkflowCompanySection = Field(default_factory=WorkflowCompanySection)
    collection: WorkflowCollectionSection = Field(default_factory=WorkflowCollectionSection)
    financial: WorkflowFinancialSection = Field(default_factory=WorkflowFinancialSection)
    industry: WorkflowIndustrySection = Field(default_factory=WorkflowIndustrySection)
    risk: WorkflowRiskSection = Field(default_factory=WorkflowRiskSection)
    decisioning: WorkflowDecisionSection = Field(default_factory=WorkflowDecisionSection)
    artifacts: WorkflowArtifactSection = Field(default_factory=WorkflowArtifactSection)

    @model_validator(mode="after")
    def _populate_sections(self) -> WorkflowContext:
        self.runtime = WorkflowRuntimeSection(
            request_id=self.request_id,
            company_name=self.company_name,
            collect_sources=list(self.collect_sources),
        )
        self.company = WorkflowCompanySection(
            company_found=self.company_found,
            workflow_code=self.workflow_code,
            workflow_message=self.workflow_message,
            corp_code=self.corp_code,
            corp_name=self.corp_name,
            company_profile=self.company_profile,
            company_resolution=self.company_resolution,
        )
        self.collection = WorkflowCollectionSection(
            news_data=list(self.news_data),
            news_result=self.news_result,
            news_collector_config=self.news_collector_config,
            news_tool_runs=list(self.news_tool_runs),
            news_tool_errors=list(self.news_tool_errors),
        )
        self.financial = WorkflowFinancialSection(
            financial_statements=self.financial_statements,
            financial_result=self.financial_result,
            financial_ratios=self.financial_ratios,
            company_ratios=self.company_ratios,
            growth_ratios=self.growth_ratios,
            altman_z=self.altman_z,
            financial_trend=self.financial_trend,
            trend_analysis=self.trend_analysis,
            financial_flags=list(self.financial_flags),
            financial_summary=self.financial_summary,
            risk_filters=self.risk_filters,
            risk_filter=self.risk_filter,
            grade_cap=self.grade_cap,
            total_assets=self.total_assets,
            total_assets_statement=self.total_assets_statement,
            revenue=self.revenue,
            avg_revenue_last_3y=self.avg_revenue_last_3y,
            operating_income=self.operating_income,
            net_income=self.net_income,
            financial_tool_runs=list(self.financial_tool_runs),
            financial_tool_errors=list(self.financial_tool_errors),
        )
        self.industry = WorkflowIndustrySection(
            industry_result=self.industry_result,
            industry_outlook=self.industry_outlook,
            peer_comparison=self.peer_comparison,
            ksic_code=self.ksic_code,
            outlook_score=self.outlook_score,
            business_cycle=self.business_cycle,
            macro_indicators=self.macro_indicators,
            macro_signals=self.macro_signals,
            industry_summary=self.industry_summary,
            industry_tool_runs=list(self.industry_tool_runs),
            industry_tool_errors=list(self.industry_tool_errors),
        )
        self.risk = WorkflowRiskSection(
            risk_event_result=self.risk_event_result,
            overall_risk_level=self.overall_risk_level,
            critical_count=self.critical_count,
            high_count=self.high_count,
            medium_count=self.medium_count,
            low_count=self.low_count,
            latest_debt_ratio=self.latest_debt_ratio,
            latest_op_margin=self.latest_op_margin,
            is_net_income_negative=self.is_net_income_negative,
            all_events=list(self.all_events),
            classified_events=list(self.classified_events),
            timeline=list(self.timeline),
        )
        self.decisioning = WorkflowDecisionSection(
            decision=self.decision,
            credit_grade=self.credit_grade,
            credit_score=self.credit_score,
            decision_confidence=self.decision_confidence,
            decision_reasons=list(self.decision_reasons),
            recommended_limit=self.recommended_limit,
            limit_range=self.limit_range,
            limit_basis=self.limit_basis,
            explanation=self.explanation,
            grade_detail=self.grade_detail,
            processed_at=self.processed_at,
        )
        self.artifacts = WorkflowArtifactSection(
            report=self.report,
            validation_result=self.validation_result,
            document_result=self.document_result,
            pdf_path=self.pdf_path,
            output_dir=self.output_dir,
            texts=list(self.texts),
            chart_images=list(self.chart_images),
            page_count=self.page_count,
        )
        return self


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


class WorkflowJobSubmitResponse(BaseModel):
    """비동기 워크플로우 job 생성 응답 계약."""

    job_id: str
    request_id: str
    company_name: str
    status: WorkflowJobStatus
    submitted_at: str
    status_url: str
    result_url: str


class WorkflowJobStatusResponse(BaseModel):
    """비동기 워크플로우 job 상태 조회 응답 계약."""

    job_id: str
    request_id: str
    company_name: str
    status: WorkflowJobStatus
    submitted_at: str
    started_at: str | None = None
    finished_at: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    step_summary: dict[str, int] | None = None


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
