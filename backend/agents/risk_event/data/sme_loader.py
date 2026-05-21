"""SME 데이터 로더

financial_features.csv 또는 DB에서 기업 재무 데이터를 로드한다.
현 단계(CSV 기반)에서는 파일을 직접 읽고, 이후 DB 연동 시 get_by_corp_code만 수정한다.
"""

from __future__ import annotations

import csv
import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

# 기본 CSV 경로 (환경변수로 오버라이드 가능)
_DEFAULT_FINANCIAL_CSV = Path(__file__).parents[3] / "ksm_result" / "financial_features.csv"
_DEFAULT_SME_CSV = Path(__file__).parents[3] / "ksm_result" / "sme_list.csv"

FINANCIAL_CSV_PATH = Path(os.getenv("FINANCIAL_CSV_PATH", str(_DEFAULT_FINANCIAL_CSV)))
SME_CSV_PATH = Path(os.getenv("SME_CSV_PATH", str(_DEFAULT_SME_CSV)))


# ─── CSV 로더 ─────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _load_financial_csv() -> list[dict]:
    """financial_features.csv를 메모리에 로드한다 (최초 1회)."""
    if not FINANCIAL_CSV_PATH.exists():
        return []
    with open(FINANCIAL_CSV_PATH, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


@lru_cache(maxsize=1)
def _load_sme_csv() -> list[dict]:
    """sme_list.csv를 메모리에 로드한다 (최초 1회)."""
    if not SME_CSV_PATH.exists():
        return []
    with open(SME_CSV_PATH, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


# ─── 공개 API ─────────────────────────────────────────────────────────────────

def get_financial_rows(corp_code: str) -> list[dict]:
    """특정 기업의 연도별 재무 데이터를 반환한다.

    Returns:
        financial_features.csv에서 해당 corp_code 행 목록 (연도 오름차순)
    """
    rows = [
        r for r in _load_financial_csv()
        if str(r.get("corp_code", "")).zfill(8) == str(corp_code).zfill(8)
    ]
    return sorted(rows, key=lambda r: int(r.get("year", 0)))


def get_company_info(corp_code: str) -> Optional[dict]:
    """sme_list.csv에서 기업 기본 정보를 반환한다."""
    for row in _load_sme_csv():
        if str(row.get("corp_code", "")).zfill(8) == str(corp_code).zfill(8):
            return row
    return None


def search_companies_by_name(keyword: str) -> list[dict]:
    """기업명 키워드로 후보 기업 목록을 반환한다."""
    return [
        r for r in _load_sme_csv()
        if keyword in str(r.get("corp_name", ""))
    ]


def get_all_corp_codes() -> list[str]:
    """전체 중소기업 corp_code 목록을 반환한다."""
    return [
        str(r.get("corp_code", "")).zfill(8)
        for r in _load_sme_csv()
    ]


def reload_cache() -> None:
    """캐시를 강제 초기화한다 (파일 갱신 시 사용)."""
    _load_financial_csv.cache_clear()
    _load_sme_csv.cache_clear()
