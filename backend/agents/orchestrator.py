from typing import Any


async def run_credit_workflow(company_name: str) -> dict[str, Any]:
    """
    멀티 에이전트 심사 파이프라인 진입점(MVP 스텁).
    이후 DART·뉴스·리스크·XAI 에이전트를 순차/병렬로 연결한다.
    """
    return {
        "company_name": company_name,
        "status": "stub",
        "message": "에이전트 파이프라인 미연결. orchestrator에서 단계별 호출을 구현하세요.",
    }
