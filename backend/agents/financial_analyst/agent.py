from langchain_anthropic import ChatAnthropic
from langgraph.prebuilt import create_react_agent

from .prompts import FINANCIAL_PROMPT
from .tools import (
    get_financial_statements,
    calc_financial_ratios,
    calc_altman_z_prime,
    trend_analysis,
)

llm = ChatAnthropic(model="claude-sonnet-4-6")

financial_agent = create_react_agent(
    model=llm,
    tools=[
        get_financial_statements,
        calc_financial_ratios,
        calc_altman_z_prime,
        trend_analysis,
    ],
    name="financial_analyst",
    prompt=FINANCIAL_PROMPT,
)
