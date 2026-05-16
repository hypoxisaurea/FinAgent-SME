from dotenv import load_dotenv
load_dotenv()

from langchain_anthropic import ChatAnthropic
from langgraph.prebuilt import create_react_agent

from langchain_openai import ChatOpenAI
from .tools import (
    map_corp_to_ksic,
    get_industry_avg_ratios,
    compare_to_industry,
    get_industry_outlook,
    get_macro_indicators,
)

llm = ChatOpenAI(model="gpt-4.1-nano")

industry_agent = create_react_agent(
    model=llm,
    tools=[
        map_corp_to_ksic,
        get_industry_avg_ratios,
        compare_to_industry,
        get_industry_outlook,
        get_macro_indicators,
    ],
    name="industry_analyst",
    prompt=INDUSTRY_PROMPT,
)
