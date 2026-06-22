"""KR 신용평가방법론 기반 재무지표별 등급 매핑

JSON 캐시(backend/rag/credit_thresholds/{sub_sector}.json)에서
임계값을 읽어 5개 재무지표(EBITDA마진/순차입금·EBITDA/EBITDA·총금융비용/
부채비율/차입금의존도)의 KR 등급을 산출한다.

한계:
- EBITDA/총금융비용: PDF 기준은 이자비용+매출채권처분손실+자본화이자비용이지만
  현재 calc_financial_ratios는 이자비용만 사용 → 과대평가 가능성 있음
- 사업항목(50%) 미반영 → 합산 신용등급이 아닌 지표별 참고 등급만 제공
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_THRESHOLDS_DIR = Path(__file__).resolve().parents[1] / "rag" / "credit_thresholds"

_SCOPE_NOTE = (
    "사업항목(50%) 미반영, KR 공시 등급-점수 환산표 없어 합산 점수 미생성. "
    "지표별 등급만 참고용으로 제공"
)

# calc_financial_ratios 반환 키 → JSON 메트릭 키 (동일하므로 그대로 사용)
# unit="percent" 지표는 소수값(0~1 또는 소수비율)을 ×100 해서 비교
_PERCENT_METRICS = {"ebitda_margin", "debt_ratio", "borrow_dep"}


def calc_kr_financial_grades(
    ratios: dict[str, Any],
    sub_sector: str,
) -> dict[str, Any] | None:
    """재무비율 dict와 sub_sector를 받아 KR 방법론 기반 지표별 등급을 반환한다.

    Args:
        ratios:     calc_financial_ratios 반환 dict (또는 동일 키 포함 dict)
        sub_sector: "corporate_제조" | "제약업" 등 (JSON 파일명과 일치해야 함)

    Returns:
        {
            "methodology": str,
            "per_metric_grades": {
                "<metric>": {
                    "grade":  str | None,   # None = 산출불가 (값 없음)
                    "label":  str,
                    "weight": str,          # 예: "5%"
                    "value":  float | None, # 비교에 사용된 실제 값 (percent 기준)
                }
            },
            "scope_note": str,
        }
        지원하지 않는 sub_sector이면 None 반환.
    """
    cache_path = _THRESHOLDS_DIR / f"{sub_sector}.json"
    if not cache_path.exists():
        logger.warning("kr_grade_mapper: 지원하지 않는 sub_sector=%s (파일 없음)", sub_sector)
        return None

    with cache_path.open(encoding="utf-8") as f:
        spec = json.load(f)

    per_metric: dict[str, Any] = {}
    for metric_key, meta in spec["metrics"].items():
        raw_value: float | None = ratios.get(metric_key)

        # None이면 등급 산출불가
        if raw_value is None:
            per_metric[metric_key] = {
                "grade":  None,
                "label":  meta["label"],
                "weight": f"{meta['weight_pct']:g}%",
                "value":  None,
                "note":   "산출불가",
            }
            continue

        # percent 단위 지표는 소수 → % 변환
        compare_value = raw_value * 100.0 if metric_key in _PERCENT_METRICS else raw_value

        grade = _lookup_grade(compare_value, meta["thresholds"])
        per_metric[metric_key] = {
            "grade":  grade,
            "label":  meta["label"],
            "weight": f"{meta['weight_pct']:g}%",
            "value":  round(compare_value, 4),
        }

    return {
        "methodology":       spec["methodology"],
        "per_metric_grades": per_metric,
        "scope_note":        _SCOPE_NOTE,
    }


def _lookup_grade(value: float, thresholds: list[dict[str, Any]]) -> str:
    """임계값 리스트를 순서대로 평가해 첫 번째 일치 등급을 반환한다."""
    for t in thresholds:
        op = t["op"]
        tv = t["value"]
        if op == "gte" and value >= tv:
            return t["grade"]
        if op == "gt"  and value >  tv:
            return t["grade"]
        if op == "lte" and value <= tv:
            return t["grade"]
        if op == "lt"  and value <  tv:
            return t["grade"]
    return "B"  # 안전망 (정상적인 JSON이면 도달하지 않음)
