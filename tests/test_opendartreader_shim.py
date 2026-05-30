# ruff: noqa: E402

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from agents.financial_analyst import financial_tools
from agents.industry_analyst import industry_tools
from opendartreader import OpenDartReader


def test_opendartreader_shim_exposes_vendor_reader() -> None:
    assert callable(OpenDartReader)


def test_agent_tools_use_opendartreader_shim() -> None:
    assert financial_tools.OpenDartReader is OpenDartReader
    assert industry_tools.OpenDartReader is OpenDartReader
