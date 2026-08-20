"""Self-hosted NLLB-200 translation service, served over a small REST API."""

import re
import threading
from collections import defaultdict
from pathlib import Path

import ctranslate2
import transformers
from fastapi import FastAPI
from pydantic import BaseModel

MODEL_NAME = "facebook/nllb-200-distilled-600M"
MODEL_DIR = Path("/models/nllb-200-distilled-600M-int8")

# Safety net for a single very long line: scale the output-token budget with the
# input instead of relying on ctranslate2's fixed 256-token default.
_MIN_DECODING_LENGTH = 256
_DECODING_LENGTH_MULTIPLIER = 6
_MAX_DECODING_LENGTH = 2048

# NLLB isn't markdown-aware: a short line like "### Why" gets its heading marker
# corrupted or dropped inconsistently per target language. Strip these off before
# translating and reattach them untouched afterwards.
_HEADER_RE = re.compile(r"^(#{1,6}\s+)")
# Zero-width space/joiner/BOM (U+200B/U+200C/U+200D/U+FEFF) commonly precede an
# emoji as residue from copy-pasting rich text (e.g. from a notes app or wiki) --
# swallow them as part of the same match so they travel with their emoji instead
# of being left behind to confuse the tokenizer on their own.
_INVISIBLE_PREFIX_CHARS = "".join(
    chr(code_point) for code_point in (0x200B, 0x200C, 0x200D, 0xFEFF)
)
# Not anchored: an emoji anywhere in a sentence -- not just as a line prefix --
# hits the tokenizer raw and comes back as a literal <unk> if it's not in NLLB's
# vocabulary (true of most flags: they're regional-indicator pairs, a huge
# combinatorial space the model never saw enough of in training). No trailing
# \s* here (unlike a pure prefix-strip) -- consuming a real space in the middle
# of a sentence would glue the placeholder to the next word.
_EMOJI_RE = re.compile(
    f"[{_INVISIBLE_PREFIX_CHARS}]*"
    "[\U0001f1e6-\U0001f1ff\U00002600-\U000027bf\U0001f300-\U0001faff️]+"
)
_EMOJI_PLACEHOLDER_PREFIX = "xEMOJIx"
_EMOJI_PLACEHOLDER_SUFFIX = "x"

# NLLB also stops early mid-sentence when a single line packs more than one
# sentence together (very common in prose without a line break per sentence) —
# split after ./!/? + space, only when followed by a capital letter (avoids
# splitting on things like "3.5" or an abbreviation followed by lowercase).
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-ZÀ-Ý])")

# Typographic punctuation (smart quotes, em/en dash — common from iOS/macOS
# autocorrect) tokenizes as <unk> in NLLB's vocabulary; the plain ASCII form
# doesn't. Ellipsis ("…") is deliberately not included: it tokenizes fine.
_PUNCTUATION_NORMALIZATION = str.maketrans(
    {
        "—": "-",
        "–": "-",
        "“": '"',
        "”": '"',
        "‘": "'",
        "’": "'",
    }
)

app = FastAPI()
_lock = threading.Lock()
_translator: ctranslate2.Translator | None = None
_tokenizers: dict[str, transformers.PreTrainedTokenizerBase] = {}


def _ensure_model() -> None:
    """Convert the official Meta NLLB-200 weights to CTranslate2 int8 once."""
    if MODEL_DIR.exists():
        return
    converter = ctranslate2.converters.TransformersConverter(MODEL_NAME)
    converter.convert(str(MODEL_DIR), quantization="int8")


def _get_translator() -> ctranslate2.Translator:
    global _translator  # pylint: disable=global-statement
    if _translator is None:
        with _lock:
            if _translator is None:
                _ensure_model()
                _translator = ctranslate2.Translator(str(MODEL_DIR), device="cpu")
    return _translator


def _get_tokenizer(src_lang: str) -> transformers.PreTrainedTokenizerBase:
    if src_lang not in _tokenizers:
        with _lock:
            if src_lang not in _tokenizers:
                _tokenizers[src_lang] = transformers.AutoTokenizer.from_pretrained(
                    MODEL_NAME, src_lang=src_lang
                )
    return _tokenizers[src_lang]


class TranslateRequest(BaseModel):
    """Body for POST /translate: text plus explicit FLORES-200 source/target codes."""

    q: str
    source: str
    target: str


class TranslateResponse(BaseModel):
    """Body returned by POST /translate."""

    translatedText: str


def _split_header_prefix(line: str) -> tuple[str, str]:
    """Pull a markdown heading marker off a line.

    Returns (prefix, rest) — prefix is reattached untouched after translation,
    rest is what actually gets sent to the model.
    """
    header_match = _HEADER_RE.match(line)
    if header_match:
        return header_match.group(0), line[header_match.end() :]
    return "", line


def _split_into_sentences(text: str) -> list[str]:
    """Split text into sentences — NLLB stops generating after the first one
    when a line packs more than one together, silently dropping the rest.
    """
    return _SENTENCE_RE.split(text)


