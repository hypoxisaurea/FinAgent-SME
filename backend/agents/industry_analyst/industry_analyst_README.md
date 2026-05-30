# Industry Analyst Agent

## 역할

기업이 속한 산업의 동종업계 평균 재무비율, 업황 신호, 경기 국면, 거시환경을 분석하는 에이전트입니다.
개별 기업 재무비율 계산은 Financial Agent의 영역이며, 본 에이전트는 산업 맥락과 거시환경 분석에 집중합니다.

---

## 데이터 소스

| 소스 | 접근 방법 | 용도 |
|---|---|---|
| DART Open API | `OpenDartReader` | 기업 업종코드 조회 |
| 한국은행 ECOS Open API | REST API | 기준금리, 원달러환율, 선행·동행종합지수 |
| KOSIS Open API (통계청) | REST API | 광공업·서비스업·전산업 생산지수 |
| 한국은행 기업경영분석 CSV | 로컬 파일 (`data/`) | 산업별 중소기업 평균 재무비율 |
| 농림업생산지수 CSV | 로컬 파일 (`data/`) | A01 농업 업황 산출 |

### 환경변수

```
DART_API_KEY=...    # opendart.fss.or.kr 에서 무료 발급
ECOS_API_KEY=...    # ecos.bok.or.kr 에서 무료 발급
KOSIS_API_KEY=...   # kosis.kr 에서 무료 발급
```

---

## 파일 구조

```
industry_analyst/
    __init__.py          # industry_agent 객체 export
    industry_agent.py    # LangGraph ReAct 에이전트 생성
    industry_prompts.py  # 에이전트 페르소나 및 출력 스키마 정의
    industry_tools.py    # 도구 함수 5개
    data/
        profit_ratio.csv      # 한국은행 기업경영분석 5.1.2 손익 지표
        asset_ratio.csv       # 한국은행 기업경영분석 5.1.3 자산/자본 지표
        activity_ratio.csv    # 한국은행 기업경영분석 5.1.4 활동성(회전율) 지표
        growth_ratio.csv      # 한국은행 기업경영분석 5.1.1 성장성 지표
        agri_production.csv   # KOSIS 농림업생산지수 (A01 농업용)
```

---

## 에이전트 설정

| 항목 | 값 |
|---|---|
| 모델 | `gpt-4.1-mini` |
| 프레임워크 | LangGraph `create_react_agent` |
| 에이전트 이름 | `industry_analyst` |
| 도구 수 | 5개 |

---

## data/ 폴더 파일 설명

| 파일 | 출처 | 사용 지표 |
|---|---|---|
| `profit_ratio.csv` | ECOS 기업경영분석 5.1.2 | 매출액영업이익률, 이자보상비율 |
| `asset_ratio.csv` | ECOS 기업경영분석 5.1.3 | 부채비율, 유동비율, 차입금의존도 |
| `activity_ratio.csv` | ECOS 기업경영분석 5.1.4 | 매출채권회전율, 총자산회전율 |
| `growth_ratio.csv` | ECOS 기업경영분석 5.1.1 | 매출액증가율 |
| `agri_production.csv` | KOSIS 농림업생산지수 | 농업총계 행으로 A01 농업 업황 산출 |

> **CSV 다운로드 경로**:
> - 기업경영분석: ecos.bok.or.kr → 통계검색 → 기업경영분석 → 해당 분류 선택 → 기업규모 "중소기업" 선택 → CSV 다운로드
> - 농림업생산지수: kosis.kr → 통계검색 → 농림업생산지수 → CSV 다운로드

> **CSV 미커버 업종**: K(금융·보험), O(공공행정), Q(보건·사회복지) 등은 `map_corp_to_ksic`에서 `"N/A"` 반환되어 산업평균 비교가 비활성화됩니다.

---

## KSIC 매핑

DART `induty_code` 앞 2자리를 기준으로 KSIC 대분류에 매핑합니다.

