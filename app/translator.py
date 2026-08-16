import httpx

from app.config import LIBRETRANSLATE_URL, NLLB_URL
from app.lang_codes import to_flores


class UnsupportedLanguageError(Exception):
    """A detected or target language has no FLORES-200 mapping."""


async def detect_language(text: str) -> str:
    """Return the ISO 639-1 code LibreTranslate detects for text."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(f"{LIBRETRANSLATE_URL}/detect", json={"q": text})
        response.raise_for_status()
        return response.json()[0]["language"]


async def translate(text: str, target_lang: str) -> tuple[str, str]:
    """Translate text into target_lang, auto-detecting the source language.

    Detection stays on LibreTranslate (already deployed, fasttext-based);
    the actual translation runs on the self-hosted NLLB-200 service, which
    needs explicit FLORES-200 source/target codes instead of "auto".

    Returns (translated_text, detected_source_lang_code).
    """
    detected = await detect_language(text)

    source_flores = to_flores(detected)
    target_flores = to_flores(target_lang)
    if source_flores is None or target_flores is None:
        raise UnsupportedLanguageError(
            f"no FLORES-200 mapping for source={detected!r} or target={target_lang!r}"
        )

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{NLLB_URL}/translate",
            json={"q": text, "source": source_flores, "target": target_flores},
        )
        response.raise_for_status()
        return response.json()["translatedText"], detected


async def list_languages() -> list[dict]:
    """Return LibreTranslate's raw /languages payload (code, name, targets)."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(f"{LIBRETRANSLATE_URL}/languages")
        response.raise_for_status()
        return response.json()
