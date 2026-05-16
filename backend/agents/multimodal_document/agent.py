"""Multimodal Document Agent 구현체"""

from __future__ import annotations

from typing import Any

from .graph import run_multimodal_document_agent


class MultimodalDocumentAgent:
    """PDF 사업보고서에서 텍스트·테이블·차트를 추출하고 요약하는 에이전트."""

    name: str = "multimodal_document"

    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Multimodal Document Agent 실행.

        Args:
            payload:
                company_name (str)         : 기업명
                corp_code    (str)         : DART 고유번호
                pdf_bytes    (bytes | None): PDF 바이너리
                pdf_path     (str | None)  : PDF 파일 경로 (pdf_bytes 없을 때)

        Returns:
            MultimodalDocumentResult.model_dump()
        """
        result = await run_multimodal_document_agent(
            company_name=payload["company_name"],
            corp_code=payload["corp_code"],
            pdf_bytes=payload.get("pdf_bytes"),
            pdf_path=payload.get("pdf_path"),
        )
        return result.model_dump()
