from backend_env import load_backend_env

load_backend_env()

from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from .financial_prompts import FINANCIAL_PROMPT
from .financial_tools import (
    get_financial_statements,
    calc_financial_ratios,
    calc_altman_z_prime,
    trend_analysis,
    apply_risk_filters,
)

llm = ChatOpenAI(model="gpt-4.1-nano")

financial_agent = create_react_agent(
    model=llm,
    tools=[
        get_financial_statements,
        calc_financial_ratios,
        calc_altman_z_prime,
        trend_analysis,
        apply_risk_filters,
    ],
    name="financial_analyst",
    prompt=FINANCIAL_PROMPT,
)
