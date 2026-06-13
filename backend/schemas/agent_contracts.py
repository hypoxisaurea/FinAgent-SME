from __future__ import annotations

from datetime import date
from typing import Any

from backend.schemas.state import BusinessCycle, FinancialRatios
from pydantic import BaseModel, ConfigDict, Field


class AgentInputModel(BaseModel):
    """에이전트 입력 계약 베이스 모델."""

    model_config = ConfigDict(extra="allow")


class AgentOutputModel(BaseModel):
    """에이전트 출력 계약 베이스 모델."""

    model_config = ConfigDict(extra="forbid")


class WorkflowReportPayload(AgentOutputModel):
    """ReportAgent가 생성하는 최종 보고서 페이로드."""

    company_name: str | None = None
    corp_name: str | None = None
    corp_code: str | None = None
    generated_at: str
    decision: str | None = None
    credit_grade: str | None = None
    confidence: float | None = None
    recommended_limit: int | float | None = None
    summary: str
    key_risks: list[str] = Field(default_factory=list)
    recommendation: str


class ValidationCheckPayload(AgentOutputModel):
    """ValidationAgent 단일 체크 결과."""

    name: str
    passed: bool
    detail: str


class ValidationResultPayload(AgentOutputModel):
    """ValidationAgent 검증 요약 페이로드."""

    validation_passed: bool
    pass_rate: float
    passed_checks: int
    total_checks: int
    failed_checks: list[str] = Field(default_factory=list)
    checks: list[ValidationCheckPayload] = Field(default_factory=list)


class CompanyResolverInput(AgentInputModel):
    request_id: str | None = None
    company_name: str


class CompanyResolverOutput(AgentOutputModel):
    company_found: bool
    workflow_status: str | None = None
    workflow_code: str | None = None
    workflow_message: str | None = None
    corp_code: str | None = None
    corp_name: str | None = None
    company_profile: dict[str, Any] | None = None
    company_resolution: dict[str, Any] = Field(default_factory=dict)


class NewsCollectorInput(AgentInputModel):
    request_id: str | None = None
    company_name: str | None = None
    corp_name: str | None = None
    stock_code: str | None = None
    lookback_days: int = 30
    max_articles: int = 20
    company_limit: int | None = None
    summarize: bool = True
    model_name: str | None = None
    database_url: str | None = None
    show_progress: bool = True


class NewsCollectorOutput(AgentOutputModel):
    news_data: list[dict[str, Any]] = Field(default_factory=list)
    news_result: dict[str, Any]
    news_collector_config: dict[str, Any]
    news_tool_runs: list[dict[str, Any]] = Field(default_factory=list)
    news_tool_errors: list[dict[str, Any]] = Field(default_factory=list)


class FinancialAnalystInput(AgentInputModel):
    request_id: str | None = None
    company_name: str | None = None
    corp_code: str
    target_year: int = 2024


class FinancialAnalystOutput(AgentOutputModel):
    financial_statements: dict[str, Any]
    financial_ratios: dict[str, Any]
    company_ratios: dict[str, Any]
    altman_z: dict[str, Any]
    financial_trend: dict[str, Any]
    financial_flags: list[str] = Field(default_factory=list)
    risk_filters: dict[str, Any]
    grade_cap: str | None = None
    total_assets: int | float | None = None
    total_assets_statement: int | float | None = None
    revenue: int | float | None = None
    avg_revenue_last_3y: int | float | None = None
    operating_income: int | float | None = None
    net_income: int | float | None = None
    financial_summary: dict[str, Any]
    financial_tool_runs: list[dict[str, Any]] = Field(default_factory=list)
    financial_tool_errors: list[dict[str, Any]] = Field(default_factory=list)


class IndustryAnalystInput(AgentInputModel):
    request_id: str | None = None
    company_name: str | None = None
    corp_code: str
    financial_ratios: FinancialRatios | dict[str, Any] | None = None
    target_year: int = 2024


class IndustryAnalystOutput(AgentOutputModel):
    ksic_code: str
    industry_summary: dict[str, Any] | str
    industry_outlook: dict[str, Any]
    business_cycle: BusinessCycle | dict[str, Any]
    macro_indicators: dict[str, Any]
    peer_comparison: dict[str, Any] | None = None
    industry_tool_runs: list[dict[str, Any]] = Field(default_factory=list)
    industry_tool_errors: list[dict[str, Any]] = Field(default_factory=list)


class RiskEventInput(AgentInputModel):
    request_id: str | None = None
    company_name: str
    corp_code: str
    news_data: list[dict[str, Any]] = Field(default_factory=list)
    disclosure_data: list[dict[str, Any]] = Field(default_factory=list)
    court_data: list[dict[str, Any]] = Field(default_factory=list)


class DecisionInput(AgentInputModel):
    request_id: str | None = None
    company_name: str = ""
    corp_code: str = ""
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    overall_risk_level: str | None = None
    latest_debt_ratio: float | None = None
    latest_op_margin: float | None = None
    is_net_income_negative: bool = False
    grade_cap: str | None = None
    total_assets: int | float | None = None
    total_assets_statement: int | float | None = None
    revenue: int | float | None = None
    avg_revenue_last_3y: int | float | None = None
    classified_events: list[Any] = Field(default_factory=list)


class DecisionOutputContract(AgentOutputModel):
    company_name: str
    corp_code: str
    grade: str
    grade_score: int
    decision: str
    confidence: float
    reasons: list[str] = Field(default_factory=list)
    recommended_limit: int | None = None
    limit_range: str | None = None
    limit_basis: str = ""
    explanation: dict[str, Any] | None = None
    grade_detail: dict[str, Any]
    processed_at: date
    processing_errors: list[str] = Field(default_factory=list)
    credit_grade: str
    credit_score: int
    decision_confidence: float
    decision_reasons: list[str] = Field(default_factory=list)


class ReportInput(AgentInputModel):
    company_name: str | None = None
    corp_name: str | None = None
    corp_code: str | None = None
    decision: str | None = None
    credit_grade: str | None = None
    decision_confidence: float | None = None
    decision_reasons: list[str] = Field(default_factory=list)
    recommended_limit: int | float | None = None
    explanation: dict[str, Any] | None = None
    overall_risk_level: str | None = None


class ReportOutput(AgentOutputModel):
    report: WorkflowReportPayload


class ValidationInput(AgentInputModel):
    request_id: str | None = None
    company_name: str | None = None
    corp_name: str | None = None
    corp_code: str | None = None
    decision: str | None = None
    credit_grade: str | None = None
    decision_confidence: float | None = None
    decision_reasons: list[str] = Field(default_factory=list)
    recommended_limit: int | float | None = None
    explanation: dict[str, Any] | None = None
    report: WorkflowReportPayload | dict[str, Any] | None = None


class ValidationOutput(AgentOutputModel):
    validation_result: ValidationResultPayload


class MultiModalDocumentInput(AgentInputModel):
    pdf_path: str
    output_dir: str | None = None


class MultiModalDocumentOutput(AgentOutputModel):
    name: str
    pdf_path: str
    output_dir: str
    texts: list[str] = Field(default_factory=list)
    chart_images: list[Any] = Field(default_factory=list)
    page_count: int
