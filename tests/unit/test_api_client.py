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
