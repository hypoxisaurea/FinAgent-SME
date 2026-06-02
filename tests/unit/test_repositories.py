from __future__ import annotations

from typing import Any

from backend.data.repositories import company_master
from backend.data.repositories import db_access
from backend.data.repositories import financial_feature


class _FakeResult:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def mappings(self) -> "_FakeResult":
        return self

    def all(self) -> list[dict[str, Any]]:
        return self._rows


class _FakeConnection:
    def __init__(self, engine: "_FakeEngine") -> None:
        self._engine = engine

    def __enter__(self) -> "_FakeConnection":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def execute(self, query: Any, params: dict[str, Any]) -> _FakeResult:
        self._engine.executed_queries.append((str(query), params))
        return _FakeResult(self._engine.rows)


class _FakeEngine:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.executed_queries: list[tuple[str, dict[str, Any]]] = []
        self.disposed = False

    def connect(self) -> _FakeConnection:
        return _FakeConnection(self)

    def dispose(self) -> None:
        self.disposed = True


class _FakeInspector:
    def __init__(self, tables: dict[str, bool]) -> None:
        self._tables = tables

    def has_table(self, table_name: str) -> bool:
        return self._tables.get(table_name, False)


def test_get_financial_rows_by_corp_code_queries_postgres_table(
    monkeypatch,
) -> None:
    fake_engine = _FakeEngine(
        [
            {
                "corp_code": "00123456",
                "corp_name": "테스트기업",
                "stock_code": "123456",
                "year": 2024,
                "revenue": 1000,
            }
        ]
    )

    monkeypatch.setattr(
        db_access,
        "create_db_engine",
        lambda: fake_engine,
    )
    monkeypatch.setattr(
        db_access,
        "inspect",
        lambda engine: _FakeInspector(
            {financial_feature.FEATURES_TABLE_NAME: True}
        ),
    )

    rows = financial_feature.get_financial_rows_by_corp_code("123456")

    assert rows == fake_engine.rows
    assert fake_engine.executed_queries[0][1] == {"corp_code": "00123456"}
    assert "FROM financial_features" in fake_engine.executed_queries[0][0]
    assert fake_engine.disposed is True


def test_get_all_corp_codes_returns_empty_when_master_table_is_missing(
    monkeypatch,
) -> None:
    fake_engine = _FakeEngine([])

    monkeypatch.setattr(
        db_access,
        "create_db_engine",
        lambda: fake_engine,
    )
    monkeypatch.setattr(
        db_access,
        "inspect",
        lambda engine: _FakeInspector(
            {company_master.SME_LIST_TABLE_NAME: False}
        ),
    )

    corp_codes = company_master.get_all_corp_codes()

    assert corp_codes == []
    assert fake_engine.executed_queries == []
    assert fake_engine.disposed is True


def test_find_company_row_by_name_returns_first_match(monkeypatch) -> None:
    fake_engine = _FakeEngine(
        [
            {
                "corp_code": "00123456",
                "corp_name": "테스트기업",
            }
        ]
    )

    monkeypatch.setattr(
        db_access,
        "create_db_engine",
        lambda: fake_engine,
    )
    monkeypatch.setattr(
        db_access,
        "inspect",
        lambda engine: _FakeInspector(
            {company_master.SME_LIST_TABLE_NAME: True}
        ),
    )

    row = company_master.find_company_row_by_name("테스트기업")

    assert row == {
        "corp_code": "00123456",
        "corp_name": "테스트기업",
    }
    assert fake_engine.executed_queries[0][1] == {"company_name": "테스트기업"}
    assert "WHERE corp_name = :company_name" in fake_engine.executed_queries[0][0]