| DART 코드 | KSIC 코드 |
|---|---|
| 01 | A01 농업 |
| 03 | A03 어업 |
| 05~08 | B 광업 |
| 10~34 | C 제조업 |
| 35 | D35 전기, 가스, 증기 및 공기조절 공급업 |
| 37~39 | E37-39 하수 · 폐기물 처리, 원료재생업 |
| 41~42 | F 건설업 |
| 45~47 | G 도매 및 소매업 |
| 49~52 | H 운수 및 창고업 |
| 55~56 | I 숙박 및 음식점업 |
| 58~63 | J 정보통신업 |
| 64~66 | (K 금융·보험 — 데이터 없음) |
| 68 | L 부동산업 |
| 71~73 | M 전문, 과학 및 기술 서비스업 |
| 74~76 | N 사업시설 관리 및 사업지원 및 임대 서비스업 |
| 85 | P 교육 서비스업 |
| 90~91 | R 예술, 스포츠 및 여가관련 서비스업 |
| 95 | S95 개인 및 소비용품 수리업 |
| 96 | S96 기타 개인 서비스업 |

---

## 도구 설명

### 1. `map_corp_to_ksic(corp_code)`

DART 회사개황에서 업종코드를 가져와 KSIC 코드로 변환합니다.

- **입력**: `corp_code` (8자리 DART 고유번호)
- **출력**: `{"corp_name": str, "ksic_code": str}` dict
- **특이사항**: 매핑 없는 업종이면 `ksic_code`가 `"N/A (업종코드 XXX - 산업평균 데이터 없음)"` 로 반환

---

### 2. `get_industry_avg_ratios(ksic_code, year, company_ratios=None)`

한국은행 기업경영분석 CSV에서 KSIC 업종 중소기업 평균 재무비율 8개를 조회하고, 선택적으로 기업 비율과의 비교(`peer_comparison`)를 함께 반환합니다.

- **입력**:
  - `ksic_code`, `year`
  - `company_ratios` (dict, optional): Financial Agent의 `calc_financial_ratios` 결과
- **출력**: 산업평균 8종 + `sector_note` + + `data_year` + (전달 시) `peer_comparison`
  
  **`data_year`**: 실제 데이터 기준 연도. 요청 연도(`year`)가 CSV에 없을 경우 그 이하 최대 연도로 폴백되며, 이때 `year ≠ data_year`가 됩니다.

**산업평균 지표**

영업이익률, 부채비율, 유동비율, 이자보상비율, 차입금의존도, 매출채권회전율, 총자산회전율, 매출액증가율

**peer_comparison 판정 로직**

- `_compare()` 내부 함수가 업종별 허용범위(`_SECTOR_THRESHOLDS`)를 적용하여 4단계 판정
- 부채비율·차입금의존도는 **역방향**(낮을수록 양호) 처리

| 판정 | 의미 |
|---|---|
| `better` | 산업평균보다 양호 |
| `in-line` | 허용범위 내 동등 |
| `worse` | 산업평균보다 열위 |
| `n/a` | 데이터 없음 |

**업종별 허용범위 (`_SECTOR_THRESHOLDS`)**

업종별로 정상 변동폭이 다르므로 ±10% 단일 기준 대신 업종별 차별 기준을 적용합니다.

| 업종 | 부채비율 허용폭 | 비고 |
|---|---|---|
| J 정보통신업 | ±10% | 자산 경량형, 부채 낮아야 정상 |
| L 부동산업 | ±35% | 레버리지 구조적으로 높음 |
| F 건설업 | ±30% | 200% 이상도 정상 범위 |
| G 도매·소매 | ±15% | 마진 낮고 회전 빠른 구조 |

> 전체 18개 KSIC 업종에 대해 8개 지표별 허용범위가 `industry_tools.py`에 정의되어 있습니다.

**`sector_note`**: 업종별 주의사항 텍스트 (예: "수강료 선수금이 유동부채 증가 요인 → 유동비율 낮아도 실질 위험 낮을 수 있음")

---

### 3. `get_industry_outlook(ksic_code)`

업종별로 적합한 생산지수 데이터 소스를 자동 선택하여 업황 등급(Low/Medium/High)을 산출합니다.

