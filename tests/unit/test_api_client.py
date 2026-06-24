from __future__ import annotations

import pytest

import backend.common.api_client as api_client
import backend.tools.news as news


def _clear_llm_env(monkeypatch) -> None:
    for env_name in (
        "OPEN_ROUTER_API_KEY",
        "OPENROUTER_API_KEY",
        "OPEN_ROUTER_BASE_URL",
        "OPENROUTER_BASE_URL",
        "OPEN_ROUTER_MODEL",
        "OPENROUTER_MODEL",
        "OPEN_ROUTER_SITE_URL",
        "OPENROUTER_SITE_URL",
        "OPEN_ROUTER_APP_NAME",
        "OPENROUTER_APP_NAME",
        "OPEN_AI_API_KEY",
        "OPENAI_API_KEY",
        "OPEN_API_KEY",
        "OPENAI_MODEL",
        "OPEN_ROUTER_RISK_EVENT_MODEL",
        "OPEN_ROUTER_DECISION_MODEL",
        "OPEN_ROUTER_NEWS_SUMMARY_MODEL",
    ):
        monkeypatch.delenv(env_name, raising=False)


def test_get_llm_client_config_prefers_open_router_settings(monkeypatch) -> None:
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("OPEN_ROUTER_API_KEY", "sk-openrouter")
    monkeypatch.setenv("OPEN_ROUTER_SITE_URL", "https://finagent.example.com")
    monkeypatch.setenv("OPEN_ROUTER_APP_NAME", "FinAgent-SME")

    config = api_client.get_llm_client_config()

    assert config.api_key == "sk-openrouter"
    assert config.provider == "openrouter"
    assert config.base_url == api_client.DEFAULT_OPEN_ROUTER_BASE_URL
    assert config.default_headers == {
        "HTTP-Referer": "https://finagent.example.com",
        "X-Title": "FinAgent-SME",
    }


def test_get_model_name_defaults_to_openai_model_when_no_explicit_model(monkeypatch) -> None:
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("OPEN_ROUTER_API_KEY", "sk-openrouter")

    assert api_client.get_model_name() == api_client.DEFAULT_OPENAI_MODEL


def test_get_model_name_defaults_to_openai_model_without_api_key(monkeypatch) -> None:
    _clear_llm_env(monkeypatch)

    assert api_client.get_model_name() == api_client.DEFAULT_OPENAI_MODEL


def test_get_risk_event_model_name_prefers_stage_specific_env(monkeypatch) -> None:
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("OPEN_ROUTER_RISK_EVENT_MODEL", "google/gemma-3-12b-it")

    assert api_client.get_risk_event_model_name() == "google/gemma-3-12b-it"


def test_get_risk_event_model_name_uses_default_when_env_missing(monkeypatch) -> None:
    _clear_llm_env(monkeypatch)

    assert api_client.get_risk_event_model_name() == api_client.DEFAULT_RISK_EVENT_MODEL


def test_get_decision_model_name_prefers_stage_specific_env(monkeypatch) -> None:
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("OPEN_ROUTER_DECISION_MODEL", "openai/gpt-4o-mini")

    assert api_client.get_decision_model_name() == "openai/gpt-4o-mini"


def test_get_decision_model_name_uses_default_when_env_missing(monkeypatch) -> None:
    _clear_llm_env(monkeypatch)

    assert api_client.get_decision_model_name() == api_client.DEFAULT_DECISION_MODEL


def test_build_llm_client_kwargs_falls_back_to_legacy_openai_key(monkeypatch) -> None:
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("OPEN_AI_API_KEY", "sk-openai")

    client_kwargs = api_client.build_llm_client_kwargs(timeout=30)

    assert client_kwargs == {
        "api_key": "sk-openai",
        "timeout": 30,
    }


def test_get_llm_client_config_error_guides_primary_and_legacy_envs(monkeypatch) -> None:
    _clear_llm_env(monkeypatch)

    with pytest.raises(EnvironmentError) as exc_info:
        api_client.get_llm_client_config()

    assert "OPEN_ROUTER_API_KEY" in str(exc_info.value)
    assert "OPEN_AI_API_KEY" in str(exc_info.value)


def test_news_get_openai_client_uses_open_router_kwargs(monkeypatch) -> None:
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("OPEN_ROUTER_API_KEY", "sk-openrouter")
    monkeypatch.setenv("OPEN_ROUTER_BASE_URL", "https://openrouter.example.com/api/v1")
    monkeypatch.setenv("OPEN_ROUTER_SITE_URL", "https://finagent.example.com")
    monkeypatch.setenv("OPEN_ROUTER_APP_NAME", "FinAgent-SME")

    captured_kwargs: dict[str, str | dict[str, str]] = {}

    class FakeClient:
        def __init__(self, **kwargs) -> None:
            captured_kwargs.update(kwargs)

    monkeypatch.setattr(news, "get_openai_class", lambda: FakeClient)

    client = news.get_openai_client()

    assert isinstance(client, FakeClient)
    assert captured_kwargs == {
        "api_key": "sk-openrouter",
        "base_url": "https://openrouter.example.com/api/v1",
        "default_headers": {
            "HTTP-Referer": "https://finagent.example.com",
            "X-Title": "FinAgent-SME",
        },
    }


