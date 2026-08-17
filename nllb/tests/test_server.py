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


def test_translate_scales_max_decoding_length_with_input():
    """A long source text gets more than ctranslate2's 256-token default, so it doesn't truncate."""
    fake_result = MagicMock()
    fake_result.hypotheses = [["spa_Latn", "hola"]]
    fake_translator = MagicMock()
    fake_translator.translate_batch.return_value = [fake_result]

    long_source_tokens = [f"tok{i}" for i in range(200)]
    fake_tokenizer = MagicMock()
    fake_tokenizer.decode.return_value = "hola"
    fake_tokenizer.convert_ids_to_tokens.return_value = long_source_tokens

    with (
        patch.object(server, "_translator", fake_translator),
        patch.object(server, "_tokenizers", {"eng_Latn": fake_tokenizer}),
    ):
        client.post(
            "/translate", json={"q": "a long guide...", "source": "eng_Latn", "target": "spa_Latn"}
        )

    max_decoding_length = fake_translator.translate_batch.call_args.kwargs["max_decoding_length"]
    # pylint: disable-next=protected-access
    expected = len(long_source_tokens) * server._DECODING_LENGTH_MULTIPLIER
    assert max_decoding_length == expected
    assert max_decoding_length > 256


def test_translate_keeps_the_floor_for_short_input():
    """A short message still gets at least ctranslate2's original 256-token default."""
    fake_result = MagicMock()
    fake_result.hypotheses = [["spa_Latn", "hola"]]
    fake_translator = MagicMock()
    fake_translator.translate_batch.return_value = [fake_result]

    fake_tokenizer = MagicMock()
    fake_tokenizer.decode.return_value = "hola"
    fake_tokenizer.convert_ids_to_tokens.return_value = ["tok1", "tok2"]

    with (
        patch.object(server, "_translator", fake_translator),
        patch.object(server, "_tokenizers", {"eng_Latn": fake_tokenizer}),
    ):
        client.post("/translate", json={"q": "hello", "source": "eng_Latn", "target": "spa_Latn"})

    max_decoding_length = fake_translator.translate_batch.call_args.kwargs["max_decoding_length"]
    assert max_decoding_length == 256


def test_translate_multiline_text_batches_and_rejoins_each_line():
    """A multi-line message translates each line separately and rejoins them in order."""
    first_result = MagicMock()
    first_result.hypotheses = [["spa_Latn", "hola"]]
    second_result = MagicMock()
    second_result.hypotheses = [["spa_Latn", "mundo"]]
    fake_translator = MagicMock()
    fake_translator.translate_batch.return_value = [first_result, second_result]

    fake_tokenizer = MagicMock()
    fake_tokenizer.decode.side_effect = ["hola", "mundo"]

    with (
        patch.object(server, "_translator", fake_translator),
        patch.object(server, "_tokenizers", {"eng_Latn": fake_tokenizer}),
    ):
        response = client.post(
            "/translate", json={"q": "hello\nworld", "source": "eng_Latn", "target": "spa_Latn"}
        )

    assert response.json() == {"translatedText": "hola\nmundo"}
    batch_arg = fake_translator.translate_batch.call_args.args[0]
    assert len(batch_arg) == 2
    assert fake_translator.translate_batch.call_args.kwargs["target_prefix"] == [
        ["spa_Latn"],
        ["spa_Latn"],
    ]


def test_translate_preserves_blank_lines_without_sending_them():
    """Blank lines (section separators) pass through untouched, never hit the translator."""
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
            "/translate", json={"q": "\nhello\n\n", "source": "eng_Latn", "target": "spa_Latn"}
        )

    assert response.json() == {"translatedText": "\nhola\n\n"}
    batch_arg = fake_translator.translate_batch.call_args.args[0]
    assert len(batch_arg) == 1


def test_translate_protects_markdown_heading_marker():
    """A '### Heading' line keeps its marker intact; only the text gets translated."""
    fake_result = MagicMock()
    fake_result.hypotheses = [["spa_Latn", "Por qué"]]
    fake_translator = MagicMock()
    fake_translator.translate_batch.return_value = [fake_result]

    fake_tokenizer = MagicMock()
    fake_tokenizer.decode.return_value = "Por qué"

    with (
        patch.object(server, "_translator", fake_translator),
        patch.object(server, "_tokenizers", {"eng_Latn": fake_tokenizer}),
    ):
        response = client.post(
            "/translate", json={"q": "### Why", "source": "eng_Latn", "target": "spa_Latn"}
        )

    assert response.json() == {"translatedText": "### Por qué"}
    fake_tokenizer.encode.assert_called_once_with("Why")


def test_translate_protects_leading_emoji():
    """A leading emoji is preserved as-is, not sent through the tokenizer/model."""
    fake_result = MagicMock()
    fake_result.hypotheses = [["spa_Latn", "hola mundo"]]
    fake_translator = MagicMock()
    fake_translator.translate_batch.return_value = [fake_result]

    fake_tokenizer = MagicMock()
    fake_tokenizer.decode.return_value = "hola mundo"

    with (
        patch.object(server, "_translator", fake_translator),
        patch.object(server, "_tokenizers", {"eng_Latn": fake_tokenizer}),
    ):
        response = client.post(
            "/translate", json={"q": "🏗️ hello world", "source": "eng_Latn", "target": "spa_Latn"}
        )

    assert response.json() == {"translatedText": "🏗️ hola mundo"}
    fake_tokenizer.encode.assert_called_once_with("hello world")


def test_translate_skips_the_translator_for_a_heading_only_line():
    """A heading marker with nothing after it (no text) never reaches the translator."""
    fake_translator = MagicMock()
    fake_tokenizer = MagicMock()

    with (
        patch.object(server, "_translator", fake_translator),
        patch.object(server, "_tokenizers", {"eng_Latn": fake_tokenizer}),
    ):
        response = client.post(
            "/translate", json={"q": "### ", "source": "eng_Latn", "target": "spa_Latn"}
        )

    assert response.json() == {"translatedText": "### "}
    fake_translator.translate_batch.assert_not_called()
