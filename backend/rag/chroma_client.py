from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np
from chromadb.api.types import EmbeddingFunction

COLLECTION_NAME = "industry_knowledge"
BACKEND_DIR = Path(__file__).resolve().parents[1]
DEFAULT_PERSIST_DIR = BACKEND_DIR / "vectorstore" / "industry_knowledge"

logger = logging.getLogger(__name__)

_ST_MODEL_NAME = "jhgan/ko-sroberta-multitask"
_st_model: Any = None


def _load_sentence_transformer() -> Any:
    """jhgan/ko-sroberta-multitask 모델을 최초 1회만 로딩한 뒤 모듈 수준에서 캐싱한다."""
    global _st_model
    if _st_model is None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "sentence-transformers is required: pip install sentence-transformers"
            ) from exc
        logger.info("rag_embedding_model_loading model=%s", _ST_MODEL_NAME)
        _st_model = SentenceTransformer(_ST_MODEL_NAME)
        logger.info("rag_embedding_model_loaded model=%s", _ST_MODEL_NAME)
    return _st_model


class KoSRobertaEmbeddingFunction(EmbeddingFunction[list[str]]):
    """jhgan/ko-sroberta-multitask 기반 한국어 의미 임베딩 함수 (768차원)."""

    _MODEL_NAME = _ST_MODEL_NAME
    _DIMENSIONS = 768

    def __init__(
        self,
        *,
        model_name: str = _MODEL_NAME,
        dimensions: int = _DIMENSIONS,
    ) -> None:
        self._model_name = model_name
        self._dimensions = dimensions

    @staticmethod
    def name() -> str:
        return "finagent_ko_sroberta_embedding"

    def get_config(self) -> dict[str, Any]:
        return {
            "model_name": self._model_name,
            "dimensions": self._dimensions,
        }

    @staticmethod
    def validate_config(config: dict[str, Any]) -> None:
        model_name = config.get("model_name", _ST_MODEL_NAME)
        dimensions = config.get("dimensions", KoSRobertaEmbeddingFunction._DIMENSIONS)

        if not isinstance(model_name, str) or not model_name.strip():
            raise ValueError("model_name은 비어 있지 않은 문자열이어야 합니다.")
        if not isinstance(dimensions, int) or dimensions <= 0:
            raise ValueError("dimensions는 1 이상의 정수여야 합니다.")

    def validate_config_update(
        self,
        old_config: dict[str, Any],
        new_config: dict[str, Any],
    ) -> None:
        self.validate_config(old_config)
        self.validate_config(new_config)
        if old_config != new_config:
            raise ValueError("임베딩 함수 설정은 생성 이후 변경할 수 없습니다.")

    @staticmethod
    def build_from_config(config: dict[str, Any]) -> "KoSRobertaEmbeddingFunction":
        KoSRobertaEmbeddingFunction.validate_config(config)
        return KoSRobertaEmbeddingFunction(
            model_name=str(config.get("model_name", _ST_MODEL_NAME)),
            dimensions=int(
                config.get(
                    "dimensions",
                    KoSRobertaEmbeddingFunction._DIMENSIONS,
                )
            ),
        )

    def __call__(self, input: list[str]) -> np.ndarray[Any, Any]:  # noqa: A002
        return _load_sentence_transformer().encode(
            list(input),
            normalize_embeddings=True,
        )

    def embed_query(self, input: list[str]) -> list[np.ndarray[Any, Any]]:
        return self.__call__(input)


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
        embedding_function=KoSRobertaEmbeddingFunction(),
        metadata={"description": "Industry credit rating methodology PDFs"},
    )
