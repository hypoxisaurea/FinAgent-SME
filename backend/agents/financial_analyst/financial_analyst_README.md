# Financial Analyst Agent

## 역할

DART 공시 재무제표를 기반으로 기업의 정량적 재무 리스크를 분석하는 에이전트입니다.
산업 비교나 뉴스 해석은 담당하지 않으며, 재무 수치 계산과 이상 징후 탐지, 신용등급 상한 결정에 집중합니다.

---

## 데이터 소스

| 소스 | 라이브러리 | 용도 |
|---|---|---|
| DART Open API | `OpenDartReader` | 재무제표 수집 (`finstate_all`), 회사 정보 조회 |

### 환경변수

```
DART_API_KEY=...   # opendart.fss.or.kr 에서 무료 발급
```

---

## 파일 구조

```
financial_analyst/
    __init__.py          # financial_agent 객체 export
    financial_agent.py   # LangGraph ReAct 에이전트 생성
    financial_prompts.py # 에이전트 페르소나 및 출력 스키마 정의
    financial_tools.py   # 도구 함수 5개
```

---

## 에이전트 설정

| 항목 | 값 |
|---|---|
| 모델 | `gpt-4.1-nano` |
| 프레임워크 | LangGraph `create_react_agent` |
| 에이전트 이름 | `financial_analyst` |
| 도구 수 | 5개 |

---

## 도구 설명

### 1. `get_financial_statements(corp_code, year)`

DART API에서 재무제표를 가져와 표준 계정과목 dict로 반환합니다.

- **입력**: `corp_code` (8자리 DART 고유번호), `year` (분석 연도)
- **출력**: 표준 계정과목 dict (총 21개 항목)
- **특이사항**:
  - 사업보고서(`reprt_code=11011`) 기준, 연결재무제표(CFS) 우선
  - 손익계산서(IS) 없으면 포괄손익계산서(CIS)로 대체
  - 계정과목명 변동에 대응: `account_id` (IFRS 표준 코드) 우선 매칭, 미존재 시 공백 제거 후 텍스트 매칭
  - 매출액·매출원가·이자비용 등은 다중 명칭(`영업수익` or `수익(매출액)` or `매출액`) 순차 매칭
  - 유형자산취득은 CF에 음수로 기록되므로 `abs()` 처리 후 저장 (FCF 계산용)

**수집 계정과목**

| 카테고리 | 항목 |
|---|---|
| 재무상태표 | 유동자산, 유동부채, 자산총계, 자본총계, 부채총계, 이익잉여금 |
| 활동성 지표용 | 재고자산, 매출채권, 매입채무 |
| 차입금 구성 | 단기차입금, 유동성장기차입금, 장기차입금, 사채 |
| 유형자산 | 유형자산 |
| 손익계산서 | 매출액, 매출원가, 영업이익, 당기순이익, 이자비용 |
| 현금흐름표 | 영업현금흐름, 유형자산취득 |

---

### 2. `calc_financial_ratios(fs)`

재무제표 dict에서 안정성·활동성·수익성·현금흐름 4개 영역의 비율을 계산합니다.

- **입력**: `get_financial_statements` 결과 dict
- **출력**: 15개 재무비율

| 영역 | 지표 | 계산식 |
|---|---|---|
| 안정성 | 부채비율 (debt_ratio) | 부채총계 / 자본총계 |
| 안정성 | 유동비율 (current_ratio) | 유동자산 / 유동부채 |
| 안정성 | 당좌비율 (quick_ratio) | (유동자산 - 재고자산) / 유동부채 |
| 안정성 | 차입금의존도 (borrow_dep) | (단기 + 유동성장기 + 장기차입금 + 사채) / 총자산 |
| 안정성 | 이자보상배율 (interest_coverage) | 영업이익 / 이자비용 (이자비용=0 시 null) |
| 활동성 | 매출채권회전율 (receivable_turnover) | 매출액 / 매출채권 |
| 활동성 | 총자산회전율 (asset_turnover) | 매출액 / 총자산 |
| 활동성 | 매입채무회전율 (payable_turnover) | 매출원가 / 매입채무 |
| 수익성 | ROA | 당기순이익 / 총자산 |
| 수익성 | 영업이익률 (op_margin) | 영업이익 / 매출액 |
| 수익성 | 매출원가율 (cogs_ratio) | 매출원가 / 매출액 |
| 현금흐름 | OCF/매출액 (ocf_to_sales) | 영업현금흐름 / 매출액 |
| 현금흐름 | OCF/당기순이익 (ocf_to_net_income) | 영업현금흐름 / 당기순이익 (당기순이익=0 시 null) |
| 현금흐름 | FCF (잉여현금흐름) | 영업현금흐름 - 유형자산취득 |
| 현금흐름 | FCF/매출액 (fcf_to_sales) | FCF / 매출액 |

