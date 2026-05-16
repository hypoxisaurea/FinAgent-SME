from typing import TypedDict, Annotated, Optional
from langgraph.graph.message import add_messages

class CreditState(TypedDict):
    # 입력
    corp_name: str
    corp_code: str
    target_year: int
    # Financial Agent 결과
    financial_ratios: Optional[dict]
    altman_z: Optional[dict]
    financial_flags: list[str]
    # Industry Agent 결과
    ksic_code: Optional[str]
    industry_comparison: Optional[dict]
    industry_outlook: Optional[dict]
    # 메시지 히스토리
    messages: Annotated[list, add_messages]