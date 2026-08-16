"""Tests for the nllb translation service, mocking ctranslate2/transformers directly."""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

import server

client = TestClient(server.app)


def _fake_path(exists: bool) -> MagicMock:
    """pathlib.Path uses slots, so its instance methods can't be patched directly."""
    fake_path = MagicMock()
    fake_path.exists.return_value = exists
    return fake_path


def test_health_reports_converting_when_model_missing():
    """Before conversion, /health says so instead of claiming readiness."""
    with patch.object(server, "MODEL_DIR", _fake_path(False)):
        response = client.get("/health")
    assert response.json() == {"status": "converting"}


def test_health_reports_ready_when_model_present():
    """Once the model directory exists, /health reports ready."""
    with patch.object(server, "MODEL_DIR", _fake_path(True)):
        response = client.get("/health")
    assert response.json() == {"status": "ready"}


def test_ensure_model_skips_conversion_when_already_present():
    """A model already on disk is never re-downloaded/re-converted."""
    with (
        patch.object(server, "MODEL_DIR", _fake_path(True)),
        patch("server.ctranslate2.converters.TransformersConverter") as converter_cls,
    ):
        server._ensure_model()  # pylint: disable=protected-access
    converter_cls.assert_not_called()


def test_translate_endpoint_uses_cached_translator_and_tokenizer():
    """POST /translate flows through the cached translator/tokenizer and back out."""
    fake_result = MagicMock()
    fake_result.hypotheses = [["spa_Latn", "hola"]]
    fake_translator = MagicMock()
    fake_translator.translate_batch.return_value = [fake_result]

    fake_tokenizer = MagicMock()
    fake_tokenizer.decode.return_value = "hola"

    with (
        patch.object(server, "_translator", fake_translator),
        patch.object(server, "_tokenizers", {"eng_Latn": fake_tokenizer}),
    ):
        response = client.post(
            "/translate", json={"q": "hello", "source": "eng_Latn", "target": "spa_Latn"}
        )

    assert response.status_code == 200
    assert response.json() == {"translatedText": "hola"}
    fake_translator.translate_batch.assert_called_once()
