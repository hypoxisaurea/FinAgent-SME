from __future__ import annotations

import logging
from typing import Any

from backend.rag.retriever import DEFAULT_TOP_K, retrieve_industry_methodology
from fastmcp import FastMCP

logger = logging.getLogger(__name__)

mcp = FastMCP("FinAgent-SME Industry RAG")


@mcp.tool
def lookup_industry_methodology(
    query: str,
    industry_name: str | None = None,
    ksic_code: str | None = None,
    sub_sector: str | None = None,
    top_k: int = DEFAULT_TOP_K,
    use_hybrid: bool = False,
) -> dict[str, Any]:
    """업종 신용평가방법론 RAG 검색 결과와 출처를 반환한다."""
    logger.info(
        (
            "industry_mcp_lookup_started industry_name=%s ksic_code=%s "
            "sub_sector=%s top_k=%s use_hybrid=%s"
        ),
        industry_name,
        ksic_code,
        sub_sector,
        top_k,
        use_hybrid,
    )
    result = retrieve_industry_methodology(
        query=query,
        industry_name=industry_name,
        ksic_code=ksic_code,
        sub_sector=sub_sector,
        top_k=top_k,
        include_contexts=True,
        use_hybrid=use_hybrid,
    )
    methodology = result.get("industry_methodology", {})
    logger.info(
        "industry_mcp_lookup_finished unavailable=%s source_count=%s",
        methodology.get("unavailable"),
        len(result.get("methodology_sources", [])),
    )
    return result


def main() -> None:
    """FinAgent-SME Industry RAG MCP server를 stdio transport로 실행한다."""
    mcp.run()


if __name__ == "__main__":
    main()

