from __future__ import annotations

from typing import Any

from backend.rag.retriever import retrieve_industry_methodology


class _FakeCollection:
    def __init__(self, result: dict[str, Any] | None = None) -> None:
        self.result = result or {
            "documents": [["건설업은 수주잔고, 원가율, PF 우발채무가 주요 리스크입니다."]],
            "metadatas": [
                [
                    {
                        "filename": "2025 건설업 신용평가방법론.pdf",
                        "page": 7,
                        "industry_name": "건설업",
                        "ksic_code": "F 건설업",
                        "sub_sector": "건설",
                    }
                ]
            ],
            "distances": [[0.25]],
        }
        self.last_query: dict[str, Any] = {}

    def query(self, **kwargs: Any) -> dict[str, Any]:
        self.last_query = kwargs
        result = dict(self.result)
        if "ids" not in result:
            docs = self.result.get("documents", [[]])[0]
            result["ids"] = [[f"fake_id_{i}" for i in range(len(docs))]]
        return result

    def get(self, **_: Any) -> dict[str, Any]:
        """BM25 코퍼스 빌딩용 전체 문서 반환 (flat 형식)."""
        docs = list(self.result.get("documents", [[]])[0])
        return {
            "ids": [f"fake_id_{i}" for i in range(len(docs))],
            "documents": docs,
        }


class _FailingCollection:
    def query(self, **_: Any) -> dict[str, Any]:
        raise RuntimeError("vector store unavailable")


class _FallbackCollection:
    def __init__(self) -> None:
        self.last_get: dict[str, Any] = {}

    def query(self, **_: Any) -> dict[str, Any]:
        raise RuntimeError("query embedding unavailable")

    def get(self, **kwargs: Any) -> dict[str, Any]:
        self.last_get = kwargs
        return {
            "documents": [
                [
                    "건설업은 수주잔고와 PF 우발채무를 중심으로 평가한다.",
                ]
            ],
            "metadatas": [
                [
                    {
                        "filename": "2025 건설업 신용평가방법론.pdf",
                        "page": 9,
                        "industry_name": "건설업",
                        "ksic_code": "F 건설업",
                        "sub_sector": "건설",
                    }
                ]
            ],
        }


def test_retrieve_industry_methodology_returns_chunks_and_sources() -> None:
    collection = _FakeCollection()

    result = retrieve_industry_methodology(
        industry_name="건설업",
        top_k=3,
        collection=collection,
    )

    methodology = result["industry_methodology"]
    assert methodology["industry_name"] == "건설업"
    assert "수주잔고" in methodology["summary"]
    assert methodology["source_count"] == 1
    assert methodology["unavailable"] is False
    assert methodology["error"] is None
    assert result["methodology_sources"] == [
        {
            "filename": "2025 건설업 신용평가방법론.pdf",
            "page": 7,
            "score": 0.8,
            "industry_name": "건설업",
            "ksic_code": "F 건설업",
            "sub_sector": "건설",
        }
    ]


def test_retrieve_industry_methodology_can_include_retrieved_contexts() -> None:
    collection = _FakeCollection()

    result = retrieve_industry_methodology(
        industry_name="건설업",
        collection=collection,
        include_contexts=True,
    )

    assert result["retrieved_contexts"] == [
        "건설업은 수주잔고, 원가율, PF 우발채무가 주요 리스크입니다."
    ]


def test_retrieve_industry_methodology_cleans_summary_noise() -> None:
    collection = _FakeCollection(
        {
            "documents": [
                [
                    "건설업 박찬보 기업2실 선임연구원 연락처 02-1234-5678 email@test.com",
                    "본 보고서는 공시 목적이며 무단 배포를 금지합니다.",
                    (
                        "건설업 신용평가방법론상 주요 평가요소는 수주잔고, "
                        "사업포트폴리오, EBITDA마진, 부채비율, PF 우발채무 "
                        "리스크 등이다."
                    ),
                    (
                        "건설업 신용평가방법론상 주요 평가요소는 수주잔고, "
                        "사업포트폴리오, EBITDA마진, 부채비율, PF 우발채무 "
                        "리스크 등이다."
                    ),
                    "시장지위와 재무융통성은 사업위험 및 재무위험 판단에 활용된다.",
                ]
            ],
            "metadatas": [
                [
                    {
                        "filename": "2025 건설업 신용평가방법론.pdf",
                        "page": 4,
                        "industry_name": "건설업",
                        "ksic_code": "F 건설업",
                        "sub_sector": "건설",
                    }
                ]
            ],
            "distances": [[0.1]],
        }
    )

    result = retrieve_industry_methodology(industry_name="건설업", collection=collection)
    summary = result["industry_methodology"]["summary"]

    assert "수주잔고" in summary
    assert "PF 우발채무" in summary
    assert "시장지위" in summary
    assert "재무융통성" in summary
    assert "연구원" not in summary
    assert "연락처" not in summary
    assert "email@test.com" not in summary
    assert "공시" not in summary
    assert summary.count("주요 평가요소") == 1
    assert len(summary) <= 1200
    assert result["industry_methodology"]["source_count"] == 1
    assert result["methodology_sources"][0]["filename"] == "2025 건설업 신용평가방법론.pdf"


