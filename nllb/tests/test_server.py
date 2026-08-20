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
    fake_tokenizer.decode.return_value = "xEMOJIx0x hola mundo"

    with (
        patch.object(server, "_translator", fake_translator),
        patch.object(server, "_tokenizers", {"eng_Latn": fake_tokenizer}),
    ):
        response = client.post(
            "/translate", json={"q": "🏗️ hello world", "source": "eng_Latn", "target": "spa_Latn"}
        )

    assert response.json() == {"translatedText": "🏗️ hola mundo"}
    fake_tokenizer.encode.assert_called_once_with("xEMOJIx0x hello world")


def test_translate_protects_leading_emoji_after_a_zero_width_space():
    """Real bug: a zero-width space (U+200B) before the emoji -- common residue
    from copy-pasting rich text -- broke the anchored emoji regex entirely, so
    the emoji was never stripped, hit the tokenizer, and came back as <unk>.
    """
    zero_width_space = chr(0x200B)
    fake_result = MagicMock()
    fake_result.hypotheses = [["spa_Latn", "hola mundo"]]
    fake_translator = MagicMock()
    fake_translator.translate_batch.return_value = [fake_result]

    fake_tokenizer = MagicMock()
    fake_tokenizer.decode.return_value = "xEMOJIx0x hola mundo"

    with (
        patch.object(server, "_translator", fake_translator),
        patch.object(server, "_tokenizers", {"eng_Latn": fake_tokenizer}),
    ):
        response = client.post(
            "/translate",
            json={
                "q": f"{zero_width_space}👑 hello world",
                "source": "eng_Latn",
                "target": "spa_Latn",
            },
        )

    assert response.json() == {"translatedText": f"{zero_width_space}👑 hola mundo"}
    fake_tokenizer.encode.assert_called_once_with("xEMOJIx0x hello world")


def test_translate_protects_emoji_in_the_middle_of_a_sentence():
    """Real bug: a flag emoji after "react cu", not at the start of the line,
    was never protected -- it hit the tokenizer directly and NLLB doesn't have
    a token for most flags (regional-indicator pairs), so it came back as a
    literal <unk>.
    """
    fake_result = MagicMock()
    fake_result.hypotheses = [["ita_Latn", "reagisci con xEMOJIx0x per favore"]]
    fake_translator = MagicMock()
    fake_translator.translate_batch.return_value = [fake_result]

    fake_tokenizer = MagicMock()
    fake_tokenizer.decode.return_value = "reagisci con xEMOJIx0x per favore"

    with (
        patch.object(server, "_translator", fake_translator),
        patch.object(server, "_tokenizers", {"ron_Latn": fake_tokenizer}),
    ):
        response = client.post(
            "/translate",
            json={"q": "react cu 🇷🇴 please", "source": "ron_Latn", "target": "ita_Latn"},
        )

    assert response.json() == {"translatedText": "reagisci con 🇷🇴 per favore"}
    fake_tokenizer.encode.assert_called_once_with("react cu xEMOJIx0x please")


def test_translate_protects_multiple_emoji_in_the_same_sentence():
    """Two different emoji in one sentence must each land back in their own spot,
    not get mixed up with each other.
    """
    fake_result = MagicMock()
    fake_result.hypotheses = [["spa_Latn", "hola xEMOJIx0x mundo xEMOJIx1x"]]
    fake_translator = MagicMock()
    fake_translator.translate_batch.return_value = [fake_result]

    fake_tokenizer = MagicMock()
    fake_tokenizer.decode.return_value = "hola xEMOJIx0x mundo xEMOJIx1x"

    with (
        patch.object(server, "_translator", fake_translator),
        patch.object(server, "_tokenizers", {"eng_Latn": fake_tokenizer}),
    ):
        response = client.post(
            "/translate",
            json={"q": "hello 🎉 world 🔥", "source": "eng_Latn", "target": "spa_Latn"},
        )

    assert response.json() == {"translatedText": "hola 🎉 mundo 🔥"}
    fake_tokenizer.encode.assert_called_once_with("hello xEMOJIx0x world xEMOJIx1x")


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


def test_translate_normalizes_typographic_punctuation():
    """An em dash gets normalized to a plain hyphen before it ever reaches the tokenizer."""
    fake_result = MagicMock()
    fake_result.hypotheses = [["spa_Latn", "hola - mundo"]]
    fake_translator = MagicMock()
    fake_translator.translate_batch.return_value = [fake_result]

    fake_tokenizer = MagicMock()
    fake_tokenizer.decode.return_value = "hola - mundo"

    with (
        patch.object(server, "_translator", fake_translator),
        patch.object(server, "_tokenizers", {"eng_Latn": fake_tokenizer}),
    ):
        response = client.post(
            "/translate",
            json={"q": "hello — world", "source": "eng_Latn", "target": "spa_Latn"},
        )

    assert response.json() == {"translatedText": "hola - mundo"}
    fake_tokenizer.encode.assert_called_once_with("hello - world")


def test_translate_splits_multiple_sentences_within_a_line():
    """A line with two sentences translates both instead of dropping the second."""
    first_result = MagicMock()
    first_result.hypotheses = [["spa_Latn", "Hola."]]
    second_result = MagicMock()
    second_result.hypotheses = [["spa_Latn", "Esto es una prueba."]]
    fake_translator = MagicMock()
    fake_translator.translate_batch.return_value = [first_result, second_result]

    fake_tokenizer = MagicMock()
    fake_tokenizer.decode.side_effect = ["Hola.", "Esto es una prueba."]

    with (
        patch.object(server, "_translator", fake_translator),
        patch.object(server, "_tokenizers", {"eng_Latn": fake_tokenizer}),
    ):
        response = client.post(
            "/translate",
            json={"q": "Hello. This is a test.", "source": "eng_Latn", "target": "spa_Latn"},
        )

    assert response.json() == {"translatedText": "Hola. Esto es una prueba."}
    batch_arg = fake_translator.translate_batch.call_args.args[0]
    assert len(batch_arg) == 2


def test_translate_splits_sentences_after_stripping_a_heading_marker():
    """Heading protection and sentence splitting compose correctly on the same line."""
    first_result = MagicMock()
    first_result.hypotheses = [["spa_Latn", "Primera."]]
    second_result = MagicMock()
    second_result.hypotheses = [["spa_Latn", "Segunda."]]
    fake_translator = MagicMock()
    fake_translator.translate_batch.return_value = [first_result, second_result]

    fake_tokenizer = MagicMock()
    fake_tokenizer.decode.side_effect = ["Primera.", "Segunda."]

    with (
        patch.object(server, "_translator", fake_translator),
        patch.object(server, "_tokenizers", {"eng_Latn": fake_tokenizer}),
    ):
        response = client.post(
            "/translate",
            json={"q": "### First. Second.", "source": "eng_Latn", "target": "spa_Latn"},
        )

    assert response.json() == {"translatedText": "### Primera. Segunda."}
