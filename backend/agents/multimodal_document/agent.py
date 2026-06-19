from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any, Callable

from backend.agents.multimodal_document.processor import (
    extract_pdf_chart_images,
    extract_pdf_text,
)
from backend.common.agent import Agent
from backend.common.contracts import build_agent_output, elapsed_ms
from backend.schemas.agent_contracts import (
    MultiModalDocumentInput,
    MultiModalDocumentOutput,
)

logger = logging.getLogger(__name__)

@dataclass(slots=True)
class AgentTask:
    """멀티모달 문서 에이전트가 실행하는 내부 작업 단위."""

    name: str
    handler: Callable[[dict[str, Any]], dict[str, Any]]


class MultiModalDocumentAgent(Agent):
    """공시자료 PDF와 이미지 기반 차트 정보를 추출하는 멀티모달 문서 에이전트."""

    name = "multimodal_document"
    input_model = MultiModalDocumentInput
    output_model = MultiModalDocumentOutput

    def __init__(self) -> None:
        self._tasks = [
            AgentTask(name="extract_text", handler=self._extract_text),
            AgentTask(name="extract_chart_images", handler=self._extract_chart_images),
        ]

    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        """payload 컨텍스트를 기반으로 내부 작업을 계획하고 순차 실행합니다."""
        started_at = perf_counter()
        context = self._build_context(payload)
        task_results: dict[str, Any] = {
            "name": self.name,
            "pdf_path": str(context["pdf_path"]),
            "output_dir": str(context["output_dir"]),
        }

        for task in self._plan():
            logger.info("Executing multimodal task: %s", task.name)
            result = task.handler(context)
            if not isinstance(result, dict):
                raise TypeError(
                    (
                        f"{self.name} task '{task.name}' must return a dict, "
                        f"got {type(result).__name__}"
                    )
                )
            context.update(result)
            task_results.update(result)

        task_results["page_count"] = len(task_results.get("texts", []))
        return build_agent_output(task_results, latency_ms=elapsed_ms(started_at))

    def _build_context(self, payload: dict[str, Any]) -> dict[str, Any]:
        pdf_path = payload.get("pdf_path")
        output_dir = payload.get("output_dir", "/tmp/multimodal_document")

        if not pdf_path:
            raise ValueError("payload must include 'pdf_path'")

        source_path = Path(pdf_path)
        if not source_path.exists():
            raise FileNotFoundError(f"PDF file not found: {source_path}")

        target_dir = Path(output_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        return {
            "pdf_path": source_path,
            "output_dir": target_dir,
        }

    def _plan(self) -> list[AgentTask]:
        return list(self._tasks)

    def _extract_text(self, context: dict[str, Any]) -> dict[str, Any]:
        pdf_path = context["pdf_path"]
        text_pages = extract_pdf_text(str(pdf_path))
        return {"texts": text_pages}

    def _extract_chart_images(self, context: dict[str, Any]) -> dict[str, Any]:
        pdf_path = context["pdf_path"]
        output_dir = context["output_dir"]
        chart_images = extract_pdf_chart_images(str(pdf_path), output_dir)
        return {"chart_images": chart_images}
