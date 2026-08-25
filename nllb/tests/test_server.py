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


def test_translate_restores_an_emoji_placeholder_the_model_capitalized():
    """Real bug (Beastmaster guide -> Romanian): a placeholder that lands at the
    start of a sentence gets treated as a word and capitalized by the model
    (xEMOJIx0x -> XEMOJIx0x), so a case-sensitive restore left the literal
    placeholder in the published translation instead of the emoji.
    """
    fake_result = MagicMock()
    fake_result.hypotheses = [["ron_Latn", "convocarea"]]
    fake_translator = MagicMock()
    fake_translator.translate_batch.return_value = [fake_result]

    fake_tokenizer = MagicMock()
    fake_tokenizer.decode.return_value = "XEMOJIx0x Beastmaster - convocarea"

    with (
        patch.object(server, "_translator", fake_translator),
        patch.object(server, "_tokenizers", {"eng_Latn": fake_tokenizer}),
    ):
        response = client.post(
            "/translate",
            json={"q": "🐲 Beastmaster — summoning", "source": "eng_Latn", "target": "ron_Latn"},
        )

    assert response.json() == {"translatedText": "🐲 Beastmaster - convocarea"}


def _translate_with_decode(source_text: str, decoded_text: str) -> tuple[dict, MagicMock]:
    """Run /translate with the model mocked to return decoded_text; returns
    (response json, fake_tokenizer) so callers can assert what got encoded."""
    fake_result = MagicMock()
    fake_result.hypotheses = [["spa_Latn", "x"]]
    fake_translator = MagicMock()
    fake_translator.translate_batch.return_value = [fake_result]

    fake_tokenizer = MagicMock()
    fake_tokenizer.decode.return_value = decoded_text

    with (
        patch.object(server, "_translator", fake_translator),
        patch.object(server, "_tokenizers", {"eng_Latn": fake_tokenizer}),
    ):
        response = client.post(
            "/translate", json={"q": source_text, "source": "eng_Latn", "target": "spa_Latn"}
        )
    return response.json(), fake_tokenizer


def test_translate_protects_a_glossary_term():
    """Real bug (Beastmaster guide -> Romanian): in-game terms came back
    translated or corrupted ("Beastmaster" -> "Maestrul Bestiei"); glossary
    terms must reach the model as placeholders and come back verbatim.
    """
    result, fake_tokenizer = _translate_with_decode("the Beastmaster leads", "el xEMOJIx0x lidera")

    assert result == {"translatedText": "el Beastmaster lidera"}
    fake_tokenizer.encode.assert_called_once_with("the xEMOJIx0x leads")


def test_translate_protects_a_multi_word_term_as_one_unit():
    """ "Behemoth Points" is one term -- longest-first matching, so it must not
    decompose into a protected "Behemoth" plus a translatable "Points"
    (the Romanian incident dropped "Points" entirely).
    """
    result, fake_tokenizer = _translate_with_decode(
        "spend Behemoth Points wisely", "gasta xEMOJIx0x sabiamente"
    )

    assert result == {"translatedText": "gasta Behemoth Points sabiamente"}
    fake_tokenizer.encode.assert_called_once_with("spend xEMOJIx0x wisely")


def test_translate_keeps_the_authors_casing_on_a_protected_term():
    """Matching is case-insensitive but restoring gives back exactly what the
    author wrote -- a lowercase "behemoths" stays lowercase."""
    result, _ = _translate_with_decode("two behemoths fell", "dos xEMOJIx0x cayeron")

    assert result == {"translatedText": "dos behemoths cayeron"}


def test_translate_leaves_common_words_alone():
    """Only the exact all-caps UI label is protected -- lowercase "fighting" in a
    normal sentence must still reach the model translatable."""
    _, fake_tokenizer = _translate_with_decode("we are fighting tonight", "peleamos hoy")

    fake_tokenizer.encode.assert_called_once_with("we are fighting tonight")


def test_translate_protects_an_emoji_and_a_term_in_the_same_sentence():
    """Emoji and glossary terms share one placeholder namespace -- interleaved
    indices must each restore to their own original."""
    result, fake_tokenizer = _translate_with_decode(
        "⚔️ the Beastmaster strikes", "xEMOJIx0x el xEMOJIx1x golpea"
    )

    assert result == {"translatedText": "⚔️ el Beastmaster golpea"}
    fake_tokenizer.encode.assert_called_once_with("xEMOJIx0x the xEMOJIx1x strikes")


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


def test_load_glossary_missing_file_degrades_to_empty(tmp_path):
    """No mounted glossary means an empty one -- the service must still start."""
    # pylint: disable=protected-access
    assert server._load_glossary(tmp_path / "absent.json") == ((), ())


def test_load_glossary_invalid_json_degrades_to_empty(tmp_path):
    """A malformed glossary file is ignored, never a crash at import time."""
    path = tmp_path / "glossary.json"
    path.write_text("{not json", encoding="utf-8")
    # pylint: disable=protected-access
    assert server._load_glossary(path) == ((), ())


def test_load_glossary_non_object_json_degrades_to_empty(tmp_path):
    """Valid JSON that isn't an object (e.g. a bare list) is rejected as a whole."""
    path = tmp_path / "glossary.json"
    path.write_text('["just", "a", "list"]', encoding="utf-8")
    # pylint: disable=protected-access
    assert server._load_glossary(path) == ((), ())


def test_load_glossary_reads_both_term_groups_and_drops_blanks(tmp_path):
    """Both groups load; blank/whitespace-only entries never become terms."""
    path = tmp_path / "glossary.json"
    path.write_text('{"any_case": ["Behemoth", "  "], "exact_case": ["SUMMON"]}', encoding="utf-8")
    # pylint: disable=protected-access
    assert server._load_glossary(path) == (("Behemoth",), ("SUMMON",))


def test_terms_regex_is_none_for_an_empty_glossary():
    """An empty alternation would match the empty string at every word boundary,
    littering placeholders through the text -- the regex must be absent entirely."""
    # pylint: disable=protected-access
    assert server._terms_regex(()) is None


def test_protect_verbatim_with_empty_glossary_leaves_plain_text_untouched():
    """With no glossary mounted, only emoji get protected; words pass through."""
    with (
        patch.object(server, "_TERMS_ANY_CASE_RE", None),
        patch.object(server, "_TERMS_EXACT_CASE_RE", None),
    ):
        # pylint: disable=protected-access
        protected, found = server._protect_verbatim("the Beastmaster leads")
    assert protected == "the Beastmaster leads"
    assert found == []