def test_retrieve_industry_methodology_limits_summary_to_1200_chars() -> None:
    noisy_prefix = "저자 기업평가본부 선임연구원 연락처 02-1111-2222. "
    long_risk_sentence = (
        "평가요소 사업위험 재무위험 수주잔고 PF 부채비율 EBITDA 차입금 "
        "시장지위 사업포트폴리오 재무융통성 리스크를 종합적으로 검토한다. "
    )
    collection = _FakeCollection(
        {
            "documents": [[noisy_prefix, long_risk_sentence * 40]],
            "metadatas": [
                [
                    {
                        "filename": "2025 건설업 신용평가방법론.pdf",
                        "page": 8,
                        "industry_name": "건설업",
                        "ksic_code": "F 건설업",
                        "sub_sector": "건설",
                    }
                ]
            ],
            "distances": [[0.2]],
        }
    )

    result = retrieve_industry_methodology(industry_name="건설업", collection=collection)
    summary = result["industry_methodology"]["summary"]

    assert len(summary) <= 1200
    assert "평가요소" in summary
    assert "저자" not in summary


def test_retrieve_industry_methodology_filters_by_industry_name() -> None:
    collection = _FakeCollection()

    retrieve_industry_methodology(industry_name="반도체업", collection=collection)

    assert collection.last_query["where"] == {"industry_name": "반도체업"}
    assert collection.last_query["n_results"] == 5


def test_retrieve_industry_methodology_falls_back_to_metadata_get() -> None:
    collection = _FallbackCollection()

    result = retrieve_industry_methodology(
        ksic_code="F 건설업",
        sub_sector="건설",
        collection=collection,
        include_contexts=True,
    )

    assert collection.last_get["where"] == {
        "$and": [{"ksic_code": "F 건설업"}, {"sub_sector": "건설"}]
    }
    assert result["industry_methodology"]["unavailable"] is False
    assert result["retrieved_contexts"] == [
        "건설업은 수주잔고와 PF 우발채무를 중심으로 평가한다."
    ]


def test_retrieve_industry_methodology_filters_by_ksic_code() -> None:
    collection = _FakeCollection()

    retrieve_industry_methodology(ksic_code="C 제조업", collection=collection)

    assert collection.last_query["where"] == {"ksic_code": "C 제조업"}
    assert "C 제조업" in collection.last_query["query_texts"][0]


def test_retrieve_industry_methodology_combines_filters() -> None:
    collection = _FakeCollection()

    retrieve_industry_methodology(
        ksic_code="C 제조업",
        sub_sector="조선",
        collection=collection,
    )

    assert collection.last_query["where"] == {
        "$and": [{"ksic_code": "C 제조업"}, {"sub_sector": "조선"}]
    }


def test_retrieve_industry_methodology_extracts_key_risk_factors() -> None:
    collection = _FakeCollection(
        result={
            "documents": [
                [
                    "건설업은 PF 우발채무 리스크가 핵심 위험 요인이며 수주잔고 감소 시 악화될 수 있다.",
                    "원자재 가격 변동과 환율 리스크로 인한 원가 부담이 커지고 있다.",
                    "단기.",
                ]
            ],
            "metadatas": [[{"filename": "2025 건설업 신용평가방법론.pdf", "page": 1,
                            "industry_name": "건설업", "ksic_code": "F 건설업", "sub_sector": "건설"}]],
            "distances": [[0.2]],
        }
    )

    result = retrieve_industry_methodology(industry_name="건설업", collection=collection)
    key_risks = result["industry_methodology"]["key_risk_factors"]

    assert len(key_risks) >= 1
    assert any("리스크" in s or "위험" in s or "악화" in s or "부담" in s for s in key_risks)
    assert all(20 <= len(s) <= 120 for s in key_risks)


