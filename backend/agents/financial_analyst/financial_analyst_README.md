# Financial Analyst Agent

## 역할

DART 공시 재무제표를 기반으로 기업의 정량적 재무 리스크를 분석하는 에이전트입니다.
산업 비교나 뉴스 해석은 담당하지 않으며, 재무 수치 계산과 이상 징후 탐지에 집중합니다.

---

## 데이터 소스

| 소스 | 라이브러리 | 용도 |
|---|---|---|
| DART Open API | `OpenDartReader` | 재무제표 수집 (`finstate_all`) |

### 환경변수 필요
```
DART_API_KEY=...   # opendart.fss.or.kr 에서 무료 발급
```

---

## 파일 구조

```
financial_analyst/
    __init__.py     # financial_agent 객체 export
    agent.py        # LangGraph ReAct 에이전트 생성
    prompts.py      # 에이전트 페르소나 및 출력 스키마 정의
    tools.py        # 도구 함수 4개
```

---

## 도구 설명

### 1. `get_financial_statements(corp_code, year)`
DART API에서 재무제표를 가져와 표준 계정과목 dict로 반환합니다.

- **입력**: `corp_code` (8자리 DART 고유번호), `year` (분석 연도)
- **출력**: 표준 계정과목 dict
- **특이사항**:
  - 개별재무제표(OFS) 우선, 없으면 연결재무제표(CFS) 사용
  - 손익계산서(IS) 없으면 포괄손익계산서(CIS)로 대체
  - 기업마다 계정과목명이 달라 다중 매칭 처리 (`영업수익` or `수익(매출액)` or `매출액`)

### 2. `calc_financial_ratios(fs)`
재무제표 dict에서 6종 재무비율과 현금흐름 비율을 계산합니다.

- **입력**: `get_financial_statements` 결과 dict
- **출력**:

| 지표 | 계산식 |
|---|---|
| 부채비율 | 부채총계 / 자본총계 |
| 유동비율 | 유동자산 / 유동부채 |
| ROA | 당기순이익 / 총자산 |
| 영업이익률 | 영업이익 / 매출액 |
| 이자보상배율 | 영업이익 / 이자비용 |
| 영업현금흐름/매출액 | 영업현금흐름 / 매출액 |
| 영업현금흐름/당기순이익 | 영업현금흐름 / 당기순이익 |

### 3. `calc_altman_z_prime(fs)`
비상장 중소기업용 Altman Z'-Score(1983)를 계산합니다.

- **입력**: `get_financial_statements` 결과 dict
- **출력**: Z' 점수, 위험 구간, 구성 요소

**공식**
```
Z' = 0.717·X1 + 0.847·X2 + 3.107·X3 + 0.420·X4 + 0.998·X5
  X1 = 운전자본 / 총자산
  X2 = 이익잉여금 / 총자산
  X3 = 영업이익 / 총자산
  X4 = 자본총계(장부가) / 부채총계  ← 비상장용 (시가총액 대신)
  X5 = 매출액 / 총자산
```

**판정 기준**
| 구간 | 판정 |
|---|---|
| Z' > 2.9 | Safe (안전) |
| 1.23 ≤ Z' ≤ 2.9 | Grey (주의) |
| Z' < 1.23 | Distress (위험) |

### 4. `trend_analysis(corp_code, years)`
최근 3개년 재무비율의 급변 항목을 탐지합니다.

- **입력**: `corp_code`, `years` (분석 연도 리스트, 예: [2021, 2022, 2023])
- **출력**: 이상 플래그 목록, YoY 변화량, 연도별 히스토리
- **탐지 기준**:
  - 부채비율 YoY +20%p 이상 급증
  - 영업이익률 YoY -5%p 이상 급락
  - 영업현금흐름 음수 전환

---

## 출력 스키마

```json
{
  "ratios": {
    "debt_ratio": 0.0,
    "current_ratio": 0.0,
    "roa": 0.0,
    "op_margin": 0.0,
    "interest_coverage": 0.0,
    "ocf_to_sales": 0.0,
    "ocf_to_net_income": 0.0
  },
  "altman_z": {"z_prime": 0.0, "zone": "Safe/Grey/Distress"},
  "trend_flags": ["이상 징후 플래그 목록"],
  "summary_kor": "재무비율, Altman Z'-Score, 추세 분석 결과를 종합한 한 단락 요약"
}
```

