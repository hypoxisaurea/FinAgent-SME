============================================================
[A] 기존 도구 회귀 테스트 — DART API 호출 포함
============================================================

[A-1] get_financial_statements
reprt_code='11011', fs_div='CFS' (사업보고서, 연결제무제표)'
  ✅ PASS  반환값이 dict
  ✅ PASS  매출액 키 존재
  ✅ PASS  자본총계 키 존재
  ✅ PASS  audit_opinion 키 존재 (신규)
  ✅ PASS  is_external_audit 키 존재 (신규)
  ✅ PASS  is_external_audit 가 bool
     audit_opinion    = 적정의견
     is_external_audit= True

[A-2] calc_financial_ratios
  ✅ PASS  반환값이 dict
  ✅ PASS  debt_ratio 존재
  ✅ PASS  op_margin 존재
  ✅ PASS  15개 이상 비율 반환
     debt_ratio = 0.8819
     op_margin  = 0.1312

[A-3] calc_altman_z_prime
  ✅ PASS  반환값이 dict
  ✅ PASS  z_prime 존재
  ✅ PASS  zone 값이 유효
     Z' = 2.163  →  Grey

[A-4] trend_analysis — growth_ratios 섹션 포함
reprt_code='11011', fs_div='CFS' (사업보고서, 연결제무제표)'
reprt_code='11011', fs_div='CFS' (사업보고서, 연결제무제표)'
reprt_code='11011', fs_div='CFS' (사업보고서, 연결제무제표)'
  ✅ PASS  반환값이 dict
  ✅ PASS  flags 키 존재
  ✅ PASS  yoy 키 존재
  ✅ PASS  history 키 존재
  ✅ PASS  growth_ratios 키 존재 (신규)
  ✅ PASS    revenue_growth 존재
  ✅ PASS    asset_growth 존재
  ✅ PASS    net_income_growth 존재
  ✅ PASS    tangible_asset_growth 존재
     revenue_growth    = 0.0075
     asset_growth      = -0.0807
     net_income_growth = -0.4764

============================================================
[B] apply_risk_filters 보완 테스트 — mock 데이터
============================================================

[B-1 정상 기업 → 필터 없음]
  ✅ PASS  grade_cap = None  (기대: None)
  ✅ PASS  triggered 빈 리스트  (실제: [])

[B-2 완전자본잠식 + 3년 연속 흑자 → CCC 면제]
  ✅ PASS  grade_cap = None  (기대: None)
  ✅ PASS  triggered 빈 리스트  (실제: [])
  ✅ PASS  완전자본잠식_면제 detail 키 존재

[B-3 완전자본잠식 + 흑자 미충족 → CCC]
  ✅ PASS  grade_cap = 'CCC'  (기대: 'CCC')
  ✅ PASS  '완전자본잠식' triggered 에 포함

[B-4 자기자본비율 8% → CCC]
  ✅ PASS  grade_cap = 'CCC'  (기대: 'CCC')
  ✅ PASS  '자기자본비율_10%이하' triggered 에 포함

[B-5 감사의견 부적정 + 외감 → CCC]
  ✅ PASS  grade_cap = 'CCC'  (기대: 'CCC')
  ✅ PASS  '감사의견_부적정또는거절' triggered 에 포함

[B-6 감사의견 부적정 + 비외감 → 필터 미발동]
  ✅ PASS  grade_cap = None  (기대: None)
  ✅ PASS  triggered 빈 리스트  (실제: [])

[B-7 감사의견 거절 + 외감 → CCC]
  ✅ PASS  grade_cap = 'CCC'  (기대: 'CCC')
  ✅ PASS  '감사의견_부적정또는거절' triggered 에 포함

[B-8 당기순손실 2년 연속 → B]
  ✅ PASS  grade_cap = 'B'  (기대: 'B')
  ✅ PASS  '당기순손실_2년연속' triggered 에 포함

[B-9 매출 1억 → B+]
  ✅ PASS  grade_cap = 'B+'  (기대: 'B+')
  ✅ PASS  '매출액_3억미만' triggered 에 포함

[B-10 매출 15억 → BB+]
  ✅ PASS  grade_cap = 'BB+'  (기대: 'BB+')
  ✅ PASS  '매출액_20억미만' triggered 에 포함

[B-11 복수 필터 (감사의견CCC + 순손실B) → CCC 우선]
  ✅ PASS  grade_cap = 'CCC'  (기대: 'CCC')
  ✅ PASS  '감사의견_부적정또는거절' triggered 에 포함
  ✅ PASS  '당기순손실_2년연속' triggered 에 포함

============================================================
[C] get_financial_statements — audit 필드 실제 API 검증
============================================================

[C-1] 메가스터디교육(주) — 상장사이므로 is_external_audit=True 기대
  ✅ PASS  is_external_audit=True  (실제: True)
  ✅ PASS  audit_opinion 값 있음  (실제: '적정의견')

============================================================
[D] industry 도구 회귀 테스트 — DART/ECOS/KOSIS API 호출 포함
============================================================

[D-1] map_corp_to_ksic
  ✅ PASS  ksic_code 반환: P 교육 서비스업

     [참고] company_ratios.sales_growth = 0.0075  (growth_ratios 경로 확인)

[D-2] get_industry_avg_ratios
  ✅ PASS  반환값이 dict
  ✅ PASS  peer_comparison 존재
  ✅ PASS  company_ratios 전달 시 peer_comparison 활성화

[D-3] get_industry_outlook
  ✅ PASS  반환값이 dict
  ✅ PASS  outlook_score 유효: Medium

[D-4] get_business_cycle
  ✅ PASS  반환값이 dict
  ✅ PASS  경기 국면 키 존재: ['leading_latest', 'coincident_latest', 'leading_trend', 'coincident_trend', 'business_cycle_phase']

[D-5] get_macro_indicators
  ✅ PASS  반환값이 dict
  ✅ PASS  base_rate 존재: 2.5
  ✅ PASS  usd_krw 존재:   1484.8

============================================================
최종 결과
============================================================
  PASS: 59 / 59
  FAIL: 0 / 59

  🎉 모든 테스트 통과