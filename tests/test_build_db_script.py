# ruff: noqa: E402

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from scripts import build_db


def test_build_db_parser_defaults() -> None:
    parser = build_db.build_parser()
    args = parser.parse_args([])

    assert args.year == 2024
    assert args.sample_size is None
    assert args.skip_db_save is False


def test_run_build_db_passes_args_to_pipeline(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_execute_dart_pipeline(
        *,
        year: int,
        sample_size: int | None,
        skip_db_save: bool,
    ) -> dict[str, object]:
        captured["year"] = year
        captured["sample_size"] = sample_size
        captured["skip_db_save"] = skip_db_save
        return {
            "status": "success",
            "sme_count": 3,
            "financial_data_count": 3,
            "db_save_counts": {"sme_list": 3},
        }

    monkeypatch.setattr(build_db, "execute_dart_pipeline", fake_execute_dart_pipeline)
    parser = build_db.build_parser()
    args = parser.parse_args(
        [
            "--year",
            "2023",
            "--sample-size",
            "10",
            "--skip-db-save",
        ]
    )

    result = build_db.run_build_db(args)

    assert captured == {
        "year": 2023,
        "sample_size": 10,
        "skip_db_save": True,
    }
    assert result["status"] == "success"
