from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

COLLECTION_NAME = "industry_knowledge"
BACKEND_DIR = Path(__file__).resolve().parents[1]
DEFAULT_PERSIST_DIR = BACKEND_DIR / "vectorstore" / "industry_knowledge"


class HashEmbeddingFunction:
    """외부 API 없이 동작하는 결정론적 해시 기반 로컬 임베딩 함수."""

    def __init__(self, dimensions: int = 384) -> None:
        self._dimensions = dimensions

    def name(self) -> str:
        return "finagent_hash_embedding"

    def get_config(self) -> dict[str, int]:
        return {"dimensions": self._dimensions}

    def validate_config(self, config: dict[str, Any]) -> None:
        dimensions = config.get("dimensions")
        if dimensions is not None and int(dimensions) <= 0:
            raise ValueError("dimensions must be positive")

    def __call__(self, input: list[str]) -> list[list[float]]:  # noqa: A002
        return [self._embed(text) for text in input]

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self._dimensions
        tokens = text.lower().split()
        if not tokens:
            return vector

        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self._dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign

        norm = sum(value * value for value in vector) ** 0.5
        if norm == 0:
            return vector
        return [value / norm for value in vector]


def get_chroma_client(persist_dir: Path | str | None = None) -> Any:
    """업종 신용평가방법론 문서용 영구 Chroma 클라이언트를 생성한다."""
    try:
        import chromadb
        from chromadb.config import Settings
    except ImportError as exc:
        raise RuntimeError("chromadb is required for industry RAG") from exc

    resolved_dir = Path(persist_dir or DEFAULT_PERSIST_DIR)
    resolved_dir.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(
        path=str(resolved_dir),
        settings=Settings(anonymized_telemetry=False),
    )


def get_industry_collection(
    persist_dir: Path | str | None = None,
    collection_name: str = COLLECTION_NAME,
) -> Any:
    """Industry RAG 검색기가 사용하는 Chroma 컬렉션을 반환한다."""
    client = get_chroma_client(persist_dir)
    return client.get_or_create_collection(
        name=collection_name,
        embedding_function=HashEmbeddingFunction(),
        metadata={"description": "Industry credit rating methodology PDFs"},
    )
