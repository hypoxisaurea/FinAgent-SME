# DART SME List Extractor

이 프로젝트는 DART(OpenDART)에서 중소기업 후보군과 기초 재무 데이터를 수집하는 1차 추출 도구입니다.

아직 전체 파이프라인이 agent화된 상태는 아니며, 현재는 팀원들이 후속 작업에 필요한 기본 데이터를 안정적으로 확보할 수 있도록 `dart_extract_sme_list.py`를 중심으로 사용합니다.

## 이 단계에서 할 수 있는 일

이 스크립트로 아래 3가지 결과를 만들 수 있습니다.

(`ksm_result` 폴더엔 제가 실행해서 얻은 데이터가 들어있습니다.)

- `sme_list.csv`
- `financial_features.csv`
- `financial_error_logs.csv`

즉, 팀은 이 단계에서 "대상 기업군 선정"과 "기초 재무 데이터 확보"까지 진행할 수 있습니다.

## 수집 기준

스크립트는 DART 기업 목록 중 `corp_cls`가 `K`, `N`인 기업을 대상으로 재무 데이터를 조회하고, 아래 조건을 만족하는 기업만 남깁니다.

- 자산총계 5,000억 이하
- 최근 3개년 평균 매출 1,000억 이하

기본 사업연도는 `2024`, 기본 보고서 코드는 `11011`입니다.

## 파일 구성

- `dart_extract_sme_list.py`: 메인 수집 스크립트
- `requirements.txt`: 실행에 필요한 패키지 목록

## 사전 준비

### 1. DART API Key 발급

OpenDART API Key가 필요합니다.

- OpenDART: https://opendart.fss.or.kr/

### 2. Python 환경 준비

이 프로젝트는 Python 3.13 환경에서 개발되었습니다.

가상환경 생성:

```bash
python3.13 -m venv .venv
source .venv/bin/activate
```
폴더 위치로 이동:
```bash
cd backend/agents/collector
```

패키지 설치:

```bash
pip install -r requirements.txt
```

## 실행 방법

### 1. API Key를 인자로 넘기는 방식

```bash
python dart_extract_sme_list.py --api-key YOUR_DART_API_KEY
```

### 2. 실행 중 직접 입력하는 방식

```bash
python dart_extract_sme_list.py
```

실행 후 프롬프트가 나오면 API Key를 입력하면 됩니다.

## 주요 옵션

- `--year`: 사업연도 지정
- `--report-code`: 보고서 코드 지정
- `--output-dir`: 결과 저장 폴더 지정
- `--sample-size`: 일부 기업만 테스트 실행
- `--run-self-test`: API 호출 없이 helper 테스트만 실행

예시:

```bash
python dart_extract_sme_list.py --api-key YOUR_DART_API_KEY --year 2024 --sample-size 100 --output-dir temp_result
```

## 팀 권장 실행 순서

처음 사용하는 팀원은 아래 순서를 권장합니다.

1. 가상환경 생성
2. `pip install -r requirements.txt`
3. `python dart_extract_sme_list.py --run-self-test`
4. `--sample-size 10` 또는 `--sample-size 100`으로 테스트 실행
5. 결과 파일 3종 확인
6. 전체 실행 `python dart_extract_sme_list.py --api-key YOUR_DART_API_KEY`

예시:

```bash
python dart_extract_sme_list.py --run-self-test
python dart_extract_sme_list.py --api-key YOUR_DART_API_KEY --year 2024 --sample-size 100 --output-dir temp_result
python dart_extract_sme_list.py --api-key YOUR_DART_API_KEY --year 2024 --output-dir final_result
```

## 결과 파일 설명

### `sme_list.csv`

필터를 통과한 기업 목록입니다.

주요 컬럼:

- `corp_code`
- `corp_name`
- `stock_code`
- `avg_revenue_last_3y`
- `total_assets`

팀에서 공용 대상 기업 리스트로 사용할 수 있습니다.

### `financial_features.csv`

기업별 연도별 재무 데이터입니다.

주요 컬럼:

- `corp_code`
- `corp_name`
- `stock_code`
- `year`
- `avg_revenue_last_3y`
- `total_assets`
- `revenue`
- `operating_income`
- `net_income`
- `total_assets_statement`
- `total_liabilities`
- `total_equity`

후속 분석, 기준 점검, agent 입력 데이터의 기반으로 사용할 수 있습니다.

### `financial_error_logs.csv`

수집 실패 또는 예외 상황을 기록한 파일입니다.

주요 컬럼:

- `error_datetime`
- `corp_code`
- `corp_name`
- `error_type`
- `message`

필요한 경우 `traceback`, `response`가 함께 기록될 수 있습니다.

## 자주 보는 에러 유형

- `NO_LIST`
- `EMPTY_DF`
- `NO_FS`
- `NO_ASSET`
- `ASSET_NAN`
- `NO_LIABILITY`
- `LIABILITY_NAN`
- `NO_REVENUE`
- `REVENUE_NAN`
- `EXCEPTION`

전체 실행 후에는 `financial_error_logs.csv`를 함께 확인하는 것을 권장합니다.

## 팀 활용 방식

현재 단계에서의 권장 사용 방식은 아래와 같습니다.

1. 한 명이 기준 연도와 실행 옵션을 정해서 결과를 생성합니다.
2. `sme_list.csv`를 팀 공용 대상 기업 리스트로 공유합니다.
3. `financial_features.csv`를 후속 분석이나 자동화 입력 데이터로 사용합니다.
4. `financial_error_logs.csv`를 보고 누락 기업이나 예외 케이스를 추적합니다.
5. 이후 agent workflow가 준비되면 이 결과 파일들을 입력 데이터로 연결합니다.

## 현재 범위

- 이 스크립트는 기본 데이터 확보 단계까지를 목표로 합니다.
- 전체 프로젝트는 아직 agent 중심 파이프라인으로 완전히 전환되지 않았습니다.
- 따라서 현재는 팀이 결과 파일을 직접 검토하고 다음 작업으로 넘기는 방식입니다.

## 빠른 시작

```bash
python dart_extract_sme_list.py --api-key YOUR_DART_API_KEY --year 2024 --sample-size 100 --output-dir temp_result
```

실행 후 아래 파일을 확인하면 됩니다.

- `temp_result/sme_list.csv`
- `temp_result/financial_features.csv`
- `temp_result/financial_error_logs.csv`

## 다음 단계

이 저장 결과를 바탕으로 이후에는 아래 작업으로 확장할 수 있습니다.

- agent workflow 입력 스키마 정리
- 재시도 전략 추가
- 후속 기업 상세 데이터 수집 자동화
- 전체 파이프라인 agent화

