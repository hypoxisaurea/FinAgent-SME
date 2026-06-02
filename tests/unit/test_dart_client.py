from __future__ import annotations

import pytest

from backend.integrations import dart_client


def test_get_dart_api_key_returns_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(dart_client.OPEN_DART_API_KEY_ENV, "test-key")

    assert dart_client.get_dart_api_key() == "test-key"


def test_get_dart_api_key_can_be_optional(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(dart_client.OPEN_DART_API_KEY_ENV, raising=False)

    assert dart_client.get_dart_api_key(required=False) is None


def test_resolve_dart_api_key_prefers_cli_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(dart_client.OPEN_DART_API_KEY_ENV, raising=False)

    assert dart_client.resolve_dart_api_key("cli-key") == "cli-key"


def test_get_dart_client_uses_shim(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, str] = {}

    class FakeOpenDartReader:
        def __init__(self, api_key: str) -> None:
            captured["api_key"] = api_key

    monkeypatch.setenv(dart_client.OPEN_DART_API_KEY_ENV, "dart-key")
    monkeypatch.setattr(dart_client, "OpenDartReader", FakeOpenDartReader)

    client = dart_client.get_dart_client()

    assert isinstance(client, FakeOpenDartReader)
    assert captured["api_key"] == "dart-key"


def test_get_dart_json_injects_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"status": "000"}

    def fake_get(url: str, *, params: dict[str, object], timeout: int) -> FakeResponse:
        captured["url"] = url
        captured["params"] = params
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setenv(dart_client.OPEN_DART_API_KEY_ENV, "dart-key")
    monkeypatch.setattr(dart_client.requests, "get", fake_get)

    result = dart_client.get_dart_json("sample.json", params={"corp_code": "00123456"})

    assert result == {"status": "000"}
    assert captured["url"] == "https://opendart.fss.or.kr/api/sample.json"
    assert captured["params"] == {
        "corp_code": "00123456",
        "crtfc_key": "dart-key",
    }
    assert captured["timeout"] == 10


def test_get_dart_json_maps_request_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_get(*args, **kwargs):  # noqa: ANN002, ANN003
        raise dart_client.requests.RequestException("network down")

    monkeypatch.setenv(dart_client.OPEN_DART_API_KEY_ENV, "dart-key")
    monkeypatch.setattr(dart_client.requests, "get", fake_get)

    with pytest.raises(ConnectionError, match="DART API 호출 실패"):
        dart_client.get_dart_json("sample.json")


def test_get_dart_bytes_returns_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResponse:
        content = b"zip-bytes"

        def raise_for_status(self) -> None:
            return None

    def fake_get(*args, **kwargs):  # noqa: ANN002, ANN003
        return FakeResponse()

    monkeypatch.setenv(dart_client.OPEN_DART_API_KEY_ENV, "dart-key")
    monkeypatch.setattr(dart_client.requests, "get", fake_get)

    assert dart_client.get_dart_bytes("document.xml") == b"zip-bytes"


def test_fetch_dart_list_records_validates_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        dart_client,
        "get_dart_json",
        lambda *args, **kwargs: {"status": "013", "message": "no data"},
    )

    with pytest.raises(ValueError, match="DART 공시 목록 조회 실패"):
        dart_client.fetch_dart_list_records(
            corp_code="00123456",
            bgn_de="20240101",
            end_de="20241231",
        )