| 업종 | 데이터 소스 | 비고 |
|---|---|---|
| B 광업, C 제조업 | KOSIS 광공업생산지수 (DT_1F02011) | 생산·재고·출하 3지표 종합 판정 |
| E·G·H·I·J·L·M·N·P·R·S | KOSIS 서비스업생산지수 (DT_1KC2020) | 불변지수 기준, 업종명 키워드 필터 |
| F 건설업 | KOSIS 전산업생산지수 (DT_1KE10041) | 건설업 행 추출 |
| A01 농업 | 농림업생산지수 CSV | 농업총계 행 연간 YoY |
| A03 어업, D35 전기가스 | 데이터 없음 → Medium 중립 적용 | KOSIS API/CSV 모두 미커버 |

**광공업 등급 판정 (3지표 조합)**

| 조건 | 등급 |
|---|---|
| 생산 YoY ≤ -10% **AND** 재고 증가 | High |
| 생산 YoY ≤ -5% **OR** 재고 YoY > +5% | Medium |
| 그 외 | Low |

**서비스·건설·농업 등급 판정 (생산지수 YoY 단순 기준)**

| 조건 | 등급 |
|---|---|
| YoY ≥ +3% | Low (양호) |
| -3% ≤ YoY < +3% | Medium |
| YoY < -3% | High (부진) |

---

### 4. `get_business_cycle()`

한국은행 ECOS에서 선행·동행종합지수 순환변동치를 조회하여 현재 경기 국면을 판단합니다.

- **입력**: 없음
- **출력**: 선행/동행지수 최신값, 추세(rising/falling), 경기 국면

**경기 국면 판정**

| 선행 추세 | 동행 추세 | 국면 |
|---|---|---|
| ↑ | ↑ | 확장 |
| ↑ | ↓ | 회복 (바닥 탈출) |
| ↓ | ↑ | 둔화 (정점 근접) |
| ↓ | ↓ | 수축 |

> 조회 기간은 실행 시점 기준 동적으로 산출되며(최근 2년치), 최근 3개월 평균과 직전 3개월 평균을 비교해 추세를 판단합니다.

---

### 5. `get_macro_indicators(ksic_code="")`

한국은행 ECOS에서 기준금리와 원달러환율을 조회하고, 업종별 환율 영향을 해석합니다.

- **입력**: `ksic_code` (optional, 전달 시 환율 영향 해석 포함)
- **출력**: 기준금리, 원달러환율, 금리 추세 + (전달 시) 환율 민감도·영향 해석

**업종별 환율 민감도 (`_FX_SENSITIVITY`)**

| 분류 | 해당 업종 | 원화 약세 시 영향 |
|---|---|---|
| 수출형 | C 제조업, A03 어업, H 운수·창고 | 긍정적 (수출 경쟁력↑) |
| 수입의존형 | G 도매·소매, A01 농업 | 부정적 (수입 원가↑) |
| 원자재수입형 | D35 전기·가스 | 부정적 (원자재 비용↑) |
| 내수형 | F 건설, I 숙박·음식, L 부동산, P 교육, R 예술 등 | 중립 (간접 영향) |
| 중립형 | J 정보통신, M 전문·과학 | 중립 |

**환율 방향 판정**

| usd_krw | fx_direction |
|---|---|
| > 1350 | 원화 약세 |
| < 1200 | 원화 강세 |
| 1200~1350 | 원화 중립 |

---

## 출력 스키마

```json
{
  "corp_name": "string",
  "ksic_code": "string",
  "sector_note": "string",
  "industry_avg": {
    "op_margin": float,
    "debt_ratio": float,
    "current_ratio": float,
    "interest_coverage": float,
    "borrow_dep": float,
    "receivable_turnover": float,
    "asset_turnover": float,
    "sales_growth": float
  },
  "peer_comparison": {
    "<지표명>": {
      "company": "float | null",
      "avg": float,
      "judgment": "better | in-line | worse | n/a"
    }
  },
  "outlook_score": "Low | Medium | High",
  "outlook_source": "string",
  "outlook_detail": {
    "production_index_yoy": "float | null",
    "inventory_index_yoy": "float | null",
    "shipment_index_yoy": "float | null"
  },
  "business_cycle": {
    "phase": "확장 | 회복 | 둔화 | 수축",
    "leading_trend": "rising | falling",
    "coincident_trend": "rising | falling",
    "leading_latest": float,
    "coincident_latest": float
  },
  "macro_signals": {
    "base_rate": float,
    "usd_krw": float,
    "rate_trend": "rising | falling | stable",
    "fx_sensitivity": "string | null",
    "fx_direction": "string | null",
    "fx_impact": "string | null"
  },
  "summary_kor": "string"
}
```