---

### 3. `calc_altman_z_prime(fs)`

비상장 중소기업용 Altman Z'-Score (1983) 부도예측 점수를 계산합니다.

- **입력**: `get_financial_statements` 결과 dict
- **출력**: Z' 점수, 위험 구간, 5개 구성요소

**공식**
```
Z' = 0.717·X1 + 0.847·X2 + 3.107·X3 + 0.420·X4 + 0.998·X5
  X1 = 운전자본 / 총자산
  X2 = 이익잉여금 / 총자산
  X3 = 영업이익 / 총자산
  X4 = 자본총계(장부가) / 부채총계   ← 비상장용 (시가총액 대신 장부가)
  X5 = 매출액 / 총자산
```

**판정 기준**

| 구간 | 판정 |
|---|---|
| Z' > 2.9 | Safe (안전) |
| 1.23 ≤ Z' ≤ 2.9 | Grey (주의) |
| Z' < 1.23 | Distress (위험) |

---

### 4. `trend_analysis(corp_code, years)`

복수 연도 재무지표의 추세 분석과 급변 항목 탐지를 수행합니다.

- **입력**: `corp_code`, `years` (분석 연도 리스트, 권장 3개년)
- **출력**: 이상 플래그 목록, YoY 변화량, 연도별 히스토리, 성장성 지표(growth_ratios)

**연도별 history 항목**

연도, 부채비율, 영업이익률, ICR(이자보상배율), 매출액, 당기순이익, 총자산, 영업현금흐름

**YoY 추적 항목**

부채비율 변화량, 영업이익률 변화량, 매출액 성장률, 자산증가율

**YoY 플래그 (전년 대비)**

| 조건 | 플래그 |
|---|---|
| 부채비율 +20%p 이상 급증 | `{year}_debt_ratio_spike_+XX%` |
| 영업이익률 -5%p 이상 급락 | `{year}_op_margin_drop_-XX%` |
| 매출액 -10% 이상 급감 | `{year}_revenue_drop_-XX%` |
| 영업현금흐름 음수 전환 | `{year}_negative_operating_cashflow` |

**데이터 누락 플래그**

| 조건 | 플래그 |
|---|---|
| 해당 연도 DART 재무제표 없음 | `{year}_data_missing` |

**절댓값 플래그 (최신 연도)**

| 조건 | 플래그 |
|---|---|
| ICR < 1.0 | `{year}_icr_danger_X.XX` |
| 1.0 ≤ ICR < 1.5 | `{year}_icr_caution_X.XX` |
| 부채비율 ≥ 300% | `{year}_debt_ratio_danger_XXX%` |
| 200% ≤ 부채비율 < 300% | `{year}_debt_ratio_caution_XXX%` |

**growth_ratios 항목**

| 항목 | 설명 | null 조건 |
|---|---|---|
| revenue_growth | 매출액증가율 (최신 YoY) | 연도 1개뿐일 때 |
| asset_growth | 총자산증가율 (최신 YoY) | 연도 1개뿐일 때 |
| net_income_growth | 순이익증가율 | 직전연도 순이익=0이거나 연도 1개뿐일 때 |
| tangible_asset_growth | 유형자산증가율 | 현재 미구현 (항상 null) |

---

### 5. `apply_risk_filters(fs, history)`

재무 데이터 기반 신용등급 상한(`grade_cap`)을 결정합니다.

