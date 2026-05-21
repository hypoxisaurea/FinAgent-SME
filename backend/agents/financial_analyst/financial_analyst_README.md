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
OPEN_DART_API_KEY=...   # opendart.fss.or.kr 에서 무료 발급
```

---

## 파일 구조

```
financial_analyst/
    __init__.py     # financial_agent 객체 export
    agent.py        # LangGraph ReAct 에이전트 생성
    prompts.py      # 에이전트 페르소나 및 출력 스키마 정의
    tools.py        # 도구 함수 5개
```

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
| 안정성 | 이자보상배율 (interest_coverage) | 영업이익 / 이자비용 |
| 활동성 | 매출채권회전율 (receivable_turnover) | 매출액 / 매출채권 |
| 활동성 | 총자산회전율 (asset_turnover) | 매출액 / 총자산 |
| 활동성 | 매입채무회전율 (payable_turnover) | 매출원가 / 매입채무 |
| 수익성 | ROA | 당기순이익 / 총자산 |
| 수익성 | 영업이익률 (op_margin) | 영업이익 / 매출액 |
| 수익성 | 매출원가율 (cogs_ratio) | 매출원가 / 매출액 |
| 현금흐름 | OCF/매출액 (ocf_to_sales) | 영업현금흐름 / 매출액 |
| 현금흐름 | OCF/당기순이익 (ocf_to_net_income) | 영업현금흐름 / 당기순이익 |
| 현금흐름 | FCF (잉여현금흐름) | 영업현금흐름 - 유형자산취득 |
| 현금흐름 | FCF/매출액 (fcf_to_sales) | FCF / 매출액 |

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

### 4. `trend_analysis(corp_code, years)`

복수 연도 재무지표의 추세 분석과 급변 항목 탐지를 수행합니다.

- **입력**: `corp_code`, `years` (분석 연도 리스트, 권장 3개년)
- **출력**: 이상 플래그 목록, YoY 변화량, 연도별 히스토리

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

**절댓값 플래그 (최신 연도)**

| 조건 | 플래그 |
|---|---|
| ICR < 1.0 | `{year}_icr_danger_X.XX` |
| 1.0 ≤ ICR < 1.5 | `{year}_icr_caution_X.XX` |
| 부채비율 ≥ 300% | `{year}_debt_ratio_danger_XXX%` |
| 200% ≤ 부채비율 < 300% | `{year}_debt_ratio_caution_XXX%` |

### 5. `apply_risk_filters(fs, history)`

재무 데이터 기반 신용등급 상한(`grade_cap`)을 결정합니다.

- **입력**: `fs` (`get_financial_statements` 결과), `history` (`trend_analysis` 결과의 history)
- **출력**: 등급 상한, 발동된 필터 목록, 필터별 판단 근거

**필터 우선순위**

| 우선순위 | 조건 | grade_cap |
|---|---|---|
| 1 | 자기자본 ≤ 0 (전액잠식) | CCC |
| 2 | 자기자본비율 ≤ 10% | CCC |
| 3 | 당기순손실 2개년 연속 | B |
| 4 | 0 < 매출액 < 3억 | B+ |
| 5 | 3억 ≤ 매출액 < 20억 | BB+ |

> 복수 필터 발동 시 가장 강한 제약(낮은 등급) 적용. `grade_cap`은 절대 상한이며 실제 최종 등급은 Orchestrator 레벨에서 산출됩니다.

---

## 출력 스키마

> *추가 예정*

---

## 테스트 결과

> *추가 예정*

---

## 사용 방법

> *추가 예정*
