from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

import backend.opendartreader as opendartreader_shim
from backend.opendartreader import OpenDartReader
from backend.tools import financial, industry


def test_opendartreader_shim_exposes_vendor_reader() -> None:
    assert callable(OpenDartReader)


def test_agent_tools_use_opendartreader_shim() -> None:
    assert financial.OpenDartReader is OpenDartReader
    assert industry.OpenDartReader is OpenDartReader


def test_opendartreader_shim_redirects_cache_outside_backend(
    monkeypatch,
    tmp_path: Path,
) -> None:
    cache_dir = tmp_path / "dart-cache"
    cache_file = cache_dir / (
        f"opendartreader_corp_codes_{datetime.today().strftime('%Y%m%d')}.pkl"
    )
    corp_codes_df = pd.DataFrame(
        [
            {
                "corp_code": "00123456",
                "corp_name": "테스트기업",
                "stock_code": "123456",
            }
        ]
    )
    call_count = {"count": 0}

    def fake_corp_codes(api_key: str) -> pd.DataFrame:
        call_count["count"] += 1
        assert api_key == "test-key"
        return corp_codes_df

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENDARTREADER_CACHE_DIR", str(cache_dir))
    monkeypatch.setattr(
        opendartreader_shim._vendor_module.dart_list,
        "corp_codes",
        fake_corp_codes,
    )

    reader = OpenDartReader("test-key")
    second_reader = OpenDartReader("test-key")

    assert reader.api_key == "test-key"
    assert second_reader.api_key == "test-key"
    assert call_count["count"] == 1
    assert cache_file.exists()
    assert not (tmp_path / "docs_cache").exists()
