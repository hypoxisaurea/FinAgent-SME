from __future__ import annotations

import backend.tools.company_registry as company_registry


def test_fetch_statement_detail_dataframe_falls_back_to_ofs_and_maps_variants(
    monkeypatch,
) -> None:
    calls: list[str] = []

    def _fake_get_dart_json(
        endpoint: str,
        *,
        params: dict[str, str] | None = None,
        timeout: int = 10,
    ) -> dict[str, object]:
        assert endpoint == "fnlttSinglAcntAll.json"
        assert timeout == 20
        assert params is not None
        calls.append(params["fs_div"])
        if params["fs_div"] == "CFS":
            return {"status": "013", "message": "조회된 데이타가 없습니다."}
        return {
            "status": "000",
            "list": [
                {
                    "account_nm": "유동자산",
                    "thstrm_amount": "1,000",
                    "frmtrm_amount": "900",
                    "bfefrmtrm_amount": "800",
                },
                {
                    "account_nm": "유동부채",
                    "thstrm_amount": "400",
                    "frmtrm_amount": "350",
                    "bfefrmtrm_amount": "300",
                },
                {
                    "account_nm": "유동재고자산",
                    "thstrm_amount": "120",
                    "frmtrm_amount": "110",
                    "bfefrmtrm_amount": "100",
                },
                {
                    "account_nm": "매출채권 및 기타유동채권",
                    "thstrm_amount": "210",
                    "frmtrm_amount": "200",
                    "bfefrmtrm_amount": "190",
                },
                {
                    "account_nm": "매입채무 및 기타유동채무",
                    "thstrm_amount": "180",
                    "frmtrm_amount": "170",
                    "bfefrmtrm_amount": "160",
                },
                {
                    "account_nm": "유형자산",
                    "thstrm_amount": "700",
                    "frmtrm_amount": "650",
                    "bfefrmtrm_amount": "600",
                },
                {
                    "account_nm": "영업활동현금흐름",
                    "thstrm_amount": "90",
                    "frmtrm_amount": "80",
                    "bfefrmtrm_amount": "70",
                },
                {
                    "account_nm": "유형자산의 취득",
                    "thstrm_amount": "-55",
                    "frmtrm_amount": "-45",
                    "bfefrmtrm_amount": "-35",
                },
                {
                    "account_nm": "자산총계",
                    "thstrm_amount": "2,000",
                    "frmtrm_amount": "1,900",
                    "bfefrmtrm_amount": "1,800",
                },
                {
                    "account_nm": "부채총계",
                    "thstrm_amount": "1,200",
                    "frmtrm_amount": "1,100",
                    "bfefrmtrm_amount": "1,000",
                },
                {
                    "account_nm": "자본총계",
                    "thstrm_amount": "800",
                    "frmtrm_amount": "800",
                    "bfefrmtrm_amount": "800",
                },
                {
                    "account_nm": "이익잉여금",
                    "thstrm_amount": "300",
                    "frmtrm_amount": "250",
                    "bfefrmtrm_amount": "200",
                },
                {
                    "account_nm": "매출액",
                    "thstrm_amount": "3,000",
                    "frmtrm_amount": "2,800",
                    "bfefrmtrm_amount": "2,600",
                },
                {
                    "account_nm": "영업이익",
                    "thstrm_amount": "200",
                    "frmtrm_amount": "180",
                    "bfefrmtrm_amount": "160",
                },
                {
                    "account_nm": "당기순이익(손실)",
                    "thstrm_amount": "150",
                    "frmtrm_amount": "140",
                    "bfefrmtrm_amount": "130",
                },
            ],
        }

    monkeypatch.setattr(company_registry, "get_dart_json", _fake_get_dart_json)

    detail_df = company_registry.fetch_statement_detail_dataframe(
        corp_code="00123456",
        business_year=2024,
        report_code="11011",
    )
    records = company_registry.build_statement_detail_records(
        detail_df,
        corp_code="00123456",
        corp_name="테스트기업",
        stock_code="123456",
        business_year=2024,
        avg_revenue_last_3y=1000.0,
        audit_opinion="적정",
        is_external_audit=True,
    )

    assert calls == ["CFS", "OFS"]
    assert len(records) == 3
    current_year_record = records[0]
    assert current_year_record["year"] == 2024
    assert current_year_record["inventory"] == 120.0
    assert current_year_record["accounts_receivable"] == 210.0
    assert current_year_record["accounts_payable"] == 180.0
    assert current_year_record["tangible_assets"] == 700.0
    assert current_year_record["operating_cashflow"] == 90.0
    assert current_year_record["capital_expenditure"] == 55.0


def test_fetch_statement_detail_dataframe_prefers_cfs_when_available(
    monkeypatch,
) -> None:
    calls: list[str] = []

    def _fake_get_dart_json(
        endpoint: str,
        *,
        params: dict[str, str] | None = None,
        timeout: int = 10,
    ) -> dict[str, object]:
        assert endpoint == "fnlttSinglAcntAll.json"
        assert params is not None
        calls.append(params["fs_div"])
        return {
            "status": "000",
            "list": [
                {
                    "account_nm": "유동자산",
                    "thstrm_amount": "1,000",
                    "frmtrm_amount": "900",
                    "bfefrmtrm_amount": "800",
                }
            ],
        }

    monkeypatch.setattr(company_registry, "get_dart_json", _fake_get_dart_json)

    detail_df = company_registry.fetch_statement_detail_dataframe(
        corp_code="00123456",
        business_year=2024,
        report_code="11011",
    )

    assert calls == ["CFS"]
    assert not detail_df.empty


def test_build_account_subset_dataframe_tolerates_missing_prior_prior_amount() -> None:
    raw_df = company_registry.pd.DataFrame(
        [
            {
                "corp_code": "00123456",
                "stock_code": "123456",
                "fs_div": "OFS",
                "account_nm": "유동자산",
                "thstrm_amount": "1,000",
                "frmtrm_amount": "900",
            }
        ]
    )

    subset_df = company_registry.build_account_subset_dataframe(
        raw_df,
        ["유동자산"],
    )

    assert list(subset_df.columns) == [
        "corp_code",
        "stock_code",
        "fs_div",
        "account_nm",
        "thstrm_amount",
        "frmtrm_amount",
        "bfefrmtrm_amount",
    ]
    assert subset_df.iloc[0]["thstrm_amount"] == 1000
    assert subset_df.iloc[0]["frmtrm_amount"] == 900
    assert company_registry.pd.isna(subset_df.iloc[0]["bfefrmtrm_amount"])