**summary_kor 구조**: `[업종 소속]` `[동종업계 비교]` `[업황]` `[경기 국면]` `[거시환경]` 5개 태그 단락

> **참고**: `peer_comparison`은 Orchestrator가 Financial Agent의 비율을 `company_ratios` 인자로 전달해야 산출됩니다. 단독 실행 시 산업평균만 반환됩니다.

---

## 도구 테스트

### 테스트 코드

```python
# test_agents.py  (프로젝트 루트에서 실행)
# 실행: python test_agents.py

from dotenv import load_dotenv
load_dotenv()

CORP_CODE = "01074862"
YEAR      = 2024

from agents.financial_analyst.financial_tools import (
    calc_financial_ratios,
    get_financial_statements,
    trend_analysis,
)
from agents.industry_analyst.industry_tools import (
    map_corp_to_ksic,
    get_industry_avg_ratios,
    get_industry_outlook,
    get_business_cycle,
    get_macro_indicators,
)

def sep(title): print(f"\n{'='*50}\n{title}\n{'='*50}")

# 사전 준비: ratios/trend (peer_comparison 용)
fs     = get_financial_statements.invoke({"corp_code": CORP_CODE, "year": YEAR})
ratios = calc_financial_ratios.invoke({"fs": fs})
trend  = trend_analysis.invoke({"corp_code": CORP_CODE, "years": [2022, 2023, 2024]})
company_ratios = {
    "debt_ratio":          ratios.get("debt_ratio"),
    "current_ratio":       ratios.get("current_ratio"),
    "op_margin":           ratios.get("op_margin"),
    "interest_coverage":   ratios.get("interest_coverage"),
    "borrow_dep":          ratios.get("borrow_dep"),
    "receivable_turnover": ratios.get("receivable_turnover"),
    "asset_turnover":      ratios.get("asset_turnover"),
    "sales_growth":        trend["yoy"]["revenue_growth"][-1],
}

# 6. map_corp_to_ksic
sep("6. map_corp_to_ksic")
try:
    ksic = map_corp_to_ksic.invoke({"corp_code": CORP_CODE})
    print(f"✅ 성공: {ksic}")
except Exception as e:
    print(f"❌ 실패: {e}")
    ksic = None

# 7. get_industry_avg_ratios
sep("7. get_industry_avg_ratios")
if ksic:
    try:
        avg = get_industry_avg_ratios.invoke({
            "ksic_code": ksic, "year": YEAR, "company_ratios": company_ratios,
        })
        print("✅ 성공")
        for k, v in avg.items():
            if k != "peer_comparison":
                print(f"  {k}: {v}")
        if "peer_comparison" in avg:
            print("  peer_comparison:")
            for k, v in avg["peer_comparison"].items():
                print(f"    {k}: {v}")
    except Exception as e:
        print(f"❌ 실패: {e}")

# 8. get_industry_outlook
sep("8. get_industry_outlook")
if ksic:
    try:
        outlook = get_industry_outlook.invoke({"ksic_code": ksic})
        print("✅ 성공")
        for k, v in outlook.items():
            print(f"  {k}: {v}")
    except Exception as e:
        print(f"❌ 실패: {e}")

# 9. get_business_cycle
sep("9. get_business_cycle")
try:
    bc = get_business_cycle.invoke({})
    print("✅ 성공")
    for k, v in bc.items():
        print(f"  {k}: {v}")
except Exception as e:
    print(f"❌ 실패: {e}")

# 10. get_macro_indicators
sep("10. get_macro_indicators")
try:
    macro = get_macro_indicators.invoke({"ksic_code": ksic or ""})
    print("✅ 성공")
    for k, v in macro.items():
        print(f"  {k}: {v}")
except Exception as e:
    print(f"❌ 실패: {e}")
```

### 테스트 결과 (메가스터디교육(주), corp_code: 01074862, 2024년)

```
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
```

---

## 에이전트 테스트

### 테스트 코드

