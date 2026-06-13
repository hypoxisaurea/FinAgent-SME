# Company Registry Builder Agent

## 역할

`CompanyRegistryBuilderAgent`는 DART 기반 기업 마스터/기업개황/재무 피처 구축 파이프라인을 감싸는 배치성 agent입니다.

## 현재 입력

- `target_year` (optional, 기본 `2024`)
- `run_sample_size` (optional)
- `skip_db_save` (optional, 기본 `False`)

## 현재 출력

- `company_registry_result`
- `dart_result`

공통 메타데이터:

- `status`
- `error_code`
- `fallback_used`
- `latency_ms`

## 내부 처리

1. 입력 payload에서 연도와 샘플 크기를 해석합니다.
2. `execute_dart_pipeline()`를 호출합니다.
3. 파이프라인 통계를 agent output으로 감싸 반환합니다.

## 상태 규칙

- 파이프라인 `status=success`면 agent도 `status=success`
- 그 외 상태면 `status=partial`, `error_code=DART_PIPELINE_DEGRADED`

## 사용 위치

- agent 이름: `company_registry_builder`
- 오케스트레이터 기본 심사 흐름에는 포함되지 않습니다.
- DB 구축/배치 시나리오에서 재사용 가능한 agent 래퍼입니다.

## 테스트

```bash
.venv/bin/pytest tests/unit/test_company_registry_pipeline_service.py -q
.venv/bin/pytest tests/cli/test_scripts_cli.py -q
```
