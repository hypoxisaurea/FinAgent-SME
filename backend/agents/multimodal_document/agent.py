from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from agents.base import Agent
from agents.multimodal_document.processor import (
    extract_pdf_chart_images,
    extract_pdf_text,
)

logger = logging.getLogger(__name__)


class MultiModalDocumentAgent:
    """공시자료 PDF와 이미지 기반 차트 정보를 추출하는 멀티모달 문서 에이전트."""

    name = "multimodal_document"

    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        """PDF 경로와 출력 디렉터리를 받아 문서 텍스트와 차트 이미지를 추출합니다."""
        pdf_path = payload.get("pdf_path")
        output_dir = payload.get("output_dir", "/tmp/multimodal_document")

        if not pdf_path:
            raise ValueError("payload must include 'pdf_path'")

        source_path = Path(pdf_path)
        if not source_path.exists():
            raise FileNotFoundError(f"PDF file not found: {source_path}")

        target_dir = Path(output_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            "Running multimodal document extraction: pdf_path=%s output_dir=%s",
            source_path,
            target_dir,
        )

        text_pages = extract_pdf_text(str(source_path))
        chart_images = extract_pdf_chart_images(str(source_path), target_dir)

        return {
            "name": self.name,
            "pdf_path": str(source_path),
            "output_dir": str(target_dir),
            "page_count": len(text_pages),
            "texts": text_pages,
            "chart_images": chart_images,
        }
