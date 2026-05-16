# Industry Analyst Agent

## 역할

기업이 속한 산업의 동종업계 평균 재무비율과 업황 신호를 분석하는 에이전트입니다.
개별 기업 재무비율 계산은 Financial Agent 영역이며, 산업 수준의 맥락과 거시환경 분석에 집중합니다.

---

## 데이터 소스

| 소스 | 접근 방법 | 용도 |
|---|---|---|
| DART Open API | `OpenDartReader` | 기업 업종코드 조회 |
| 한국은행 ECOS Open API | REST API | 기준금리, 원달러환율 |
| KOSIS Open API (통계청) | REST API | 광공업생산·재고·출하지수 |
| 한국은행 기업경영분석 CSV | 로컬 파일 | 산업별 중소기업 평균 재무비율 |

### 환경변수 필요
```
DART_API_KEY=...    # opendart.fss.or.kr 에서 무료 발급
ECOS_API_KEY=...    # ecos.bok.or.kr 에서 무료 발급
KOSIS_API_KEY=...   # kosis.kr 에서 무료 발급
```

---

## 파일 구조

```
industry_analyst/
    __init__.py         # industry_agent 객체 export
    agent.py            # LangGraph ReAct 에이전트 생성
    prompts.py          # 에이전트 페르소나 및 출력 스키마 정의
    tools.py            # 도구 함수 5개
    data/
        asset_ratio.csv     # 한국은행 기업경영분석 자산/자본 지표 (중소기업)
        profit_ratio.csv    # 한국은행 기업경영분석 손익 지표 (중소기업)
```

### data/ 폴더 파일 설명

| 파일 | 출처 | 내용 | 업종 범위 |
|---|---|---|---|
| `asset_ratio.csv` | 한국은행 ECOS 기업경영분석 5.1.3 | 부채비율, 유동비율 등 | KSIC 11차 대분류 기준 |
| `profit_ratio.csv` | 한국은행 ECOS 기업경영분석 5.1.2 | 영업이익률 등 | KSIC 11차 대분류 기준 |

> **주의**: ECOS API로 직접 조회 불가(SRCH_YN=N)한 데이터라 CSV로 로컬 저장. 데이터 갱신 시 ECOS 사이트에서 직접 다운로드 필요.
> 다운로드 경로: ecos.bok.or.kr → 통계검색 → 기업경영분석 → 5.1.2 손익지표 / 5.1.3 자산자본지표 → 중소기업 선택 → CSV 다운로드

> **없는 업종**: K(금융·보험), O(공공행정), Q(보건·사회복지), S94(협회·단체), T, U → `get_industry_avg_ratios`에서 "데이터 없음" 반환

---

## KSIC 매핑

DART `induty_code` 앞 2자리를 기준으로 KSIC 대분류에 매핑합니다.

| DART 코드 앞 2자리 | KSIC 대분류 |
|---|---|
| 10~34 | C 제조업 |
| 35 | D 전기, 가스 공급업 |
| 37~39 | E 수도, 하수, 폐기물 |
| 41~42 | F 건설업 |
| 45~47 | G 도매 및 소매업 |
| 49~52 | H 운수 및 창고업 |
| 55~56 | I 숙박 및 음식점업 |
| 58~63 | J 정보통신업 |
| 64~66 | K 금융 및 보험업 (데이터 없음) |
| 68 | L 부동산업 |
| 71~73 | M 전문, 과학 및 기술 서비스업 |
| 74~76 | N 사업시설 관리 및 임대 서비스업 |
| 85 | P 교육 서비스업 |
| 90~91 | R 예술, 스포츠 및 여가 서비스업 |
| 95~96 | S 개인 서비스업 |

---

## 도구 설명

### 1. `map_corp_to_ksic(corp_code)`
DART 회사개황에서 업종코드를 가져와 KSIC 코드로 변환합니다.

- **입력**: `corp_code` (8자리 DART 고유번호)
- **출력**: KSIC 코드 문자열 (예: `"C 제조업"`, `"P 교육 서비스업"`)
- **특이사항**: CSV에 없는 업종이면 `"N/A (업종코드 XXX - 산업평균 데이터 없음)"` 반환

### 2. `get_industry_avg_ratios(ksic_code, year)`
한국은행 기업경영분석 CSV에서 중소기업 산업평균 재무비율을 조회합니다.

- **입력**: `ksic_code`, `year`
- **출력**: 산업평균 영업이익률, 부채비율, 유동비율
- **특이사항**: `ksic_code`가 `N/A`로 시작하면 데이터 없음 반환

### 3. `compare_to_industry(company_ratios, industry_avg)`
기업 비율과 산업평균을 비교합니다.

- **입력**: 기업 비율 dict, 산업평균 dict
- **출력**: 각 지표별 `above` / `in-line` / `below` / `n/a`
- **기준**: 산업평균 대비 ±10% 이상이면 above/below
- **주의**: 현재 단독 에이전트로 실행 시 Financial Agent의 기업 비율을 State에서 받지 못해 `n/a`로 표시될 수 있음. Orchestrator와 연결되면 정상 동작함.