- **입력**: `fs` (`get_financial_statements` 결과), `history` (`trend_analysis` 결과의 history)
- **출력**: 등급 상한, 발동된 필터 목록, 필터별 판단 근거

**필터 우선순위**

| 우선순위 | 조건 | grade_cap | 적용대상 |
|---|---|---|---|
| 1 | 자기자본 ≤ 0 (전액잠식) | CCC | 전체 (3년 연속 당기순이익 흑자 시 면제) |
| 2 | 자기자본비율 ≤ 10% | CCC | 영세·개인사업자 제외 |
| 3 | 감사의견 부적정 또는 거절 | CCC | 외감기업 전용 |
| 4 | 당기순손실 2개년 연속 | B | 전체 |
| 5 | 0 < 매출액 < 3억 | B+ | 전체 |
| 6 | 3억 ≤ 매출액 < 20억 | BB+ | 전체 |

> 복수 필터 발동 시 가장 강한 제약(낮은 등급) 적용. `grade_cap`은 절대 상한이며 실제 최종 등급은 XAI/Decision Agent에서 산출됩니다.

---

## 출력 스키마

```json
{
  "ratios": {
    "debt_ratio": float,
    "current_ratio": float,
    "quick_ratio": float,
    "borrow_dep": float,
    "interest_coverage": "float | null",
    "receivable_turnover": float,
    "asset_turnover": float,
    "payable_turnover": float,
    "roa": float,
    "op_margin": float,
    "cogs_ratio": float,
    "ocf_to_sales": float,
    "ocf_to_net_income": "float | null",
    "fcf": float,
    "fcf_to_sales": float
  },
  "altman_z": {
    "z_prime": float,
    "zone": "Safe | Grey | Distress",
    "components": {"X1": float, "X2": float, "X3": float, "X4": float, "X5": float}
  },
  "trend_analysis": {
    "flags": ["string"],
    "yoy": {
      "debt_ratio": [float],
      "op_margin": [float],
      "revenue_growth": [float],
      "asset_growth": [float]
    },
    "history": [
      {
        "year": int,
        "debt_ratio": float,
        "op_margin": float,
        "icr": "float | null",
        "revenue": float,
        "net_income": float,
        "total_assets": float,
        "ocf": float
      }
    ]
  },
  "growth_ratios": {
    "revenue_growth": "float | null",
    "asset_growth": "float | null",
    "net_income_growth": "float | null",
    "tangible_asset_growth": "float | null"
  },
  "risk_filter": {
    "grade_cap": "CCC | B | B+ | BB+ | null",
    "triggered_filters": ["string"],
    "filter_detail": {}
  },
  "summary_kor": "string"
}
```

**summary_kor 구조**: `[안정성]` `[유동성]` `[수익성]` `[활동성]` `[현금흐름]` `[성장성·추세]` `[부도예측]` `[리스크 필터]` 8개 태그 단락

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
YEARS     = [2022, 2023, 2024]

from agents.financial_analyst.financial_tools import (
    get_financial_statements,
    calc_financial_ratios,
    calc_altman_z_prime,
    trend_analysis,
    apply_risk_filters,
)

def sep(title): print(f"\n{'='*50}\n{title}\n{'='*50}")

# 1. get_financial_statements
sep("1. get_financial_statements")
try:
    fs = get_financial_statements.invoke({"corp_code": CORP_CODE, "year": YEAR})
    print("✅ 성공")
    for k, v in fs.items():
        print(f"  {k}: {v:,.0f}" if isinstance(v, float) else f"  {k}: {v}")
except Exception as e:
    print(f"❌ 실패: {e}")
    fs = None

# 2. calc_financial_ratios
sep("2. calc_financial_ratios")
if fs:
    try:
        ratios = calc_financial_ratios.invoke({"fs": fs})
        print("✅ 성공")
        for k, v in ratios.items():
            print(f"  {k}: {round(v, 4) if v is not None else 'None'}")
    except Exception as e:
        print(f"❌ 실패: {e}")
        ratios = None
else:
    print("⏭️  fs 없음, 스킵")
    ratios = None

