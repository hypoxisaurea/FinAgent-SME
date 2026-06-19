from __future__ import annotations

import warnings
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from backend.rag.chroma_client import KoSRobertaEmbeddingFunction


def test_name_returns_identifier() -> None:
    fn = KoSRobertaEmbeddingFunction()
    assert fn.name() == "finagent_ko_sroberta_embedding"


def test_init_does_not_emit_chroma_deprecation_warning() -> None:
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        KoSRobertaEmbeddingFunction()

    messages = [str(warning.message) for warning in captured]
    assert not any("does not implement __init__" in message for message in messages)


def test_get_config_returns_model_and_dimensions() -> None:
    fn = KoSRobertaEmbeddingFunction()
    config = fn.get_config()
    assert config["dimensions"] == 768
    assert "ko-sroberta" in config["model_name"]


def test_build_from_config_round_trips_config() -> None:
    fn = KoSRobertaEmbeddingFunction.build_from_config(
        {
            "model_name": "jhgan/ko-sroberta-multitask",
            "dimensions": 768,
        }
    )

    assert isinstance(fn, KoSRobertaEmbeddingFunction)
    assert fn.get_config() == {
        "model_name": "jhgan/ko-sroberta-multitask",
        "dimensions": 768,
    }


def test_validate_config_accepts_any_config() -> None:
    fn = KoSRobertaEmbeddingFunction()
    fn.validate_config({})
    fn.validate_config({"dimensions": 768, "model_name": "any"})


def test_validate_config_rejects_invalid_values() -> None:
    with pytest.raises(ValueError, match="model_name"):
        KoSRobertaEmbeddingFunction.validate_config({"model_name": ""})

    with pytest.raises(ValueError, match="dimensions"):
        KoSRobertaEmbeddingFunction.validate_config({"dimensions": 0})


def test_call_encodes_with_normalization() -> None:
    fn = KoSRobertaEmbeddingFunction()
    mock_model = MagicMock()
    mock_model.encode.return_value = np.array([[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]])

    with patch("backend.rag.chroma_client._load_sentence_transformer", return_value=mock_model):
        result = fn(["부채비율", "레버리지"])

    mock_model.encode.assert_called_once_with(["부채비율", "레버리지"], normalize_embeddings=True)
    assert len(result) == 2
    assert len(result[0]) == 3
    assert isinstance(result[0], np.ndarray)
    assert np.issubdtype(result[0].dtype, np.floating)
    assert all(isinstance(v.item(), float) for v in result[0])


def test_call_returns_chroma_normalized_embeddings() -> None:
    fn = KoSRobertaEmbeddingFunction()
    mock_model = MagicMock()
    mock_model.encode.return_value = np.array([[1.0, 0.0], [0.0, 1.0], [0.5, 0.5]])

    with patch("backend.rag.chroma_client._load_sentence_transformer", return_value=mock_model):
        result = fn(["a", "b", "c"])

    assert isinstance(result, list)
    assert all(isinstance(row, np.ndarray) for row in result)
    assert all(np.issubdtype(row.dtype, np.floating) for row in result)
    assert len(result) == 3
