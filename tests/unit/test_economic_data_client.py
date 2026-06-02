from __future__ import annotations

import pytest

from backend.integrations import economic_data_client


def test_get_ecos_api_key_returns_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(economic_data_client.ECOS_API_KEY_ENV, "ecos-key")

    assert economic_data_client.get_ecos_api_key() == "ecos-key"


def test_fetch_ecos_statistic_rows_builds_request_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"StatisticSearch": {"row": [{"DATA_VALUE": "1.23"}]}}

    def fake_get(url: str, *, timeout: int) -> FakeResponse:
        captured["url"] = url
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setenv(economic_data_client.ECOS_API_KEY_ENV, "ecos-key")
    monkeypatch.setattr(economic_data_client.requests, "get", fake_get)

    rows = economic_data_client.fetch_ecos_statistic_rows(
        "722Y001",
        "A",
        "2024",
        "2024",
        "0101000",
        end_row=5,
    )

    assert rows == [{"DATA_VALUE": "1.23"}]
    assert captured["url"] == (
        "https://ecos.bok.or.kr/api/StatisticSearch/ecos-key/json/kr/"
        "1/5/722Y001/A/2024/2024/0101000"
    )
    assert captured["timeout"] == 10


def test_extract_ecos_float_series_skips_invalid_values() -> None:
    rows = [
        {"DATA_VALUE": "1.0"},
        {"DATA_VALUE": ""},
        {"DATA_VALUE": "abc"},
        {"DATA_VALUE": "2.5"},
    ]

    assert economic_data_client.extract_ecos_float_series(rows) == [1.0, 2.5]


def test_fetch_kosis_parameter_data_returns_empty_without_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(economic_data_client.KOSIS_API_KEY_ENV, raising=False)

    assert economic_data_client.fetch_kosis_parameter_data("DT_1KC2020") == []


def test_fetch_kosis_parameter_data_builds_request_params(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        def json(self) -> list[dict[str, str]]:
            return [{"PRD_DE": "202501", "DT": "101.2"}]

    def fake_get(
        url: str,
        *,
        params: dict[str, str],
        timeout: int,
    ) -> FakeResponse:
        captured["url"] = url
        captured["params"] = params
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setenv(economic_data_client.KOSIS_API_KEY_ENV, "kosis-key")
    monkeypatch.setattr(economic_data_client.requests, "get", fake_get)

    rows = economic_data_client.fetch_kosis_parameter_data("DT_1KC2020", itm_id="ALL")

    assert rows == [{"PRD_DE": "202501", "DT": "101.2"}]
    assert captured["url"] == "https://kosis.kr/openapi/Param/statisticsParameterData.do"
    assert captured["params"] == {
        "method": "getList",
        "apiKey": "kosis-key",
        "itmId": "ALL",
        "objL1": "ALL",
        "format": "json",
        "jsonVD": "Y",
        "prdSe": "M",
        "newEstPrdCnt": "13",
        "orgId": "101",
        "tblId": "DT_1KC2020",
    }
    assert captured["timeout"] == 10


def test_extract_kosis_yoy_from_rows_returns_recent_change() -> None:
    rows = [
        {
            "C1_NM": "정보통신업",
            "ITM_NM": "불변지수",
            "PRD_DE": f"2024{month:02d}",
            "DT": str(100 + month),
        }
        for month in range(1, 14)
    ]

    yoy = economic_data_client.extract_kosis_yoy_from_rows(
        rows,
        "정보통신업",
        itm_keyword="불변",
    )

    assert yoy == pytest.approx((113 - 101) / 101)

