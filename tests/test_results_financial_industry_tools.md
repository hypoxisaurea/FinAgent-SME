==================================================
1. get_financial_statements
==================================================
reprt_code='11011', fs_div='CFS' (사업보고서, 연결제무제표)'
✅ 성공
  유동자산: 214,990,218,391
  유동부채: 370,015,192,280
  총자산: 878,342,477,244
  자본총계: 466,740,892,004
  부채총계: 411,601,585,240
  이익잉여금: 316,969,120,678
  재고자산: 63,869,521,428
  매출채권: 50,692,196,702
  매입채무: 74,623,688,125
  단기차입금: 13,374,895,586
  유동성장기차입금: 24,999,996
  장기차입금: 45,833,326
  사채: 0
  유형자산: 283,983,246,188
  매출액: 942,249,234,214
  매출원가: 408,704,544,532
  영업이익: 123,624,491,071
  당기순이익: 50,154,643,118
  이자비용: 5,470,981,717
  영업현금흐름: 174,424,399,593
  유형자산취득: 15,712,187,686

==================================================
2. calc_financial_ratios
==================================================
✅ 성공
  debt_ratio: 0.8819
  current_ratio: 0.581
  quick_ratio: 0.4084
  borrow_dep: 0.0153
  interest_coverage: 22.5964
  receivable_turnover: 18.5877
  asset_turnover: 1.0728
  payable_turnover: 5.4769
  roa: 0.0571
  op_margin: 0.1312
  cogs_ratio: 0.4338
  ocf_to_sales: 0.1851
  ocf_to_net_income: 3.4777
  fcf: 158712211907.0
  fcf_to_sales: 0.1684

==================================================
3. calc_altman_z_prime
==================================================
✅ 성공
  Z' = 2.163  →  Grey
  구성요소: {'X1': -0.1765, 'X2': 0.3609, 'X3': 0.1407, 'X4': 1.134, 'X5': 1.0728}

==================================================
4. trend_analysis
==================================================
reprt_code='11011', fs_div='CFS' (사업보고서, 연결제무제표)'
reprt_code='11011', fs_div='CFS' (사업보고서, 연결제무제표)'
reprt_code='11011', fs_div='CFS' (사업보고서, 연결제무제표)'
✅ 성공
  flags: []
  yoy:   {'debt_ratio': [-0.1419, -0.0622], 'op_margin': [-0.0257, -0.0051], 'revenue_growth': [0.1188, 0.0075], 'asset_growth': [0.0561, -0.0807]}
  [2022] 부채비율=108.60%, 영업이익률=16.20%, ICR=26.97
  [2023] 부채비율=94.41%, 영업이익률=13.63%, ICR=15.94
  [2024] 부채비율=88.19%, 영업이익률=13.12%, ICR=22.60

==================================================
5. apply_risk_filters
==================================================
✅ 성공
  grade_cap:         None
  triggered_filters: []
  filter_detail:     {}

==================================================
6. map_corp_to_ksic
==================================================
✅ 성공: P 교육 서비스업

==================================================
7. get_industry_avg_ratios
==================================================
✅ 성공
  avg_op_margin: 0.038
  avg_debt_ratio: 1.3743
  avg_current_ratio: 1.117
  avg_interest_coverage: 2.3025
  avg_borrow_dep: 0.38409999999999994
  avg_receivable_turnover: 34.07
  avg_asset_turnover: 0.84
  avg_sales_growth: 0.0866
  ksic_code: P 교육 서비스업
  year: 2024
  sector_note: 수강료 선수금이 유동부채 증가 요인 → 유동비율 낮아도 실질 위험 낮을 수 있음. 학령인구 감소 장기 구조적 리스크. 온라인 전환 가속화로 고정비(임대·강사) 구조 변화 중.
  peer_comparison:
    debt_ratio: better
    current_ratio: worse
    op_margin: better
    interest_coverage: better
    borrow_dep: better
    receivable_turnover: worse
    asset_turnover: better
    sales_growth: worse

==================================================
8. get_industry_outlook
==================================================
✅ 성공
  production_index_yoy: -0.0049
  inventory_index_yoy: None
  shipment_index_yoy: None
  outlook_score: Medium
  source: KOSIS 서비스업생산지수

==================================================
9. get_business_cycle
==================================================
✅ 성공
  leading_latest: 126.4
  coincident_latest: 116.2
  leading_trend: rising
  coincident_trend: rising
  business_cycle_phase: 확장

==================================================
10. get_macro_indicators
==================================================
✅ 성공
  base_rate: 2.5
  usd_krw: 1480.6
  rate_trend: stable
  fx_sensitivity: 내수형
  fx_direction: 원화 약세
  fx_impact: 중립 (직접 영향 낮음, 수입물가 간접 영향)

==================================================
테스트 완료
==================================================