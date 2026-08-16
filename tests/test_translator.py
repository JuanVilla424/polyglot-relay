import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app import translator


def _mock_client(response):
    client = AsyncMock()
    client.post.return_value = response
    client.get.return_value = response
    client.__aenter__.return_value = client
    return client


def test_translate_returns_text_and_detected_language():
    """Happy path: translatedText and detectedLanguage.language are parsed out."""
    response = MagicMock()
    response.json.return_value = {
        "translatedText": "Hola",
        "detectedLanguage": {"confidence": 98, "language": "en"},
    }
    client = _mock_client(response)

    with patch("app.translator.httpx.AsyncClient", return_value=client):
        translated, detected = asyncio.run(translator.translate("Hello", "es"))

    assert translated == "Hola"
    assert detected == "en"
    response.raise_for_status.assert_called_once()


def test_translate_handles_missing_detected_language():
    """Non-auto-detect responses omit detectedLanguage; we shouldn't crash."""
    response = MagicMock()
    response.json.return_value = {"translatedText": "Hola"}
    client = _mock_client(response)

    with patch("app.translator.httpx.AsyncClient", return_value=client):
        translated, detected = asyncio.run(translator.translate("Hello", "es"))

    assert translated == "Hola"
    assert detected == ""


def test_list_languages_returns_raw_payload():
    """list_languages() passes the /languages JSON through unmodified."""
    response = MagicMock()
    response.json.return_value = [{"code": "en", "name": "English"}]
    client = _mock_client(response)

    with patch("app.translator.httpx.AsyncClient", return_value=client):
        result = asyncio.run(translator.list_languages())

    assert result == [{"code": "en", "name": "English"}]