# 3. calc_altman_z_prime
sep("3. calc_altman_z_prime")
if fs:
    try:
        z = calc_altman_z_prime.invoke({"fs": fs})
        print("✅ 성공")
        print(f"  Z' = {z['z_prime']}  →  {z['zone']}")
        print(f"  구성요소: {z['components']}")
    except Exception as e:
        print(f"❌ 실패: {e}")
else:
    print("⏭️  스킵")

# 4. trend_analysis
sep("4. trend_analysis")
try:
    trend = trend_analysis.invoke({"corp_code": CORP_CODE, "years": YEARS})
    print("✅ 성공")
    print(f"  flags: {trend['flags']}")
    print(f"  yoy:   {trend['yoy']}")
    for h in trend['history']:
        print(f"  [{h['year']}] 부채비율={h['debt_ratio']:.2%}, 영업이익률={h['op_margin']:.2%}, ICR={h['icr']:.2f}")
except Exception as e:
    print(f"❌ 실패: {e}")
    trend = None

# 5. apply_risk_filters
sep("5. apply_risk_filters")
if fs and trend:
    try:
        rf = apply_risk_filters.invoke({"fs": fs, "history": trend["history"]})
        print("✅ 성공")
        print(f"  grade_cap:         {rf['grade_cap']}")
        print(f"  triggered_filters: {rf['triggered_filters']}")
        print(f"  filter_detail:     {rf['filter_detail']}")
    except Exception as e:
        print(f"❌ 실패: {e}")
else:
    print("⏭️  스킵")
