import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core import translator


def _response(payload):
    response = MagicMock()
    response.json.return_value = payload
    return response


def _mock_client(*responses):
    client = AsyncMock()
    client.post.side_effect = list(responses)
    client.get.side_effect = list(responses)
    client.__aenter__.return_value = client
    return client


def test_detect_language_returns_iso_code():
    """detect_language() reads LibreTranslate's [{confidence, language}] shape."""
    client = _mock_client(_response([{"confidence": 98, "language": "en"}]))

    with patch("core.translator.httpx.AsyncClient", return_value=client):
        detected = asyncio.run(translator.detect_language("Hello"))

    assert detected == "en"


def test_translate_detects_then_calls_nllb_with_flores_codes():
    """translate() chains LibreTranslate detection into an NLLB call with FLORES-200 codes."""
    detect_response = _response([{"confidence": 90, "language": "en"}])
    translate_response = _response({"translatedText": "Hola"})
    client = _mock_client(detect_response, translate_response)

    with patch("core.translator.httpx.AsyncClient", return_value=client):
        translated, detected = asyncio.run(translator.translate("Hello", "es"))

    assert translated == "Hola"
    assert detected == "en"

    detect_call, translate_call = client.post.call_args_list
    assert detect_call.args[0].endswith("/detect")
    assert translate_call.args[0].endswith("/translate")
    assert translate_call.kwargs["json"] == {
        "q": "Hello",
        "source": "eng_Latn",
        "target": "spa_Latn",
    }


def test_translate_raises_for_unsupported_language():
    """No FLORES-200 mapping should fail loudly, not silently mistranslate."""
    client = _mock_client(_response([{"confidence": 90, "language": "xx"}]))

    with patch("core.translator.httpx.AsyncClient", return_value=client):
        with pytest.raises(translator.UnsupportedLanguageError):
            asyncio.run(translator.translate("???", "es"))


def test_list_languages_returns_raw_payload():
    """list_languages() passes LibreTranslate's /languages JSON through unmodified."""
    client = _mock_client(_response([{"code": "en", "name": "English"}]))

    with patch("core.translator.httpx.AsyncClient", return_value=client):
        result = asyncio.run(translator.list_languages())

    assert result == [{"code": "en", "name": "English"}]