def test_retrieve_industry_methodology_extracts_credit_assessment_factors() -> None:
    collection = _FakeCollection(
        result={
            "documents": [
                [
                    "주요 평가요소는 부채비율, EBITDA, 수주잔고, 시장지위이다.",
                    "차입금의존도와 수익성 지표가 신용평가의 핵심 항목이다.",
                    "단기.",
                ]
            ],
            "metadatas": [[{"filename": "2025 건설업 신용평가방법론.pdf", "page": 2,
                            "industry_name": "건설업", "ksic_code": "F 건설업", "sub_sector": "건설"}]],
            "distances": [[0.15]],
        }
    )

    result = retrieve_industry_methodology(industry_name="건설업", collection=collection)
    credit_factors = result["industry_methodology"]["credit_assessment_factors"]

    assert len(credit_factors) >= 1
    assert any(
        kw in s
        for s in credit_factors
        for kw in ("평가요소", "EBITDA", "부채비율", "차입금의존도", "수익성")
    )
    assert all(20 <= len(s) <= 120 for s in credit_factors)


def test_retrieve_industry_methodology_limits_factors_to_five() -> None:
    many_risk_sentences = [
        f"리스크 요인 {i}: 해당 업종의 주요 위험으로 경쟁이 심화되고 있다." for i in range(10)
    ]
    collection = _FakeCollection(
        result={
            "documents": [many_risk_sentences],
            "metadatas": [[{"filename": "2025 건설업 신용평가방법론.pdf", "page": 3,
                            "industry_name": "건설업", "ksic_code": "F 건설업", "sub_sector": "건설"}]],
            "distances": [[0.3]],
        }
    )

    result = retrieve_industry_methodology(industry_name="건설업", collection=collection)

    assert len(result["industry_methodology"]["key_risk_factors"]) <= 5


def test_retrieve_industry_methodology_factors_length_filter() -> None:
    collection = _FakeCollection(
        result={
            "documents": [
                [
                    "짧다.",
                    "이 문장은 정확히 20자 이상 120자 이하의 리스크 관련 문장입니다.",
                    "위험" * 65,
                ]
            ],
            "metadatas": [[{"filename": "2025 건설업 신용평가방법론.pdf", "page": 4,
                            "industry_name": "건설업", "ksic_code": "F 건설업", "sub_sector": "건설"}]],
            "distances": [[0.2]],
        }
    )

    result = retrieve_industry_methodology(industry_name="건설업", collection=collection)
    key_risks = result["industry_methodology"]["key_risk_factors"]

    assert all(20 <= len(s) <= 120 for s in key_risks)
    assert not any(len(s) < 20 or len(s) > 120 for s in key_risks)


def test_retrieve_industry_methodology_returns_unavailable_when_no_results() -> None:
    collection = _FakeCollection(
        result={
            "documents": [[]],
            "metadatas": [[]],
            "distances": [[]],
        }
    )

    result = retrieve_industry_methodology(industry_name="레미콘업", collection=collection)

    assert result["industry_methodology"]["unavailable"] is True
    assert result["industry_methodology"]["source_count"] == 0
    assert result["industry_methodology"]["error"] == "검색 결과 없음"
    assert result["methodology_sources"] == []


def test_retrieve_industry_methodology_returns_empty_contexts_when_unavailable() -> None:
    collection = _FakeCollection(
        {
            "documents": [[]],
            "metadatas": [[]],
            "distances": [[]],
        }
    )

    result = retrieve_industry_methodology(
        industry_name="레미콘업",
        collection=collection,
        include_contexts=True,
    )

    assert result["retrieved_contexts"] == []


def test_retrieve_industry_methodology_returns_unavailable_on_failure() -> None:
    result = retrieve_industry_methodology(
        industry_name="정유업",
        collection=_FailingCollection(),
    )

    assert result["industry_methodology"] == {
        "industry_name": "정유업",
        "summary": "",
        "key_risk_factors": [],
        "credit_assessment_factors": [],
        "source_count": 0,
        "unavailable": True,
        "error": "vector store unavailable",
    }
    assert result["methodology_sources"] == []


# ── Hybrid Search (BM25 + RRF) 테스트 ─────────────────────────────────────────