```

### 테스트 결과 (메가스터디교육(주), corp_code: 01074862, 2024년)

```
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
```

---

## 에이전트 테스트

### 테스트 코드

```bash
cd /path/to/backend
python -c "
from dotenv import load_dotenv; load_dotenv()
from agents.financial_analyst.financial_agent import financial_agent
result = financial_agent.invoke({'messages': [{'role': 'user', 'content': 'corp_code 01074862, 2022·2023·2024년 재무 분석해줘'}]})
print(result['messages'][-1].content)
"
```

### 테스트 결과

```json
{
  "ratios": {
    "debt_ratio": 0.8818631328246092,
    "current_ratio": 0.5810307870502555,
    "quick_ratio": 0.4084175464034544,
    "borrow_dep": 0.015308070890740754,
    "interest_coverage": 22.596399963622837,
    "receivable_turnover": 18.587658367877054,
    "asset_turnover": 1.072758358642203,
    "payable_turnover": 5.476874097235595,
    "roa": 0.05710146601969159,
    "op_margin": 0.1312014768301981,
    "cogs_ratio": 0.4337541806260323,
    "ocf_to_sales": 0.18511492847059763,
    "ocf_to_net_income": 3.4777318459355326,
    "fcf": 158712211907.0,
    "fcf_to_sales": 0.1684397356283273
  },
  "altman_z": {
    "z_prime": 2.163,
    "zone": "Grey",
    "components": {
      "X1": -0.1765,
      "X2": 0.3609,
      "X3": 0.1407,
      "X4": 1.134,
      "X5": 1.0728
    }
  },
  "trend_analysis": {
    "flags": [],
    "yoy": {
      "debt_ratio": [-0.1419, -0.0622],
      "op_margin": [-0.0257, -0.0051],
      "revenue_growth": [0.1188, 0.0075],
      "asset_growth": [0.0561, -0.0807]
    },
    "history": [
      {
        "year": 2022,
        "debt_ratio": 1.086,
        "op_margin": 0.162,
        "icr": 26.9713,
        "revenue": 835952852633.0,
        "net_income": 99557434650.0,
        "total_assets": 904710791851.0,
        "ocf": 164964063308.0
      },
      {
        "year": 2023,
        "debt_ratio": 0.9441,
        "op_margin": 0.1363,
        "icr": 15.9423,
        "revenue": 935225125443.0,
        "net_income": 95793196332.0,
        "total_assets": 955494455263.0,
        "ocf": 168597864803.0
      },
      {
        "year": 2024,
        "debt_ratio": 0.8819,
        "op_margin": 0.1312,
        "icr": 22.5964,
        "revenue": 942249234214.0,
        "net_income": 50154643118.0,
        "total_assets": 878342477244.0,
        "ocf": 174424399593.0
      }
    ]
  },
  "risk_filter": {
    "grade_cap": null,
    "triggered_filters": [],
    "filter_detail": {}
  },
  "summary_kor": "[안정성] 메가스터디교육(주)의 2024년 부채비율은 88.19%로 금융당국 권고 이내는 아니나 200% 이하로 일반적으로 양호한 수준입니다. 3개년 추세에서는 2022년 108.6%에서 점차 개선 중임을 확인할 수 있습니다. 차입금의존도는 1.53%로 낮아 외부 차입 의존도가 적으며, 이자보상배율은 22.6배로 안정적인 수준입니다.\n\n[유동성] 유동비율은 58.10%로 통상적인 안전 권고치인 150%에 미치지 못하며, 당좌비율 역시 40.84%로 즉시 상환 능력에 다소 부족함을 시사합니다. 업종 특성 등의 보완 언급은 없으나, 단기 지급능력에는 주의가 필요합니다.\n\n[수익성] 영업이익률은 13.12%로 비교적 우수하며, ROA는 5.71%로 자산 대비 이익 창출력이 양호하여 대출 원금 상환 능력이 긍정적입니다. 매출원가율은 43.38%로 원가 부담이 적당한 수준입니다.\n\n[활동성] 총자산회전율은 1.07배로 자산 운용 효율이 준수하나, 매출채권회전율은 18.59회로 양호해 회수 지연 위험은 크지 않습니다.\n\n[현금흐름] 영업현금흐름 대비 매출액 비율은 18.51%로 상당히 높고, OCF/순이익은 3.48배로 회계이익보다 실제 현금이 많아 신뢰도가 높습니다. 자유현금흐름은 1,587억원으로 차입금 상환 및 투자 여력이 충분합니다.\n\n[성장성·추세] 매출액은 2022년 대비 2023년 11.88%, 2023년 대비 2024년 0.75% 증가하여 안정적 성장을 유지 중이며, 부채비율도 3개년에 걸쳐 개선 추세입니다. 주요 지표에서 급격한 변동이나 플래그는 발견되지 않았습니다.\n\n[부도예측] Altman Z' 점수는 2.163으로 주의 단계(Grey Zone)에 해당합니다. X1 운전자본/총자산(-0.1765)이 낮아 단기 유동성 압박의 위험이 있으나, 기타 구성요소는 양호합니다.\n\n[리스크 필터] 리스크 필터 발동 없음, grade_cap 제약 없습니다."
}
```

---

## 사용 방법

### 1. 직접 호출 (단독 실행)

```python
from dotenv import load_dotenv
load_dotenv()

from agents.financial_analyst.financial_agent import financial_agent

result = financial_agent.invoke({
    "messages": [
        {"role": "user", "content": "corp_code 01074862, 2022·2023·2024년 재무 분석해줘"}
    ]
})
print(result["messages"][-1].content)
```

### 2. 메시지 형식

```
"corp_code {8자리코드}, {연도1}·{연도2}·{연도3}년 재무 분석해줘"
```

- `corp_code`: DART 8자리 고유번호 (opendart.fss.or.kr 조회)
- `years`: 분석 연도 리스트 (권장 3개년, 추세 분석에 필요)
- 가장 최신 연도 기준으로 비율 계산 및 Altman Z' 산출
- `trend_analysis`는 전달된 전체 연도에 대해 YoY 분석 수행

### 3. Orchestrator 연동

```python
# Financial Agent 결과에서 ratios 추출 → Industry Agent로 전달
financial_result = json.loads(result["messages"][-1].content)
company_ratios = financial_result["ratios"]
sales_growth   = financial_result["trend_analysis"]["yoy"]["revenue_growth"][-1]
```

> **주의**: 에이전트가 반환하는 최종 메시지는 JSON 문자열입니다. `json.loads()`로 파싱 후 사용하세요.