def test_news_summary_model_prefers_stage_specific_env(monkeypatch) -> None:
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("OPEN_ROUTER_NEWS_SUMMARY_MODEL", "qwen/qwen-2.5-7b-instruct")

    assert news.get_news_summary_model() == "qwen/qwen-2.5-7b-instruct"


def test_news_classify_article_relevance_accepts_social_article_with_company_context() -> None:
    label, meta = news._classify_article_relevance(
        title="테스트기업 공장 화재로 생산 일부 중단",
        content=(
            "테스트기업 공장에서 화재가 발생했다. "
            "회사 측은 직원 인명 피해는 없다고 밝혔다. "
            "생산라인 일부가 중단돼 복구 작업을 진행 중이다."
        ),
        corp_name="테스트기업",
    )

    assert label == "relevant"
    assert meta["score"] >= 5


def test_news_classify_article_relevance_rejects_unrelated_article() -> None:
    label, meta = news._classify_article_relevance(
        title="프로야구 스타 선수 맹활약",
        content="홈런 두 개를 기록하며 팀 승리를 이끌었다.",
        corp_name="테스트기업",
    )

    assert label == "irrelevant"
    assert meta["score"] < 2
    assert meta["title_gate_rejected"] is True


def test_extract_company_sentences_keeps_company_focused_context() -> None:
    extracted = news._extract_company_sentences(
        title="테스트기업 압수수색",
        content=(
            "테스트기업 본사가 압수수색을 받았다. "
            "회사 측은 관련 자료를 제출했다고 밝혔다. "
            "같은 업종의 다른 기업 주가는 혼조세를 보였다."
        ),
        corp_name="테스트기업",
    )

    assert "테스트기업 본사가 압수수색을 받았다." in extracted
    assert "회사 측은 관련 자료를 제출했다고 밝혔다." in extracted


def test_news_classify_article_relevance_rejects_other_company_dominant_market_article() -> None:
    label, meta = news._classify_article_relevance(
        title="3년간 8개사 상장 도운 코넥스 특급 도우미 'IBK투자증권'",
        content=(
            "IBK투자증권이 코넥스 기업의 상장을 지원하며 시장에서 주목받고 있다. "
            "삼미금속 등 일부 기업이 지원 사례로 언급됐다. "
            "IBK투자증권의 중소기업 지원 전략이 긍정적 평가를 받는다."
        ),
        corp_name="삼미금속",
    )

    assert label == "irrelevant"
    assert meta["title_gate_rejected"] is True


def test_has_sufficient_target_evidence_requires_direct_company_anchor() -> None:
    aliases = news._build_company_aliases("삼미금속")

    assert news._has_sufficient_target_evidence(
        "삼미금속 공장이 화재를 입었다. 회사 측은 복구 중이라고 밝혔다.",
        aliases,
    ) is True
    assert news._has_sufficient_target_evidence(
        "회사 측은 복구 중이라고 밝혔다. 생산 차질은 제한적이라고 설명했다.",
        aliases,
    ) is True
    assert news._has_sufficient_target_evidence(
        "코넥스 시장 지원 사례가 소개됐다. 중소기업 지원 전략이 주목받는다.",
        aliases,
    ) is False


def test_news_classify_article_relevance_keeps_financing_article_for_target_company() -> None:
    label, meta = news._classify_article_relevance(
        title="삼미금속, 300억 규모 전환사채 발행 결정",
        content=(
            "삼미금속은 300억원 규모의 전환사채 발행을 결정했다. "
            "신사업 확장과 운영자금 확보를 위한 자금조달 목적이라고 밝혔다. "
            "향후 투자 집행과 매출 성장 가속화가 기대된다."
        ),
        corp_name="삼미금속",
    )

    assert label == "relevant"
    assert meta["finance_event_hit"] is True


def test_news_classify_article_relevance_rejects_exception_only_market_article() -> None:
    label, meta = news._classify_article_relevance(
        title="심사도 합병 후도 험난…스팩상장 ‘유명무실’",
        content=(
            "스팩 시장 전반의 위축이 이어지고 있다. "
            "지난해부터 올해까지 스팩 합병으로 코스닥에 상장한 기업은 총 9곳이지만 "
            "이중 삼미금속과 삼익제약을 제외한 7곳의 종가는 합병가액을 회복하지 못했다. "
            "다른 기업들의 부진이 이어지며 시장 전반의 우려가 커졌다."
        ),
        corp_name="삼미금속",
    )

    assert label == "irrelevant"
    assert meta["title_gate_rejected"] is True