```bash
cd /path/to/backend
python -c "
from dotenv import load_dotenv; load_dotenv()
import json
from agents.financial_analyst.financial_tools import (
    get_financial_statements,
    calc_financial_ratios,
    trend_analysis,
)
from agents.industry_analyst.industry_agent import industry_agent

fs = get_financial_statements.invoke({'corp_code': '01074862', 'year': 2024})
ratios = calc_financial_ratios.invoke({'fs': fs})
trend = trend_analysis.invoke({'corp_code': '01074862', 'years': [2022, 2023, 2024]})

company_ratios = {
    'debt_ratio':          ratios['debt_ratio'],
    'current_ratio':       ratios['current_ratio'],
    'op_margin':           ratios['op_margin'],
    'interest_coverage':   ratios['interest_coverage'],
    'borrow_dep':          ratios['borrow_dep'],
    'receivable_turnover': ratios['receivable_turnover'],
    'asset_turnover':      ratios['asset_turnover'],
    'sales_growth':        trend['yoy']['revenue_growth'][-1],
}

result = industry_agent.invoke({'messages': [{'role': 'user', 'content': f'corp_code 01074862, 2024년 산업 분석해줘. company_ratios: {json.dumps(company_ratios, ensure_ascii=False)}'}]})
print(result['messages'][-1].content)
"
```

### 테스트 결과

```json
{
  "corp_name": "메가스터디교육(주)",
  "ksic_code": "P 교육 서비스업",
  "sector_note": "수강료 선수금이 유동부채 증가 요인 → 유동비율 낮아도 실질 위험 낮을 수 있음. 학령인구 감소 장기 구조적 리스크. 온라인 전환 가속화로 고정비(임대·강사) 구조 변화 중.",
  "industry_avg": {
    "op_margin": 0.038,
    "debt_ratio": 1.3743,
    "current_ratio": 1.117,
    "interest_coverage": 2.3025,
    "borrow_dep": 0.3841,
    "receivable_turnover": 34.07,
    "asset_turnover": 0.84,
    "sales_growth": 0.0866
  },
  "peer_comparison": {
    "debt_ratio": {"company": 0.8818631328246092, "avg": 1.3743, "judgment": "better"},
    "current_ratio": {"company": 0.5810307870502555, "avg": 1.117, "judgment": "worse"},
    "op_margin": {"company": 0.1312014768301981, "avg": 0.038, "judgment": "better"},
    "interest_coverage": {"company": 22.596399963622837, "avg": 2.3025, "judgment": "better"},
    "borrow_dep": {"company": 0.015308070890740754, "avg": 0.3841, "judgment": "better"},
    "receivable_turnover": {"company": 18.587658367877054, "avg": 34.07, "judgment": "worse"},
    "asset_turnover": {"company": 1.072758358642203, "avg": 0.84, "judgment": "better"},
    "sales_growth": {"company": 0.0075, "avg": 0.0866, "judgment": "worse"}
  },
  "outlook_score": "Medium",
  "outlook_source": "KOSIS 서비스업생산지수",
  "outlook_detail": {
    "production_index_yoy": -0.0049,
    "inventory_index_yoy": null,
    "shipment_index_yoy": null
  },
  "business_cycle": {
    "phase": "확장",
    "leading_trend": "rising",
    "coincident_trend": "rising",
    "leading_latest": 126.4,
    "coincident_latest": 116.2
  },
  "macro_signals": {
    "base_rate": 2.5,
    "usd_krw": 1482.9,
    "rate_trend": "stable",
    "fx_sensitivity": "내수형",
    "fx_direction": "원화 약세",
    "fx_impact": "중립 (직접 영향 낮음, 수입물가 간접 영향)"
  },
  "summary_kor": "[업종 소속]\n메가스터디교육(주)은 P 교육 서비스업에 속하는 기업으로, 수강료 선수금이 유동부채 증가 요인임에도 불구하고 유동비율이 낮은 것은 실질적인 위험으로 보기 어렵습니다. 다만, 학령인구 감소라는 장기적 구조적 리스크와 온라인 전환 가속화에 따른 고정비 구조 변화가 업종의 특성으로 작용하고 있습니다.\n\n[동종업계 비교]\n메가스터디교육(주)는 부채비율(88.19%로 산업 평균 137.43% 대비 낮음), 영업이익률(13.12%로 산업 평균 3.8% 대비 우수), 이자보상배율(22.6배로 산업 평균 2.3배 대비 탁월), 차입금의존도(1.53%로 산업 평균 38.41% 대비 매우 양호), 자산회전율(1.07회로 산업 평균 0.84회 대비 우수)에서 우수한 재무 방어력을 보입니다. 반면, 유동비율(58.10%로 산업 평균 111.7% 대비 저조)과 매출채권회전율(18.59회로 산업 평균 34.07회 대비 낮음), 매출액증가율(0.75%로 산업 평균 8.66% 대비 저조)에서는 열위에 있어 주의가 필요합니다. 특히, 매출액증가율이 산업 평균 대비 저조하여, 학령인구 감소 등 업종의 구조적 취약성과 맞물려 장기 성장 둔화 위험이 존재합니다.\n\n[업황]\nKOSIS 서비스업생산지수 출처에 따르면 메가스터디교육(주)의 업황은 생산지수가 전년 동기 대비 -0.49%로 미미한 감소세를 보여, 중립 등급의 정체 국면입니다. 재고와 출하 지수는 제공되지 않아 상세한 재고 수요 판단은 제한적입니다.\n\n[경기 국면]\n현재 선행종합지수는 126.4, 동행종합지수는 116.2로 둘 다 상승 추세이며, 이에 따라 경기 국면은 확장 국면입니다. 이는 전방 수요가 증가하는 상황으로, B2B 거래 시 상대적으로 리스크가 낮은 환경입니다.\n\n[거시환경]\n기준금리는 2.5%로 안정적이며, 환율은 원화 약세(1482.9원) 상황입니다. 메가스터디교육(주)의 업종은 내수형으로 환율 변동에 따른 직접적인 영향은 제한적이며, 수입 물가 상승을 통한 간접 영향이 존재하는 중립적인 환율 효과가 예상됩니다."
}
```

