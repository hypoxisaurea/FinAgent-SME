"""Hybrid vs Dense 성능 차이 원인 분석 스크립트.

실행:
    /opt/anaconda3/bin/python -m backend.rag.analysis_hybrid_debug
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from backend.rag.chroma_client import get_industry_collection
from backend.rag.retriever import (
    _build_bm25_index,
    _build_where_filter,
    _rrf_merge,
    _tokenize_for_bm25,
)

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

EVAL_PATH = Path(__file__).parent / "eval_datasets" / "industry_methodology.jsonl"


def _load_cases() -> list[dict]:
    cases = []
    with EVAL_PATH.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                cases.append(json.loads(line))
    return cases


# ─── 1. RRF 점수 계산 과정 상세 출력 ────────────────────────────────────────

TARGET_CASES_RRF = {"construction-01", "automobile-01", "steel-01", "shipbuilding-01"}


def analyze_rrf_scores(collection) -> None:
    print("\n" + "=" * 70)
    print("  [1] RRF 점수 계산 과정 — gold chunk rank 하락 원인")
    print("=" * 70)

    cases = _load_cases()
    for case in cases:
        cid = case["case_id"]
        if cid not in TARGET_CASES_RRF:
            continue

        query_text = case["user_input"]
        where = _build_where_filter(
            industry_name=case.get("industry_name"),
            ksic_code=case.get("ksic_code"),
            sub_sector=case.get("sub_sector"),
        )
        top_k = 5

        # Dense 검색
        dense_result = collection.query(
            query_texts=[query_text],
            n_results=top_k,
            where=where,
            include=["distances"],
        )
        dense_ids: list[str] = (dense_result.get("ids") or [[]])[0]
        (dense_result.get("distances") or [[]])[0]

        # BM25 검색
        all_result = collection.get(where=where, include=["documents"])
        all_docs: list[str] = all_result.get("documents", [])
        all_ids: list[str] = all_result.get("ids", [])

        bm25_index = _build_bm25_index(all_docs)
        raw_scores = bm25_index.get_scores(_tokenize_for_bm25(query_text))
        ranked_bm25 = sorted(zip(all_ids, raw_scores), key=lambda x: -x[1])
        bm25_ids = [did for did, _ in ranked_bm25[:top_k]]
        dict(ranked_bm25[:top_k])

        # Gold chunk (reference 기반 dense)
        ref_result = collection.query(
            query_texts=[case["reference"]],
            n_results=3,
            where=where,
            include=["distances"],
        )
        ref_ids = (ref_result.get("ids") or [[]])[0]
        ref_dists = (ref_result.get("distances") or [[]])[0]
        gold_ids = {did for did, d in zip(ref_ids, ref_dists) if d < 0.8}

        # RRF 계산 (k=60)
        k = 60
        rrf_scores: dict[str, dict] = {}
        for rank, did in enumerate(dense_ids, 1):
            rrf_scores.setdefault(did, {"dense_rank": None, "bm25_rank": None, "dense_rrf": 0.0, "bm25_rrf": 0.0})
            rrf_scores[did]["dense_rank"] = rank
            rrf_scores[did]["dense_rrf"] = 1.0 / (k + rank)
        for rank, did in enumerate(bm25_ids, 1):
            rrf_scores.setdefault(did, {"dense_rank": None, "bm25_rank": None, "dense_rrf": 0.0, "bm25_rrf": 0.0})
            rrf_scores[did]["bm25_rank"] = rank
            rrf_scores[did]["bm25_rrf"] = 1.0 / (k + rank)

        for did in rrf_scores:
            rrf_scores[did]["total"] = rrf_scores[did]["dense_rrf"] + rrf_scores[did]["bm25_rrf"]

        # 최종 순위
        merged_ids = _rrf_merge(dense_ids, bm25_ids)

        print(f"\n▶ {cid}  |  쿼리: {query_text[:35]}...")
        print(f"  Gold IDs: {[g[-8:] for g in gold_ids]}")
        print()
        print(f"  {'ID(말미8자)':<12} {'Dense순위':>10} {'BM25순위':>10} "
              f"{'Dense RRF':>11} {'BM25 RRF':>10} {'합계RRF':>10} {'HybridRank':>11} {'GOLD?':>6}")
        print("  " + "-" * 75)

        # RRF 상위 7개만 표시
        for h_rank, did in enumerate(merged_ids[:7], 1):
            info = rrf_scores.get(did, {})
            is_gold = "★ GOLD" if did in gold_ids else ""
            dr = info.get("dense_rank") or "-"
            br = info.get("bm25_rank") or "-"
            dr_rrf = f"{info.get('dense_rrf', 0):.5f}"
            br_rrf = f"{info.get('bm25_rrf', 0):.5f}"
            tot = f"{info.get('total', 0):.5f}"
            print(f"  {did[-12:]:<12} {str(dr):>10} {str(br):>10} "
                  f"{dr_rrf:>11} {br_rrf:>10} {tot:>10} {h_rank:>11} {is_gold:>6}")

        # 원인 분석
        print()
        gold_hybrid_rank = next(
            (i + 1 for i, did in enumerate(merged_ids) if did in gold_ids), None
        )
        gold_dense_rank = next(
            (i + 1 for i, did in enumerate(dense_ids) if did in gold_ids), None
        )
        intruder = merged_ids[0] if merged_ids[0] not in gold_ids else None
        if intruder and intruder in rrf_scores:
            info = rrf_scores[intruder]
            print(f"  → Gold: Dense rank {gold_dense_rank} → Hybrid rank {gold_hybrid_rank}")
            print(f"  → 순위 빼앗은 문서({intruder[-8:]}):")
            print(f"     Dense rank {info.get('dense_rank') or '-'} (RRF {info.get('dense_rrf',0):.5f})"
                  f" + BM25 rank {info.get('bm25_rank') or '-'} (RRF {info.get('bm25_rrf',0):.5f})"
                  f" = {info.get('total',0):.5f}")
            gold_id = next(iter(gold_ids))
            g_info = rrf_scores.get(gold_id, {})
            print(f"  → Gold 문서({gold_id[-8:]}):")
            print(f"     Dense rank {g_info.get('dense_rank') or '-'} (RRF {g_info.get('dense_rrf',0):.5f})"
                  f" + BM25 rank {g_info.get('bm25_rank') or '-'} (RRF {g_info.get('bm25_rrf',0):.5f})"
                  f" = {g_info.get('total',0):.5f}")
            gap = info.get("total", 0) - g_info.get("total", 0)
            print(f"  → 점수 차이: {gap:.5f}  (BM25가 non-gold 문서를 더 높게 평가)")


# ─── 2. BM25 토큰화 분석 (semiconductor-01) ─────────────────────────────────

def analyze_bm25_tokenization(collection) -> None:
    print("\n" + "=" * 70)
    print("  [2] BM25 토큰화 분석 — semiconductor-01")
    print("=" * 70)

    cases = _load_cases()
    case = next(c for c in cases if c["case_id"] == "semiconductor-01")

    query_text = case["user_input"]
    reference = case["reference"]
    where = _build_where_filter(
        industry_name=case.get("industry_name"),
        ksic_code=case.get("ksic_code"),
        sub_sector=case.get("sub_sector"),
    )

    print(f"\n  쿼리: {query_text}")
    print(f"  레퍼런스(gold 기준): {reference[:80]}...")

    q_tokens = _tokenize_for_bm25(query_text)
    r_tokens = _tokenize_for_bm25(reference)
    print(f"\n  [쿼리 토큰] ({len(q_tokens)}개): {q_tokens}")
    print(f"\n  [레퍼런스 토큰 일부] ({len(r_tokens)}개):")
    print(f"    {r_tokens}")

    # Gold chunk 찾기
    ref_result = collection.query(
        query_texts=[reference],
        n_results=3,
        where=where,
        include=["documents", "distances"],
    )
    ref_ids = (ref_result.get("ids") or [[]])[0]
    ref_dists = (ref_result.get("distances") or [[]])[0]
    (ref_result.get("documents") or [[]])[0]
    gold_ids = {did for did, d in zip(ref_ids, ref_dists) if d < 0.8}

    print(f"\n  Gold IDs: {list(gold_ids)}")

    # 전체 BM25 점수
    all_result = collection.get(where=where, include=["documents"])
    all_docs = all_result.get("documents", [])
    all_ids = all_result.get("ids", [])
    doc_map = dict(zip(all_ids, all_docs))

    bm25_index = _build_bm25_index(all_docs)
    raw_scores = bm25_index.get_scores(_tokenize_for_bm25(query_text))
    ranked = sorted(zip(all_ids, raw_scores), key=lambda x: -x[1])

    print(f"\n  BM25 상위 10개 (쿼리: '{query_text}'):")
    print(f"  {'순위':>4} {'BM25점수':>10} {'GOLD?':>6}  문서 미리보기(60자)")
    print("  " + "-" * 75)
    for rank, (did, score) in enumerate(ranked[:10], 1):
        is_gold = "★" if did in gold_ids else ""
        doc_preview = doc_map.get(did, "")[:60].replace("\n", " ")
        print(f"  {rank:>4} {score:>10.4f} {is_gold:>6}  {doc_preview}")

    print("\n  Gold chunks BM25 순위:")
    for gold_id in gold_ids:
        bm25_rank = next((i + 1 for i, (did, _) in enumerate(ranked) if did == gold_id), None)
        bm25_score = dict(ranked).get(gold_id, 0.0)
        gold_doc = doc_map.get(gold_id, "")[:100].replace("\n", " ")
        gold_tokens = _tokenize_for_bm25(gold_doc)
        overlap = set(q_tokens) & set(gold_tokens)
        print(f"    - {gold_id[-12:]}: BM25 rank {bm25_rank}, score {bm25_score:.4f}")
        print(f"      Gold 문서: {gold_doc[:80]}...")
        print(f"      Gold 토큰 일부: {gold_tokens[:15]}")
        print(f"      쿼리-gold 토큰 겹침: {overlap}")

    # Dense 결과 비교
    dense_result = collection.query(
        query_texts=[query_text],
        n_results=5,
        where=where,
        include=["distances"],
    )
    dense_ids = (dense_result.get("ids") or [[]])[0]
    dense_dists = (dense_result.get("distances") or [[]])[0]

    print("\n  Dense 결과 (거리↓ = 유사도↑):")
    for rank, (did, dist) in enumerate(zip(dense_ids, dense_dists), 1):
        is_gold = "★ GOLD" if did in gold_ids else ""
        print(f"    rank {rank}: {did[-12:]}  dist={dist:.4f}  {is_gold}")


# ─── 3. 수정 방향 시뮬레이션 ─────────────────────────────────────────────────

def _rrf_merge_weighted(
    dense_ids: list[str],
    bm25_ids: list[str],
    *,
    k: int = 60,
    dense_weight: float = 1.0,
    bm25_weight: float = 1.0,
) -> list[str]:
    """가중치 적용 RRF."""
    scores: dict[str, float] = {}
    for rank, did in enumerate(dense_ids, 1):
        scores[did] = scores.get(did, 0.0) + dense_weight / (k + rank)
    for rank, did in enumerate(bm25_ids, 1):
        scores[did] = scores.get(did, 0.0) + bm25_weight / (k + rank)
    return sorted(scores, key=lambda d: -scores[d])


def simulate_configs(collection) -> None:
    print("\n" + "=" * 70)
    print("  [3] 수정 방향 시뮬레이션 — 9개 케이스 전체 평가")
    print("=" * 70)

    configs = [
        {"name": "현재 (k=60, w=1:1)",    "k": 60,  "dw": 1.0, "bw": 1.0},
        {"name": "방안A: k=10 (Dense강화)", "k": 10,  "dw": 1.0, "bw": 1.0},
        {"name": "방안A: k=20",             "k": 20,  "dw": 1.0, "bw": 1.0},
        {"name": "방안B: k=60 w=2:1",      "k": 60,  "dw": 2.0, "bw": 1.0},
        {"name": "방안B: k=60 w=3:1",      "k": 60,  "dw": 3.0, "bw": 1.0},
        {"name": "방안B: k=60 w=5:1",      "k": 60,  "dw": 5.0, "bw": 1.0},
    ]

    cases = _load_cases()
    top_k_list = [3, 5]
    max_k = max(top_k_list)

    # 각 케이스 데이터 사전 수집
    case_data = []
    for case in cases:
        where = _build_where_filter(
            industry_name=case.get("industry_name"),
            ksic_code=case.get("ksic_code"),
            sub_sector=case.get("sub_sector"),
        )
        query_text = case["user_input"]

        ref_result = collection.query(
            query_texts=[case["reference"]],
            n_results=3,
            where=where,
            include=["distances"],
        )
        ref_ids = (ref_result.get("ids") or [[]])[0]
        ref_dists = (ref_result.get("distances") or [[]])[0]
        gold_ids = {did for did, d in zip(ref_ids, ref_dists) if d < 0.8}
        if not gold_ids:
            continue

        dense_result = collection.query(
            query_texts=[query_text],
            n_results=max_k,
            where=where,
            include=["metadatas"],
        )
        dense_ids = (dense_result.get("ids") or [[]])[0]

        all_result = collection.get(where=where, include=["documents"])
        all_docs = all_result.get("documents", [])
        all_ids = all_result.get("ids", [])

        bm25_index = _build_bm25_index(all_docs)
        raw_scores = bm25_index.get_scores(_tokenize_for_bm25(query_text))
        ranked_bm25 = sorted(zip(all_ids, raw_scores), key=lambda x: -x[1])
        bm25_ids = [did for did, _ in ranked_bm25[:max_k]]

        case_data.append({
            "case_id": case["case_id"],
            "gold_ids": gold_ids,
            "dense_ids": dense_ids,
            "bm25_ids": bm25_ids,
        })

    # 각 설정별 Hit@k/MRR 계산
    print(f"\n  {'설정':<28} {'Hit@3':>7} {'MRR@3':>7} {'Hit@5':>7} {'MRR@5':>7}")
    print("  " + "-" * 60)

    results_table = []
    for cfg in configs:
        hits3, mrrs3, hits5, mrrs5 = [], [], [], []
        for cd in case_data:
            hybrid_ids = _rrf_merge_weighted(
                cd["dense_ids"], cd["bm25_ids"],
                k=cfg["k"], dense_weight=cfg["dw"], bm25_weight=cfg["bw"]
            )
            for k_val, hits, mrrs in [(3, hits3, mrrs3), (5, hits5, mrrs5)]:
                top_ids = hybrid_ids[:k_val]
                hit = any(did in cd["gold_ids"] for did in top_ids)
                mrr_val = next(
                    (1.0 / (i + 1) for i, did in enumerate(top_ids) if did in cd["gold_ids"]),
                    0.0
                )
                hits.append(hit)
                mrrs.append(mrr_val)

        n = len(case_data)
        h3 = sum(hits3) / n
        m3 = sum(mrrs3) / n
        h5 = sum(hits5) / n
        m5 = sum(mrrs5) / n
        results_table.append((cfg["name"], h3, m3, h5, m5))
        print(f"  {cfg['name']:<28} {h3:>7.4f} {m3:>7.4f} {h5:>7.4f} {m5:>7.4f}")

    print()
    # Dense 단독 기준값 출력
    hits3, mrrs3, hits5, mrrs5 = [], [], [], []
    for cd in case_data:
        for k_val, hits, mrrs in [(3, hits3, mrrs3), (5, hits5, mrrs5)]:
            top_ids = cd["dense_ids"][:k_val]
            hit = any(did in cd["gold_ids"] for did in top_ids)
            mrr_val = next((1.0 / (i + 1) for i, did in enumerate(top_ids) if did in cd["gold_ids"]), 0.0)
            hits.append(hit)
            mrrs.append(mrr_val)
    n = len(case_data)
    print(f"  {'Dense 단독 (기준)':<28} {sum(hits3)/n:>7.4f} {sum(mrrs3)/n:>7.4f} {sum(hits5)/n:>7.4f} {sum(mrrs5)/n:>7.4f}")
    print()

    # 최고 설정 케이스별 상세
    best = max(results_table, key=lambda x: x[2] + x[4])  # MRR@3 + MRR@5 기준
    print(f"  최적 설정: {best[0]}  (MRR@3={best[2]:.4f}, MRR@5={best[4]:.4f})")


if __name__ == "__main__":
    print("컬렉션 로딩...")
    col = get_industry_collection()
    print("완료\n")

    analyze_rrf_scores(col)
    analyze_bm25_tokenization(col)
    simulate_configs(col)
