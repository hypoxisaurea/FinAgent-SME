from __future__ import annotations

import pandas as pd

from backend.data.services import company_registry_pipeline


class _FakeDart:
    def __init__(self) -> None:
        self.api_key: str | None = None

    def set_api_key(self, *, api_key: str) -> None:
        self.api_key = api_key


def test_execute_dart_pipeline_builds_and_saves_outputs(monkeypatch) -> None:
    fake_dart = _FakeDart()
    final_df = pd.DataFrame([{"corp_code": "001", "revenue": 1000}])
    statement_detail_df = pd.DataFrame([{"corp_code": "001", "current_assets": 500}])
    sme_list_df = pd.DataFrame([{"corp_code": "001"}])
    profile_df = pd.DataFrame([{"corp_code": "001", "ceo_name": "대표자"}])
    captured: dict[str, object] = {}

    monkeypatch.setattr(company_registry_pipeline.company_registry_tools, "dart", fake_dart)
    monkeypatch.setattr(
        company_registry_pipeline.company_registry_tools,
        "resolve_api_key",
        lambda _: "test-key",
    )
    monkeypatch.setattr(
        company_registry_pipeline.company_registry_tools,
        "load_sme_candidates",
        lambda sample_size: (pd.DataFrame(), pd.DataFrame([{"corp_code": "001"}])),
    )
    monkeypatch.setattr(
        company_registry_pipeline.company_registry_tools,
        "run_collection",
        lambda *, sme_df, business_year, report_code: (
            [{"corp_code": "001", "amount": 1000}],
            [{"corp_code": "001", "current_assets": 500}],
            [{"error_type": "NONE"}],
            {"success_count": 1},
        ),
    )
    monkeypatch.setattr(
        company_registry_pipeline.company_registry_tools,
        "build_final_dataframe",
        lambda processed_records: final_df,
    )
    monkeypatch.setattr(
        company_registry_pipeline.company_registry_tools,
        "build_statement_detail_dataframe",
        lambda statement_records: statement_detail_df,
    )
    monkeypatch.setattr(
        company_registry_pipeline,
        "add_created_at_column",
        lambda df, created_at: df.assign(created_at=created_at),
    )
    monkeypatch.setattr(
        company_registry_pipeline.company_registry_tools,
        "build_sme_list_dataframe",
        lambda df: sme_list_df,
    )
    monkeypatch.setattr(
        company_registry_pipeline.company_registry_tools,
        "build_company_profile_dataframe",
        lambda df: (profile_df, [], {"profile_success_count": 1}),
    )

    def _fake_save_outputs_to_database(
        sme_list_input: pd.DataFrame,
        company_profile_input: pd.DataFrame,
        final_input: pd.DataFrame,
        statement_detail_input: pd.DataFrame,
        error_input: pd.DataFrame,
    ) -> dict[str, int]:
        captured["sme_list_df"] = sme_list_input
        captured["company_profile_df"] = company_profile_input
        captured["final_df"] = final_input
        captured["statement_detail_df"] = statement_detail_input
        captured["error_df"] = error_input
        return {
            "sme_list": 1,
            "company_profiles": 1,
            "financial_statement_details": 1,
        }

    monkeypatch.setattr(
        company_registry_pipeline,
        "save_outputs_to_database",
        _fake_save_outputs_to_database,
    )

    result = company_registry_pipeline.execute_dart_pipeline(
        year=2024,
        sample_size=5,
        skip_db_save=False,
    )

    assert fake_dart.api_key == "test-key"
    assert result["status"] == "success"
    assert result["sme_count"] == 1
    assert result["financial_data_count"] == 1
    assert result["financial_statement_detail_count"] == 1
    assert result["company_profile_count"] == 1
    assert result["db_save_counts"] == {
        "sme_list": 1,
        "company_profiles": 1,
        "financial_statement_details": 1,
    }
    assert list(captured["sme_list_df"]["corp_code"]) == ["001"]
    assert list(captured["company_profile_df"]["ceo_name"]) == ["대표자"]
    assert "created_at" in captured["final_df"].columns
    assert "created_at" in captured["statement_detail_df"].columns
    assert "created_at" in captured["company_profile_df"].columns
    assert list(captured["error_df"]["error_type"]) == ["NONE"]


def test_execute_dart_pipeline_skips_db_save_when_requested(monkeypatch) -> None:
    fake_dart = _FakeDart()

    monkeypatch.setattr(company_registry_pipeline.company_registry_tools, "dart", fake_dart)
    monkeypatch.setattr(
        company_registry_pipeline.company_registry_tools,
        "resolve_api_key",
        lambda _: "test-key",
    )
    monkeypatch.setattr(
        company_registry_pipeline.company_registry_tools,
        "load_sme_candidates",
        lambda sample_size: (pd.DataFrame(), pd.DataFrame()),
    )
    monkeypatch.setattr(
        company_registry_pipeline.company_registry_tools,
        "run_collection",
        lambda *, sme_df, business_year, report_code: (
            [],
            [],
            [],
            {"success_count": 0},
        ),
    )
    monkeypatch.setattr(
        company_registry_pipeline.company_registry_tools,
        "build_final_dataframe",
        lambda processed_records: pd.DataFrame(),
    )
    monkeypatch.setattr(
        company_registry_pipeline.company_registry_tools,
        "build_statement_detail_dataframe",
        lambda statement_records: pd.DataFrame(),
    )
    monkeypatch.setattr(
        company_registry_pipeline,
        "add_created_at_column",
        lambda df, created_at: df,
    )
    monkeypatch.setattr(
        company_registry_pipeline.company_registry_tools,
        "build_sme_list_dataframe",
        lambda df: pd.DataFrame(),
    )
    monkeypatch.setattr(
        company_registry_pipeline.company_registry_tools,
        "build_company_profile_dataframe",
        lambda df: (
            pd.DataFrame(),
            [],
            {"profile_success_count": 0, "profile_error_count": 0},
        ),
    )
    monkeypatch.setattr(
        company_registry_pipeline,
        "save_outputs_to_database",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not save")),
    )

    result = company_registry_pipeline.execute_dart_pipeline(
        year=2024,
        sample_size=None,
        skip_db_save=True,
    )

    assert result["status"] == "success"
    assert result["db_save_counts"] == {}
