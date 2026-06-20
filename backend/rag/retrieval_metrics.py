"""Hit@k / MRR 정량 평가 — Dense 단독 vs Hybrid(BM25+Dense) 비교.

evaluation.py(RAGAS)와 독립적으로 동작하며 LLM 호출 없이 오프라인 실행된다.

Gold chunk 식별:
    reference 텍스트를 KoSRoberta로 임베딩 → 필터 범위 내 청크 중
    cosine 거리 < GOLD_MAX_DISTANCE 상위 GOLD_TOP_N개를 정답 집합으로 지정.

Dense 검색:
    user_input → collection.query() 벡터 검색 → top-k IDs

Hybrid 검색:
    user_input → Dense top-k + BM25 top-k → RRF 병합 → top-k IDs
    (BM25-only 문서도 최종 순위에 포함될 수 있음)
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.rag.chroma_client import get_industry_collection
from backend.rag.retriever import (
    _build_bm25_index,
    _build_where_filter,
    _rrf_merge,
    _tokenize_for_bm25,
)

logger = logging.getLogger(__name__)

EVAL_DATASET_PATH = Path(__file__).parent / "eval_datasets" / "industry_methodology.jsonl"
ARTIFACTS_DIR = Path(__file__).parent / "artifacts"

GOLD_TOP_N = 3
GOLD_MAX_DISTANCE = 0.8


# ── 데이터 로드 ────────────────────────────────────────────────────────────────


def _load_eval_cases(path: Path = EVAL_DATASET_PATH) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped:
                cases.append(json.loads(stripped))
    return cases


# ── Gold chunk 식별 ────────────────────────────────────────────────────────────


def _find_gold_chunk_ids(
    reference: str,
    collection: Any,
    where: dict[str, Any] | None,
    top_n: int = GOLD_TOP_N,
    max_distance: float = GOLD_MAX_DISTANCE,
) -> set[str]:
    """reference를 KoSRoberta로 임베딩해 가장 유사한 청크를 gold로 지정."""
    result = collection.query(
        query_texts=[reference],
        n_results=top_n,
        where=where,
        include=["distances"],
    )
    ids: list[str] = (result.get("ids") or [[]])[0]
    distances: list[float] = (result.get("distances") or [[]])[0]
    gold = {did for did, dist in zip(ids, distances) if dist < max_distance}
    logger.debug("gold_chunks case_reference_len=%d gold_count=%d", len(reference), len(gold))
    return gold


# ── 검색 함수 ──────────────────────────────────────────────────────────────────


def _dense_retrieve_ids(
    query_text: str,
    where: dict[str, Any] | None,
    top_k: int,
    collection: Any,
) -> list[str]:
    """Dense 벡터 검색만 수행 — 청크 ID 목록 반환."""
    result = collection.query(
        query_texts=[query_text],
        n_results=max(top_k, 1),
        where=where,
        include=["metadatas"],
    )
    return (result.get("ids") or [[]])[0]


def _hybrid_retrieve_ids(
    query_text: str,
    where: dict[str, Any] | None,
    top_k: int,
    collection: Any,
) -> list[str]:
    """BM25 + Dense Hybrid 검색 (RRF 병합) — 청크 ID 목록 반환.

    BM25-only 문서도 RRF 후 top-k에 포함될 수 있어 Dense 단독과 차이가 생긴다.
    """
    # Dense
    dense_ids = _dense_retrieve_ids(query_text, where, top_k, collection)

    # BM25: 필터 범위 전체 청크 대상
    all_result = collection.get(where=where, include=["documents"])
    all_docs: list[str] = all_result.get("documents", [])
    all_ids: list[str] = all_result.get("ids", [])

    if not all_docs:
        return dense_ids

    bm25_index = _build_bm25_index(all_docs)
    raw_scores = bm25_index.get_scores(_tokenize_for_bm25(query_text))

    if max(raw_scores, default=0.0) == 0:
        return dense_ids

    ranked = sorted(zip(all_ids, raw_scores), key=lambda x: -x[1])
    bm25_ids = [did for did, _ in ranked[:top_k]]

    # RRF 병합 → top-k (BM25-only 항목도 포함)
    return _rrf_merge(dense_ids, bm25_ids)[:top_k]


# ── 지표 계산 ──────────────────────────────────────────────────────────────────


def _hit_and_mrr(
    retrieved_ids: list[str],
    gold_ids: set[str],
) -> tuple[bool, float]:
    """gold chunk가 retrieved 목록에 처음 등장하는 위치로 hit, MRR 역수 반환."""
    for rank, doc_id in enumerate(retrieved_ids, start=1):
        if doc_id in gold_ids:
            return True, 1.0 / rank
    return False, 0.0


# ── 평가 메인 ──────────────────────────────────────────────────────────────────


def evaluate(
    top_k_list: list[int] | None = None,
    eval_path: Path = EVAL_DATASET_PATH,
    collection: Any | None = None,
) -> dict[str, Any]:
    """Dense vs Hybrid Hit@k / MRR 전체 평가를 실행한다."""
    if top_k_list is None:
        top_k_list = [3, 5]

    cases = _load_eval_cases(eval_path)
    target_collection = collection or get_industry_collection()
    max_top_k = max(top_k_list)

    case_results: list[dict[str, Any]] = []

    for case in cases:
        case_id: str = case["case_id"]
        user_input: str = case["user_input"]
        reference: str = case["reference"]

        where = _build_where_filter(
            industry_name=case.get("industry_name"),
            ksic_code=case.get("ksic_code"),
            sub_sector=case.get("sub_sector"),
        )

        # Gold chunk 식별 (reference 기반 dense 검색)
        gold_ids = _find_gold_chunk_ids(reference, target_collection, where)
        if not gold_ids:
            logger.warning("case=%s gold chunk 없음 — 스킵", case_id)
            continue

        # 검색 실행
        dense_ids = _dense_retrieve_ids(user_input, where, max_top_k, target_collection)
        hybrid_ids = _hybrid_retrieve_ids(user_input, where, max_top_k, target_collection)

        logger.info(
            "case=%s gold=%s dense_top5=%s hybrid_top5=%s",
            case_id,
            list(gold_ids)[:2],
            dense_ids[:3],
            hybrid_ids[:3],
        )

        case_row: dict[str, Any] = {
            "case_id": case_id,
            "gold_chunk_count": len(gold_ids),
            "dense": {},
            "hybrid": {},
        }

        for k in top_k_list:
            d_hit, d_mrr = _hit_and_mrr(dense_ids[:k], gold_ids)
            h_hit, h_mrr = _hit_and_mrr(hybrid_ids[:k], gold_ids)
            case_row["dense"][f"hit@{k}"] = d_hit
            case_row["dense"][f"mrr@{k}"] = round(d_mrr, 4)
            case_row["hybrid"][f"hit@{k}"] = h_hit
            case_row["hybrid"][f"mrr@{k}"] = round(h_mrr, 4)

        case_results.append(case_row)

    n = len(case_results)
    summary: dict[str, Any] = {"dense": {}, "hybrid": {}}
    for k in top_k_list:
        for method in ("dense", "hybrid"):
            hits = [r[method][f"hit@{k}"] for r in case_results]
            mrrs = [r[method][f"mrr@{k}"] for r in case_results]
            summary[method][f"hit@{k}"] = round(sum(hits) / n, 4) if n else 0.0
            summary[method][f"mrr@{k}"] = round(sum(mrrs) / n, 4) if n else 0.0

    return {
        "evaluated_at": datetime.now(UTC).isoformat(),
        "num_cases": n,
        "top_k_list": top_k_list,
        "gold_top_n": GOLD_TOP_N,
        "gold_max_distance": GOLD_MAX_DISTANCE,
        "summary": summary,
        "cases": case_results,
    }


# ── 출력 ───────────────────────────────────────────────────────────────────────


def print_comparison_table(result: dict[str, Any]) -> None:
    """Dense vs Hybrid 비교표를 stdout에 출력한다."""
    summary = result["summary"]
    top_k_list: list[int] = result["top_k_list"]
    n = result["num_cases"]

    print()
    print("=" * 57)
    print(f"  RAG 검색 품질 평가  (케이스 {n}개, Gold top-{result['gold_top_n']})")
    print("=" * 57)
    print(f"  {'지표':<14} {'Dense':>10} {'Hybrid':>10} {'개선':>10}")
    print("-" * 57)

    for k in top_k_list:
        for metric_prefix, label_prefix in (("hit", "Hit"), ("mrr", "MRR")):
            key = f"{metric_prefix}@{k}"
            d = summary["dense"][key]
            h = summary["hybrid"][key]
            delta = h - d
            sign = "+" if delta >= 0 else ""
            label = f"{label_prefix}@{k}"
            print(f"  {label:<14} {d:>10.4f} {h:>10.4f} {sign}{delta:>+9.4f}")

    print("=" * 57)
    print()


# ── 진입점 ─────────────────────────────────────────────────────────────────────


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    print("평가 실행 중... (KoSRoberta 임베딩 로딩 포함, 약 1~2분 소요)")
    result = evaluate(top_k_list=[3, 5])

    ARTIFACTS_DIR.mkdir(exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    out_path = ARTIFACTS_DIR / f"retrieval_metrics_{ts}.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"결과 저장: {out_path}")
    print_comparison_table(result)


if __name__ == "__main__":
    main()
