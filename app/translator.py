import httpx

from app.config import LIBRETRANSLATE_URL


async def translate(text: str, target_lang: str) -> tuple[str, str]:
    """Translate text into target_lang, auto-detecting the source language.

    Returns (translated_text, detected_source_lang_code).
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{LIBRETRANSLATE_URL}/translate",
            json={"q": text, "source": "auto", "target": target_lang, "format": "text"},
        )
        response.raise_for_status()
        data = response.json()
        detected = data.get("detectedLanguage", {}).get("language", "")
        return data["translatedText"], detected


async def list_languages() -> list[dict]:
    """Return LibreTranslate's raw /languages payload (code, name, targets)."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(f"{LIBRETRANSLATE_URL}/languages")
        response.raise_for_status()
        return response.json()