---

## 테스트 결과

### 테스트 기업: 메가스터디교육 (corp_code: 01074862, 2023년)

**1. 재무제표 수집**
```
{'유동자산': 235319047195.0, '유동부채': 406540183305.0, '총자산': 955494455263.0,
  '자본총계': 491472805323.0, '부채총계': 464021649940.0, '이익잉여금': 308227934215.0,
  '매출액': 935225125443.0, '영업이익': 127440527255.0, '당기순이익': 95793196332.0,
  '이자비용': 7993860480.0, '영업현금흐름': 168597864803.0}
```

**2. 재무비율 계산**
```
{'debt_ratio': 0.9441451183347593, 'current_ratio': 0.5788334262112924, 'roa': 0.10025510436440252,
  'op_margin': 0.13626721929079227, 'interest_coverage': 15.942300666098191, 'ocf_to_sales': 0.18027516607099078, 'ocf_to_net_income': 1.760019200305976}
```

**3. Altman Z'-Score**
```
{'z_prime': 1.981, 'zone': 'Grey',
 'components': {'X1': -0.1792, 'X2': 0.3226, 'X3': 0.1334, 'X4': 1.0592, 'X5': 0.9788}}
```

**4. 추세 분석 (2021~2023)**
```
{'flags': [],
 'yoy': {'debt_ratio': [0.0407, -0.1419], 'op_margin': [0.0213, -0.0257]},
 'history': [
   {'year': 2021, 'debt_ratio': 1.0453068794691638, 'op_margin': 0.1407, 'ocf': 192402654159.0},
   {'year': 2022, 'debt_ratio': 1.0860197404988365, 'op_margin': 0.162, 'ocf': 164964063308.0},
   {'year': 2023, 'debt_ratio': 0.9441451183347593, 'op_margin': 0.1363, 'ocf': 168597864803.0}
 ]}
```

**5. 에이전트 테스트 결과 (LLM 호출)**
```json
{
  "ratios": {
    "debt_ratio": 0.9441,
    "current_ratio": 0.5788,
    "roa": 0.1003,
    "op_margin": 0.1363,
    "interest_coverage": 15.94,
    "ocf_to_sales": 0.1803,
    "ocf_to_net_income": 1.7600
  },
  "altman_z": {
    "z_prime": 1.981,
    "zone": "Grey"
  },
  "trend_flags": [],
  "summary_kor": "해당 기업은 부채비율이 높고 유동비율은 낮으며, 재무비율상으로는 안정권에 가까우나 Altman Z'-Score는 1.98로 회색 지대에 속합니다. 최근 3년간 부채비율이 축소된 모습이 있으나, 전반적인 재무구조는 개선보다는 유지 또는 약간의 반전이 필요한 상태로 보입니다."
}
```

---

## 사용 방법

### 도구 단독 테스트
```python
from agents.financial_analyst.tools import (
    get_financial_statements,
    calc_financial_ratios,
    calc_altman_z_prime,
    trend_analysis
)
from dotenv import load_dotenv
load_dotenv()

fs = get_financial_statements.invoke({'corp_code': '01074862', 'year': 2023}) # 2025년도 가능
ratios = calc_financial_ratios.invoke({'fs': fs})
z = calc_altman_z_prime.invoke({'fs': fs})
trend = trend_analysis.invoke({'corp_code': '01074862', 'years': [2021, 2022, 2023]}) # 2023~2025년도 가능
```

### 에이전트 테스트 (OpenAI API 비용 발생)
```python
from agents.financial_analyst import financial_agent
from dotenv import load_dotenv
load_dotenv()

result = financial_agent.invoke({
    'messages': [{'role': 'user', 'content': 'corp_code 01074862, 2023년 재무 분석해줘'}] # 2025년도 가능
})
print(result['messages'][-1].content)
```