### 4. `get_industry_outlook(ksic_code)`
KOSIS 광공업생산지수에서 산업생산·재고·출하지수를 조회하여 업황 등급을 산출합니다.

- **입력**: `ksic_code`
- **출력**: 생산·재고·출하 YoY 변화율, 업황 등급 (Low/Medium/High)
- **등급 기준**:
  - High: 생산지수 YoY -10% 이하 + 재고 증가
  - Medium: 생산지수 YoY -5% ~ -10% 또는 재고 소폭 증가
  - Low: 생산지수 YoY 0% 이상

### 5. `get_macro_indicators()`
한국은행 ECOS에서 기준금리와 원달러환율을 조회합니다.

- **입력**: 없음
- **출력**: 기준금리, 원달러환율, 금리 추세

---

## 출력 스키마

```json
{
  "ksic_code": "map_corp_to_ksic 도구 결과 그대로 입력 (예: 'P 교육 서비스업')",
  "peer_comparison": {
    "debt_ratio": "above/in-line/below/n/a",
    "op_margin": "above/in-line/below/n/a",
    "current_ratio": "above/in-line/below/n/a"
  },
  "outlook_score": "Low/Medium/High",
  "macro_signals": {
    "base_rate": 0.0,
    "usd_krw": 0.0,
    "rate_trend": "rising/stable/falling"
  },
  "summary_kor": "산업 업황, 동종업계 비교 결과, 거시환경을 종합한 한 단락 요약"
}
```

---

## 테스트 결과

### 테스트 기업: 메가스터디교육 (corp_code: 01074862, 2023년)

**1. KSIC 코드 매핑**
```
P 교육 서비스업
```

**2. 산업평균 조회 (교육 서비스업 중소기업, 2023년)**
```
{'avg_op_margin': 0.0253, 'avg_debt_ratio': 1.6656, 'avg_current_ratio': 0.9708, 'ksic_code': 'P 교육 서비스업', 'year': 2023}
```

**3. 업계 비교**
```
{'debt_ratio': 'below', 'op_margin': 'above', 'current_ratio': 'below'}
```
- 부채비율: 업계 평균(166%) 대비 낮음 → 양호
- 영업이익률: 업계 평균(2.5%) 대비 높음 → 양호
- 유동비율: 업계 평균(97%) 대비 낮음 → 주의

**4. 업황 등급**
```
{'production_index_yoy': 0.0435, 'inventory_index_yoy': 0.0361, 'shipment_index_yoy': -0.0125, 'outlook_score': 'Low'}
```

**5. 거시지표**
```
{'base_rate': 3.0, 'usd_krw': 1313.7, 'rate_trend': 'stable'}
```

**6. 에이전트 테스트 결과 (LLM 호출)**

> **참고**: `peer_comparison`은 단독 실행 시 Financial Agent의 기업 비율을 State에서 받지 못해 n/a로 표시됩니다. Orchestrator 연결 후 정상 동작 예정입니다.

```json
{
  "ksic_code": "P 교육 서비스업",
  "peer_comparison": {
    "debt_ratio": "n/a",
    "op_margin": "n/a",
    "current_ratio": "n/a"
  },
  "outlook_score": "Low",
  "macro_signals": {
    "base_rate": 3.0,
    "usd_krw": 1313.7,
    "rate_trend": "stable"
  },
  "summary_kor": "해당 기업은 교육 서비스업에 속하며, 2023년 산업 전반의 성장세는 둔화되고 있습니다. 산업생산지수는 소폭 증가했으나, 출하지수는 하락세를 보여 업황이 부정적인 신호를 나타내고 있습니다. 거시환경은 기준금리 안정세와 원/달러 환율의 안정세로 별다른 급변동은 없으며, 전반적인 업황 전망은 낮은 편입니다."
}
```

---

## 사용 방법

### 도구 단독 테스트
```python
from agents.industry_analyst.tools import (
    map_corp_to_ksic,
    get_industry_avg_ratios,
    compare_to_industry,
    get_industry_outlook,
    get_macro_indicators
)
from dotenv import load_dotenv
load_dotenv()

ksic = map_corp_to_ksic.invoke({'corp_code': '01074862'})
avg = get_industry_avg_ratios.invoke({'ksic_code': ksic, 'year': 2023}) # 2025년도 가능
comp = compare_to_industry.invoke({'company_ratios': ratios, 'industry_avg': avg})
outlook = get_industry_outlook.invoke({'ksic_code': 'C'})
macro = get_macro_indicators.invoke({})
```

### 에이전트 테스트 (OpenAI API 비용 발생)
```python
from agents.industry_analyst import industry_agent
from dotenv import load_dotenv
load_dotenv()

result = industry_agent.invoke({
    'messages': [{'role': 'user', 'content': 'corp_code 01074862, 2023년 산업 분석해줘'}] # 2025년도 가능
})
print(result['messages'][-1].content)
```
