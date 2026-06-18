from __future__ import annotations

import logging
import re
from typing import Any

from backend.rag.chroma_client import get_industry_collection

logger = logging.getLogger(__name__)

DEFAULT_TOP_K = 5
MAX_SUMMARY_LENGTH = 1200

_PRIORITY_KEYWORDS = (
    "평가요소",
    "사업위험",
    "재무위험",
    "수주잔고",
    "PF",
    "부채비율",
    "EBITDA",
    "차입금",
    "시장지위",
    "사업포트폴리오",
    "재무융통성",
    "리스크",
)

_NOISE_KEYWORDS = (
    "연락처",
    "이메일",
    "저자",
    "연구원",
    "애널리스트",
    "Analyst",
    "본 보고서",
    "공시",
    "무단",
    "저작권",
    "Copyright",
)

_NOISE_PATTERNS = (
    re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"),
    re.compile(r"\b0\d{1,2}[-.)\s]?\d{3,4}[-.\s]?\d{4}\b"),
    re.compile(r"^\s*\d+\s*$"),
    re.compile(r"^\s*[-–—]?\s*\d+\s*[-–—]?\s*$"),
)

_KEY_RISK_KEYWORDS = (
    "리스크",
    "위험",
    "취약",
    "부담",
    "변동",
    "규제",
    "경쟁",
    "하락",
    "악화",
)

_CREDIT_ASSESSMENT_KEYWORDS = (
    "평가요소",
    "평가항목",
    "EBITDA",
    "부채비율",
    "차입금의존도",
    "수주잔고",
    "시장지위",
    "수익성",
)

_FACTOR_MIN_LEN = 20
_FACTOR_MAX_LEN = 120
_FACTOR_MAX_COUNT = 5


