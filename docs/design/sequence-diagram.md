# 시퀀스 다이어그램

## 1. 문서 개요

- 문서 목적: FinAgent-SME 심사 요청의 주요 호출 순서를 시각적으로 설명한다.
- 표기 기준: `Supervisor = WorkflowOrchestrator`, `Sub-Agent = 개별 Agent`

## 2. 실시간 심사 워크플로우 시퀀스

```mermaid
sequenceDiagram
    actor User as 심사 담당자
    participant UI as Streamlit UI
    participant API as FastAPI Workflows API
    participant SUP as Supervisor<br/>WorkflowOrchestrator
    participant RES as CompanyResolverAgent
    participant NEWS as NewsCollectorAgent
    participant FIN as FinancialAnalystAgent
    participant RISK as RiskEventAgent
    participant IND as IndustryAnalystAgent
    participant DOC as MultiModalDocumentAgent
    participant DEC as DecisionAgent
    participant REP as ReportAgent
    participant DB as PostgreSQL
    participant EXT as External APIs/LLM
    participant LF as Langfuse

    User->>UI: 회사명 입력 후 검색
    UI->>API: POST /api/v1/workflows/orchestrator
    API->>API: request_id 생성/바인딩
    API->>SUP: run_credit_workflow(company_name, request_id)
    SUP->>LF: trace 시작

    SUP->>RES: run(payload)
    RES->>DB: sme_list 조회
    DB-->>RES: corp_code, corp_name or 없음

    alt 대상 기업 아님
        RES-->>SUP: company_found=false, workflow_status=not_target
        SUP-->>API: not_target 결과
        API-->>UI: not_target 응답
    else 대상 기업
        par 병렬 분석
            SUP->>NEWS: run(payload)
            NEWS->>DB: sme_list / daum_news_articles
            NEWS->>EXT: Daum News / OpenAI
            NEWS->>LF: tool + generation trace
            NEWS-->>SUP: news_data, news_result
        and
            SUP->>FIN: run(payload)
            FIN->>DB: financial_features 조회
            FIN->>EXT: DART/재무 도구
            FIN-->>SUP: financial_ratios, grade_cap
        and
            opt pdf_path 존재
                SUP->>DOC: run(payload)
                DOC->>EXT: 문서/PDF 처리
                DOC-->>SUP: document_summary
            end
        end

        SUP->>RISK: run(news_data, corp_code)
        RISK->>EXT: OpenAI 감성 분석 + 리스크 핸들러
        RISK-->>SUP: overall_risk_level, event counts

        SUP->>IND: run(financial_ratios, corp_code)
        IND->>EXT: 산업/거시 지표
        IND-->>SUP: peer_comparison, macro_indicators

        SUP->>DEC: run(merged context)
        DEC->>EXT: OpenAI explanation
        DEC-->>SUP: decision, credit_grade, recommended_limit

        SUP->>REP: run(decision context)
        REP-->>SUP: report

        SUP->>LF: trace 종료, output 기록
        SUP-->>API: success/partial 결과
        API-->>UI: JSON 응답
        UI->>User: 리포트 화면 표시
    end
```

## 3. 장애 대응 시퀀스

```mermaid
sequenceDiagram
    participant SUP as Supervisor
    participant AG as Failing Agent
    participant TOOL as Internal Tool
    participant LF as Langfuse

    SUP->>AG: run(payload)
    AG->>TOOL: execute_tool_step()

    alt tool fallback 가능
        TOOL-->>AG: fallback value + tool_errors
        AG-->>SUP: status=partial, fallback_used=true
        SUP->>LF: partial 상태 기록
        SUP-->>SUP: continue_on_error 여부에 따라 후속 실행
    else 치명적 실패
        TOOL-->>AG: exception
        AG-->>SUP: status=failed
        SUP->>LF: failed 상태 기록
        alt continue_on_error=false
            SUP-->>SUP: downstream 중단
        else continue_on_error=true
            SUP-->>SUP: 부분 성공으로 후속 단계 계속
        end
    end
```

## 4. 배치 데이터 구축 시퀀스

```mermaid
sequenceDiagram
    actor Operator as 운영자/개발자
    participant CLI as setup-db.sh build
    participant SVC as company_registry_pipeline
    participant DART as OpenDART
    participant DB as PostgreSQL

    Operator->>CLI: build --year 2024 --sample-size 10
    CLI->>SVC: execute_dart_pipeline(year, sample_size)
    SVC->>DART: 기업/재무 데이터 수집
    DART-->>SVC: 원천 데이터
    SVC->>SVC: final_df, sme_list_df, error_df 생성
    SVC->>DB: sme_list 저장
    SVC->>DB: financial_features 저장
    SVC->>DB: financial_error_logs 저장
    SVC-->>CLI: 저장 결과 반환
```
