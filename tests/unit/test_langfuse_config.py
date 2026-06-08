from __future__ import annotations

from backend.common import langfuse as langfuse_module


def test_build_openai_trace_kwargs_returns_empty_when_langfuse_disabled(
    monkeypatch,
) -> None:
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)

    kwargs = langfuse_module.build_openai_trace_kwargs(
        name="decision.explanation",
        session_id="req-test",
        tags=["decision"],
        metadata={"company_name": "테스트기업"},
    )

    assert kwargs == {}


def test_build_openai_trace_kwargs_includes_langfuse_metadata_when_enabled(
    monkeypatch,
) -> None:
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    monkeypatch.setenv("FINAGENT_ENABLE_LANGFUSE_IN_TESTS", "true")
    monkeypatch.setattr(langfuse_module, "_has_langfuse_sdk", lambda: True)

    kwargs = langfuse_module.build_openai_trace_kwargs(
        name="risk_event.sentiment_analysis",
        session_id="req-test",
        tags=["risk_event", "sentiment"],
        metadata={"company_name": "테스트기업", "agent_name": "risk_event"},
    )

    assert kwargs["name"] == "risk_event.sentiment_analysis"
    assert kwargs["metadata"]["langfuse_session_id"] == "req-test"
    assert kwargs["metadata"]["langfuse_tags"] == ["risk_event", "sentiment"]
    assert kwargs["metadata"]["langfuse_metadata"] == {
        "company_name": "테스트기업",
        "agent_name": "risk_event",
    }


def test_start_as_current_observation_is_safe_when_langfuse_disabled(
    monkeypatch,
) -> None:
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)

    with langfuse_module.start_as_current_observation(
        name="credit_workflow",
        as_type="chain",
        input={"company_name": "테스트기업"},
        metadata={"request_id": "req-test"},
    ) as observation:
        observation.update(output={"status": "success"})