def _protect_emoji(text: str) -> tuple[str, list[str]]:
    """Replace every emoji anywhere in text with a numbered placeholder.

    Plain ASCII survives translation intact (confirmed empirically across
    several target languages), unlike the emoji itself, which the model
    doesn't have a token for and turns into a literal <unk>. Returns the
    placeholder-substituted text plus the emoji found, in order, so they can
    be put back after decoding.
    """
    found: list[str] = []

    def _replace(match: re.Match) -> str:
        found.append(match.group(0))
        return f"{_EMOJI_PLACEHOLDER_PREFIX}{len(found) - 1}{_EMOJI_PLACEHOLDER_SUFFIX}"

    return _EMOJI_RE.sub(_replace, text), found


def _restore_emoji(text: str, found: list[str]) -> str:
    """Put each emoji back where its placeholder from _protect_emoji ended up."""
    for i, emoji in enumerate(found):
        text = text.replace(f"{_EMOJI_PLACEHOLDER_PREFIX}{i}{_EMOJI_PLACEHOLDER_SUFFIX}", emoji)
    return text


def _prepare_lines(text: str) -> tuple[dict[int, str], dict[int, list[str]]]:
    """Split text into lines, then each non-blank line into sentences.

    Returns (prefixes, sentences_by_line) — prefixes holds each line's stripped
    markdown heading marker (reattached untouched later), sentences_by_line
    only has entries for lines that actually have translatable content.
    """
    prefixes: dict[int, str] = {}
    sentences_by_line: dict[int, list[str]] = {}
    for i, line in enumerate(text.split("\n")):
        if not line.strip():
            continue
        prefix, rest = _split_header_prefix(line)
        if not rest.strip():
            continue
        prefixes[i] = prefix
        sentences_by_line[i] = [s for s in _split_into_sentences(rest) if s.strip()]
    return prefixes, sentences_by_line


def _build_segments(sentences_by_line: dict[int, list[str]]) -> list[tuple[int, str, list[str]]]:
    """Normalize punctuation and protect emoji in every sentence, flattened for batching.

    Each entry is (line_index, text ready for the tokenizer, emoji found in it).
    """
    segments = []
    for i, sentences in sentences_by_line.items():
        for sentence in sentences:
            normalized = sentence.translate(_PUNCTUATION_NORMALIZATION)
            protected, found_emoji = _protect_emoji(normalized)
            segments.append((i, protected, found_emoji))
    return segments


def _decode_translations(
    tokenizer: transformers.PreTrainedTokenizerBase,
    flat_segments: list[tuple[int, str, list[str]]],
    results: list,
) -> dict[int, list[str]]:
    """Decode each translated segment and restore its emoji, grouped back by line."""
    translated_by_line: dict[int, list[str]] = defaultdict(list)
    for (line_index, _, found_emoji), result in zip(flat_segments, results):
        target_tokens = result.hypotheses[0][1:]
        decoded = tokenizer.decode(tokenizer.convert_tokens_to_ids(target_tokens))
        translated_by_line[line_index].append(_restore_emoji(decoded, found_emoji))
    return translated_by_line


@app.post("/translate", response_model=TranslateResponse)
def translate(req: TranslateRequest) -> TranslateResponse:
    """Translate q from the FLORES-200 source code to the target code.

    NLLB is a sentence-level model: a long multi-section message (headers, blank
    lines, lists) makes it stop generating early, well before any decoding-length
    cap — and the same thing happens within a single line when it packs more than
    one sentence together. Translating line by line, and sentence by sentence
    within each line, keeps every call short enough for the model to actually
    finish. Protecting a markdown heading marker per line, and any emoji anywhere
    in each sentence, keeps them from being corrupted in the process, and
    normalizing smart punctuation to ASCII avoids <unk> tokens for those too.
    """
    translator = _get_translator()
    tokenizer = _get_tokenizer(req.source)

    prefixes, sentences_by_line = _prepare_lines(req.q)
    if not sentences_by_line:
        return TranslateResponse(translatedText=req.q)
    flat_segments = _build_segments(sentences_by_line)

    batch = [
        tokenizer.convert_ids_to_tokens(tokenizer.encode(segment))
        for _, segment, _ in flat_segments
    ]
    max_decoding_length = min(
        _MAX_DECODING_LENGTH,
        max(
            _MIN_DECODING_LENGTH, max(len(tokens) for tokens in batch) * _DECODING_LENGTH_MULTIPLIER
        ),
    )
    results = translator.translate_batch(
        batch,
        target_prefix=[[req.target]] * len(batch),
        max_decoding_length=max_decoding_length,
    )

    translated_by_line = _decode_translations(tokenizer, flat_segments, results)

    translated_lines = req.q.split("\n")
    for i in sentences_by_line:
        translated_lines[i] = prefixes[i] + " ".join(translated_by_line[i])

    return TranslateResponse(translatedText="\n".join(translated_lines))


@app.get("/health")
def health() -> dict:
    """Report liveness immediately; model conversion/loading happens lazily."""
    return {"status": "ready" if MODEL_DIR.exists() else "converting"}
