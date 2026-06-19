from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np

from backend.rag.chroma_client import KoSRobertaEmbeddingFunction


def test_name_returns_identifier() -> None:
    fn = KoSRobertaEmbeddingFunction()
    assert fn.name() == "finagent_ko_sroberta_embedding"


def test_get_config_returns_model_and_dimensions() -> None:
    fn = KoSRobertaEmbeddingFunction()
    config = fn.get_config()
    assert config["dimensions"] == 768
    assert "ko-sroberta" in config["model_name"]


def test_validate_config_accepts_any_config() -> None:
    fn = KoSRobertaEmbeddingFunction()
    fn.validate_config({})
    fn.validate_config({"dimensions": 768, "model_name": "any"})


def test_call_encodes_with_normalization() -> None:
    fn = KoSRobertaEmbeddingFunction()
    mock_model = MagicMock()
    mock_model.encode.return_value = np.array([[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]])

    with patch("backend.rag.chroma_client._load_sentence_transformer", return_value=mock_model):
        result = fn(["부채비율", "레버리지"])

    mock_model.encode.assert_called_once_with(["부채비율", "레버리지"], normalize_embeddings=True)
    assert len(result) == 2
    assert len(result[0]) == 3
    assert all(isinstance(v, float) for v in result[0])


def test_call_returns_list_of_lists() -> None:
    fn = KoSRobertaEmbeddingFunction()
    mock_model = MagicMock()
    mock_model.encode.return_value = np.array([[1.0, 0.0], [0.0, 1.0], [0.5, 0.5]])

    with patch("backend.rag.chroma_client._load_sentence_transformer", return_value=mock_model):
        result = fn(["a", "b", "c"])

    assert isinstance(result, list)
    assert all(isinstance(row, list) for row in result)
    assert len(result) == 3
