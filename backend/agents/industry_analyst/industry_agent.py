from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from backend_env import load_backend_env

from .industry_prompts import INDUSTRY_PROMPT
from .industry_tools import (
    get_business_cycle,
    get_industry_avg_ratios,
    get_industry_outlook,
    get_macro_indicators,
    map_corp_to_ksic,
)

load_backend_env()

llm = ChatOpenAI(model="gpt-4.1-nano")

industry_agent = create_react_agent(
    model=llm,
    tools=[
        map_corp_to_ksic,
        get_industry_avg_ratios,
        get_industry_outlook,
        get_business_cycle,
        get_macro_indicators,
    ],
    name="industry_analyst",
    prompt=INDUSTRY_PROMPT,
)