---

## 사용 방법

### 1. 직접 호출 (산업평균만, company_ratios 없음)

```python
from dotenv import load_dotenv
load_dotenv()

from agents.industry_analyst.industry_agent import industry_agent

result = industry_agent.invoke({
    "messages": [
        {"role": "user", "content": "corp_code 01074862, 2024년 산업 분석해줘"}
    ]
})
print(result["messages"][-1].content)
```

### 2. Orchestrator 연동 (권장, peer_comparison 포함)

```python
import json
from agents.financial_analyst.financial_tools import (
    get_financial_statements, calc_financial_ratios, trend_analysis,
)
from agents.industry_analyst.industry_agent import industry_agent

# Financial Agent 결과에서 company_ratios 구성
fs     = get_financial_statements.invoke({"corp_code": corp_code, "year": year})
ratios = calc_financial_ratios.invoke({"fs": fs})
trend  = trend_analysis.invoke({"corp_code": corp_code, "years": years})

company_ratios = {
    "debt_ratio":          ratios["debt_ratio"],
    "current_ratio":       ratios["current_ratio"],
    "op_margin":           ratios["op_margin"],
    "interest_coverage":   ratios["interest_coverage"],
    "borrow_dep":          ratios["borrow_dep"],
    "receivable_turnover": ratios["receivable_turnover"],
    "asset_turnover":      ratios["asset_turnover"],
    "sales_growth":        trend["yoy"]["revenue_growth"][-1],
}

result = industry_agent.invoke({
    "messages": [{
        "role": "user",
        "content": f"corp_code {corp_code}, {year}년 산업 분석해줘. company_ratios: {json.dumps(company_ratios, ensure_ascii=False)}"
    }]
})
industry_result = json.loads(result["messages"][-1].content.strip("```json\n").strip("```"))
```

### 3. 메시지 형식

```
"corp_code {8자리코드}, {연도}년 산업 분석해줘. company_ratios: {JSON 문자열}"
```

- `company_ratios`를 메시지에 포함하면 `peer_comparison`이 활성화됩니다.
- `company_ratios` 없이 호출하면 산업평균(`industry_avg`)만 반환됩니다.

> **주의**: 에이전트가 반환하는 최종 메시지는 ` ```json ``` ` 코드 블록으로 감싸진 JSON 문자열입니다. 파싱 시 코드 펜스를 제거 후 `json.loads()`를 사용하세요.
