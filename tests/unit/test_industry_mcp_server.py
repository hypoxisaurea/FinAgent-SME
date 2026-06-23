from __future__ import annotations

import asyncio
from typing import Any

from fastmcp import Client

from backend.mcp import industry_server


def test_industry_mcp_lists_and_calls_rag_tool(monkeypatch) -> None:
    def fake_retrieve_industry_methodology(**kwargs: Any) -> dict[str, Any]:
        return {
            "industry_methodology": {
                "industry_name": "건설업",
                "summary": "수주잔고와 PF 우발채무를 중심으로 평가합니다.",
                "source_count": 1,
                "unavailable": False,
                "error": None,
            },
            "methodology_sources": [
                {
                    "filename": "2025 건설업 신용평가방법론.pdf",
                    "page": 10,
                    "score": 0.91,
                    "industry_name": "건설업",
                    "ksic_code": "F 건설업",
                    "sub_sector": "건설",
                }
            ],
            "retrieved_contexts": ["건설업은 수주잔고와 PF 우발채무를 확인합니다."],
            "received_kwargs": kwargs,
        }

    monkeypatch.setattr(
        industry_server,
        "retrieve_industry_methodology",
        fake_retrieve_industry_methodology,
    )

    result = asyncio.run(_list_and_call_industry_tool())

    assert result["industry_methodology"]["industry_name"] == "건설업"
    assert result["industry_methodology"]["unavailable"] is False
    assert result["methodology_sources"][0]["filename"].endswith("신용평가방법론.pdf")
    assert result["received_kwargs"] == {
        "query": "건설업 핵심 평가요소",
        "industry_name": None,
        "ksic_code": "F 건설업",
        "sub_sector": "건설",
        "top_k": 3,
        "include_contexts": True,
        "use_hybrid": False,
    }


async def _list_and_call_industry_tool() -> dict[str, Any]:
    async with Client(industry_server.mcp) as client:
        tools = await client.list_tools()
        assert any(tool.name == "lookup_industry_methodology" for tool in tools)

        result = await client.call_tool(
            "lookup_industry_methodology",
            {
                "query": "건설업 핵심 평가요소",
                "ksic_code": "F 건설업",
                "sub_sector": "건설",
                "top_k": 3,
            },
        )
        return result.data
