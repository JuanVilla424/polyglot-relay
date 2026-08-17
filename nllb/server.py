"""Self-hosted NLLB-200 translation service, served over a small REST API."""

import threading
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


@app.post("/translate", response_model=TranslateResponse)
def translate(req: TranslateRequest) -> TranslateResponse:
    """Translate q from the FLORES-200 source code to the target code.

    NLLB is a sentence-level model: a long multi-section message (headers, blank
    lines, lists) makes it stop generating early, well before any decoding-length
    cap. Translating line by line and rejoining keeps each call short enough for
    the model to actually finish.
    """
    translator = _get_translator()
    tokenizer = _get_tokenizer(req.source)

    lines = req.q.split("\n")
    translatable = [i for i, line in enumerate(lines) if line.strip()]
    if not translatable:
        return TranslateResponse(translatedText=req.q)

    batch = [tokenizer.convert_ids_to_tokens(tokenizer.encode(lines[i])) for i in translatable]
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

    translated_lines = list(lines)
    for index, result in zip(translatable, results):
        target_tokens = result.hypotheses[0][1:]
        translated_lines[index] = tokenizer.decode(tokenizer.convert_tokens_to_ids(target_tokens))

    return TranslateResponse(translatedText="\n".join(translated_lines))


@app.get("/health")
def health() -> dict:
    """Report liveness immediately; model conversion/loading happens lazily."""
    return {"status": "ready" if MODEL_DIR.exists() else "converting"}