def retrieve_industry_methodology(
    *,
    query: str | None = None,
    industry_name: str | None = None,
    ksic_code: str | None = None,
    sub_sector: str | None = None,
    top_k: int = DEFAULT_TOP_K,
    collection: Any | None = None,
) -> dict[str, Any]:
    """업종 신용평가방법론 청크와 출처 메타데이터를 검색한다.

    인프라 오류는 호출자에게 예외로 전파하지 않고 unavailable 페이로드로 반환한다.
    """
    resolved_industry_name = industry_name or ""
    try:
        target_collection = collection or get_industry_collection()
        where = _build_where_filter(
            industry_name=industry_name,
            ksic_code=ksic_code,
            sub_sector=sub_sector,
        )
        query_text = _build_query_text(
            query=query,
            industry_name=industry_name,
            ksic_code=ksic_code,
            sub_sector=sub_sector,
        )
        result = target_collection.query(
            query_texts=[query_text],
            n_results=max(top_k, 1),
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        documents = _first_list(result.get("documents"))
        metadatas = _first_list(result.get("metadatas"))
        distances = _first_list(result.get("distances"))
        sources = _build_sources(metadatas, distances)
        if not sources:
            return _unavailable_payload(resolved_industry_name, "검색 결과 없음")
        inferred_industry_name = _infer_industry_name(
            requested=resolved_industry_name,
            sources=sources,
        )

        return {
            "industry_methodology": {
                "industry_name": inferred_industry_name,
                "summary": _build_methodology_summary(documents),
                "key_risk_factors": _extract_factor_sentences(
                    documents, _KEY_RISK_KEYWORDS
                ),
                "credit_assessment_factors": _extract_factor_sentences(
                    documents, _CREDIT_ASSESSMENT_KEYWORDS
                ),
                "source_count": len(sources),
                "unavailable": False,
                "error": None,
            },
            "methodology_sources": sources,
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "industry_rag_retrieval_failed industry_name=%s error=%s",
            resolved_industry_name,
            exc,
        )
        return _unavailable_payload(resolved_industry_name, str(exc))


def _build_query_text(
    *,
    query: str | None,
    industry_name: str | None,
    ksic_code: str | None,
    sub_sector: str | None,
) -> str:
    parts = [
        value
        for value in [query, industry_name, ksic_code, sub_sector, "신용평가방법론"]
        if value
    ]
    return " ".join(parts) or "업종별 신용평가방법론"


def _build_where_filter(
    *,
    industry_name: str | None,
    ksic_code: str | None,
    sub_sector: str | None,
) -> dict[str, Any] | None:
    filters = []
    if industry_name:
        filters.append({"industry_name": industry_name})
    if ksic_code:
        filters.append({"ksic_code": ksic_code})
    if sub_sector:
        filters.append({"sub_sector": sub_sector})
    if not filters:
        return None
    if len(filters) == 1:
        return filters[0]
    return {"$and": filters}


def _build_sources(
    metadatas: list[Any],
    distances: list[Any],
) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for index, metadata in enumerate(metadatas):
        if not isinstance(metadata, dict):
            metadata = {}
        distance = _safe_float(distances[index] if index < len(distances) else None)
        sources.append(
            {
                "filename": str(metadata.get("filename", "")),
                "page": int(metadata.get("page", 0) or 0),
                "score": _distance_to_score(distance),
                "industry_name": str(metadata.get("industry_name", "")),
                "ksic_code": str(metadata.get("ksic_code", "")),
                "sub_sector": str(metadata.get("sub_sector", "")),
            }
        )
    return sources


def _build_methodology_summary(documents: list[Any]) -> str:
    candidates = _extract_summary_candidates(documents)
    if not candidates:
        return _truncate_summary(_fallback_clean_text(documents))

    ranked_candidates = sorted(
        candidates,
        key=lambda candidate: (-candidate["priority_score"], candidate["index"]),
    )
    summary_parts: list[str] = []
    current_length = 0
    for candidate in ranked_candidates:
        text = str(candidate["text"])
        separator_length = 1 if summary_parts else 0
        next_length = current_length + separator_length + len(text)
        if next_length > MAX_SUMMARY_LENGTH:
            continue
        summary_parts.append(text)
        current_length = next_length

    if not summary_parts and ranked_candidates:
        return _truncate_summary(str(ranked_candidates[0]["text"]))
    return _truncate_summary(" ".join(summary_parts))


def _extract_summary_candidates(documents: list[Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, sentence in enumerate(_split_documents_into_sentences(documents)):
        cleaned = _clean_summary_sentence(sentence)
        if not cleaned or _is_noise_sentence(cleaned):
            continue
        normalized = _normalize_for_dedup(cleaned)
        if normalized in seen:
            continue
        seen.add(normalized)
        candidates.append(
            {
                "index": index,
                "text": cleaned,
                "priority_score": _priority_score(cleaned),
            }
        )
    return candidates


def _split_documents_into_sentences(documents: list[Any]) -> list[str]:
    sentences: list[str] = []
    for document in documents:
        text = str(document).strip()
        if not text:
            continue
        normalized_text = re.sub(r"\s+", " ", text)
        normalized_text = re.sub(r"(다\.|임\.|함\.)", r"\1\n", normalized_text)
        normalized_text = re.sub(r"([.!?。])\s+", r"\1\n", normalized_text)
        sentences.extend(
            segment.strip() for segment in normalized_text.splitlines() if segment.strip()
        )
    return sentences


def _clean_summary_sentence(sentence: str) -> str:
    cleaned = re.sub(r"\s+", " ", sentence).strip()
    cleaned = re.sub(r"[-–—]\s*\d+\s*[-–—]", " ", cleaned)
    return cleaned.strip()


def _is_noise_sentence(sentence: str) -> bool:
    if len(sentence) < 15:
        return True
    if any(pattern.search(sentence) for pattern in _NOISE_PATTERNS):
        return True
    return any(keyword in sentence for keyword in _NOISE_KEYWORDS)


def _normalize_for_dedup(sentence: str) -> str:
    return re.sub(r"\s+", "", sentence).lower()


def _priority_score(sentence: str) -> int:
    return sum(1 for keyword in _PRIORITY_KEYWORDS if keyword in sentence)


def _fallback_clean_text(documents: list[Any]) -> str:
    chunks = []
    for document in documents:
        cleaned = _clean_summary_sentence(str(document))
        if cleaned and not any(pattern.search(cleaned) for pattern in _NOISE_PATTERNS):
            chunks.append(cleaned)
    return " ".join(chunks)


def _extract_factor_sentences(
    documents: list[Any],
    keywords: tuple[str, ...],
    max_count: int = _FACTOR_MAX_COUNT,
) -> list[str]:
    """키워드를 포함하는 20~120자 문장을 최대 max_count개 추출한다."""
    results: list[str] = []
    seen: set[str] = set()
    for sentence in _split_documents_into_sentences(documents):
        cleaned = _clean_summary_sentence(sentence)
        if not cleaned or _is_noise_sentence(cleaned):
            continue
        if len(cleaned) < _FACTOR_MIN_LEN or len(cleaned) > _FACTOR_MAX_LEN:
            continue
        if not any(keyword in cleaned for keyword in keywords):
            continue
        normalized = _normalize_for_dedup(cleaned)
        if normalized in seen:
            continue
        seen.add(normalized)
        results.append(cleaned)
        if len(results) >= max_count:
            break
    return results


def _truncate_summary(summary: str) -> str:
    if len(summary) <= MAX_SUMMARY_LENGTH:
        return summary
    return summary[:MAX_SUMMARY_LENGTH].rstrip()


def _infer_industry_name(
    *,
    requested: str,
    sources: list[dict[str, Any]],
) -> str:
    if requested:
        return requested
    for source in sources:
        industry_name = source.get("industry_name")
        if industry_name:
            return str(industry_name)
    return ""


def _unavailable_payload(industry_name: str, error: str) -> dict[str, Any]:
    return {
        "industry_methodology": {
            "industry_name": industry_name,
            "summary": "",
            "key_risk_factors": [],
            "credit_assessment_factors": [],
            "source_count": 0,
            "unavailable": True,
            "error": error,
        },
        "methodology_sources": [],
    }


def _first_list(value: Any) -> list[Any]:
    if isinstance(value, list) and value and isinstance(value[0], list):
        return value[0]
    if isinstance(value, list):
        return value
    return []


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _distance_to_score(distance: float | None) -> float:
    if distance is None:
        return 0.0
    return max(0.0, min(1.0, 1.0 / (1.0 + distance)))