def test_tokenize_for_bm25_splits_on_whitespace_and_punctuation() -> None:
    from backend.rag.retriever import _tokenize_for_bm25  # noqa: PLC0415

    tokens = _tokenize_for_bm25("EBITDA마진, 부채비율.")
    assert "EBITDA마진" in tokens
    assert "부채비율" in tokens
    assert "" not in tokens


def test_rrf_merge_combines_rankings() -> None:
    from backend.rag.retriever import _rrf_merge  # noqa: PLC0415

    # "a": dense 1위 + bm25 2위, "c": dense 3위 + bm25 1위 → 둘 다 "b"보다 상위
    merged = _rrf_merge(["a", "b", "c"], ["c", "a", "d"])

    assert "a" in merged[:2]
    assert merged.index("c") < merged.index("b")
    assert "d" in merged


def test_rrf_merge_boosts_item_in_both_lists() -> None:
    from backend.rag.retriever import _rrf_merge  # noqa: PLC0415

    # "x": dense 1위 + bm25 1위 → 최상위 보장
    merged = _rrf_merge(["x", "y"], ["x", "z"])
    assert merged[0] == "x"


def test_retrieve_hybrid_surfaces_keyword_match() -> None:
    """BM25가 dense top-k 밖에 있던 EBITDA 키워드 문서를 요인 추출에 포함한다."""

    class _HybridFakeCollection:
        def query(self, **_: Any) -> dict[str, Any]:
            return {
                "documents": [["일반문서: 사업위험 분석.", "수주잔고 감소가 우려된다."]],
                "metadatas": [
                    [
                        {
                            "filename": "f.pdf",
                            "page": 1,
                            "industry_name": "건설업",
                            "ksic_code": "F 건설업",
                            "sub_sector": "건설",
                        },
                        {
                            "filename": "f.pdf",
                            "page": 2,
                            "industry_name": "건설업",
                            "ksic_code": "F 건설업",
                            "sub_sector": "건설",
                        },
                    ]
                ],
                "distances": [[0.3, 0.4]],
                "ids": [["dense_0", "dense_1"]],
            }

        def get(self, **_: Any) -> dict[str, Any]:
            return {
                "ids": ["dense_0", "dense_1", "bm25_only_0"],
                "documents": [
                    "일반문서: 사업위험 분석.",
                    "수주잔고 감소가 우려된다.",
                    "EBITDA 마진과 부채비율이 핵심 재무 평가요소입니다.",
                ],
            }

    result = retrieve_industry_methodology(
        query="EBITDA",
        industry_name="건설업",
        top_k=2,
        collection=_HybridFakeCollection(),
        use_hybrid=True,
    )

    all_factors = (
        result["industry_methodology"]["key_risk_factors"]
        + result["industry_methodology"]["credit_assessment_factors"]
    )
    assert any("EBITDA" in f for f in all_factors)


# ── use_hybrid=False 기본값 검증 ───────────────────────────────────────────────


def test_use_hybrid_false_skips_bm25_get_call() -> None:
    """use_hybrid=False(기본값)이면 collection.get()을 호출하지 않는다."""

    class _TrackingCollection:
        def __init__(self) -> None:
            self.get_called = False

        def query(self, **_: Any) -> dict[str, Any]:
            return {
                "documents": [["사업위험 분석 문서."]],
                "metadatas": [[{"filename": "f.pdf", "page": 1,
                                "industry_name": "건설업", "ksic_code": "F 건설업",
                                "sub_sector": "건설"}]],
                "distances": [[0.3]],
                "ids": [["dense_0"]],
            }

        def get(self, **_: Any) -> dict[str, Any]:
            self.get_called = True
            return {"ids": [], "documents": []}

    col = _TrackingCollection()
    retrieve_industry_methodology(
        query="건설업 평가요소",
        industry_name="건설업",
        collection=col,
        use_hybrid=False,
    )
    assert not col.get_called, "use_hybrid=False이면 get()을 호출하면 안 됨"


def test_use_hybrid_false_default_matches_dense_only_result() -> None:
    """use_hybrid 미지정(기본값 False)과 명시적 False가 동일한 결과를 반환한다."""
    collection = _FakeCollection()

    result_default = retrieve_industry_methodology(
        industry_name="건설업", collection=collection
    )
    result_explicit = retrieve_industry_methodology(
        industry_name="건설업", collection=collection, use_hybrid=False
    )

    assert result_default == result_explicit
