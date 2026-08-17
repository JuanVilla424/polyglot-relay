"""ISO 639-1 <-> FLORES-200 mapping for the languages this bot supports.

NLLB-200 uses FLORES-200 codes (e.g. "eng_Latn"); LibreTranslate's /detect
endpoint and Discord users both use plain ISO 639-1 codes (e.g. "en").
Covers common world languages, not the full FLORES-200 set of 200 codes.
"""

ISO_TO_FLORES = {
    "en": "eng_Latn",
    "es": "spa_Latn",
    "fr": "fra_Latn",
    "de": "deu_Latn",
    "pt": "por_Latn",
    "it": "ita_Latn",
    "ja": "jpn_Jpan",
    "ko": "kor_Hang",
    "zh": "zho_Hans",
    "ru": "rus_Cyrl",
    "ar": "arb_Arab",
    "hi": "hin_Deva",
    "nl": "nld_Latn",
    "pl": "pol_Latn",
    "tr": "tur_Latn",
    "vi": "vie_Latn",
    "th": "tha_Thai",
    "id": "ind_Latn",
    "sv": "swe_Latn",
    "el": "ell_Grek",
    "he": "heb_Hebr",
    "uk": "ukr_Cyrl",
    "cs": "ces_Latn",
    "ro": "ron_Latn",
    "hu": "hun_Latn",
    "fi": "fin_Latn",
    "da": "dan_Latn",
    "no": "nob_Latn",
    "bn": "ben_Beng",
    "ca": "cat_Latn",
}

ISO_TO_NAME = {
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "pt": "Portuguese",
    "it": "Italian",
    "ja": "Japanese",
    "ko": "Korean",
    "zh": "Chinese",
    "ru": "Russian",
    "ar": "Arabic",
    "hi": "Hindi",
    "nl": "Dutch",
    "pl": "Polish",
    "tr": "Turkish",
    "vi": "Vietnamese",
    "th": "Thai",
    "id": "Indonesian",
    "sv": "Swedish",
    "el": "Greek",
    "he": "Hebrew",
    "uk": "Ukrainian",
    "cs": "Czech",
    "ro": "Romanian",
    "hu": "Hungarian",
    "fi": "Finnish",
    "da": "Danish",
    "no": "Norwegian",
    "bn": "Bengali",
    "ca": "Catalan",
}


def to_flores(iso_code: str) -> str | None:
    """Map an ISO 639-1 code to its FLORES-200 equivalent, if supported."""
    return ISO_TO_FLORES.get(iso_code.lower())


# One representative country flag per supported language, used by the
# "reactions" delivery mode (a flag reaction on a message triggers an on-demand
# translation to that language). Catalan has no exact country flag in the
# Unicode regional-indicator standard, so it's left out — still available
# through every other delivery mode.
ISO_TO_FLAG = {
    "en": "🇬🇧",
    "es": "🇪🇸",
    "fr": "🇫🇷",
    "de": "🇩🇪",
    "pt": "🇵🇹",
    "it": "🇮🇹",
    "ja": "🇯🇵",
    "ko": "🇰🇷",
    "zh": "🇨🇳",
    "ru": "🇷🇺",
    "ar": "🇸🇦",
    "hi": "🇮🇳",
    "nl": "🇳🇱",
    "pl": "🇵🇱",
    "tr": "🇹🇷",
    "vi": "🇻🇳",
    "th": "🇹🇭",
    "id": "🇮🇩",
    "sv": "🇸🇪",
    "el": "🇬🇷",
    "he": "🇮🇱",
    "uk": "🇺🇦",
    "cs": "🇨🇿",
    "ro": "🇷🇴",
    "hu": "🇭🇺",
    "fi": "🇫🇮",
    "da": "🇩🇰",
    "no": "🇳🇴",
    "bn": "🇧🇩",
}

FLAG_TO_ISO = {flag: iso for iso, flag in ISO_TO_FLAG.items()}


# Validated categorical palette (8 slots, fixed order, CVD-safe adjacent pairs),
# dark-surface steps since Discord's embed panel reads dark in both client themes.
LANGUAGE_COLORS = [
    0x3987E5,  # blue
    0xD95926,  # orange
    0x199E70,  # aqua
    0xC98500,  # yellow
    0xD55181,  # magenta
    0x008300,  # green
    0x9085E9,  # violet
    0xE66767,  # red
]

_LANGUAGE_ORDER = list(ISO_TO_FLORES)


def color_for(iso_code: str) -> int:
    """Deterministic color per language code: fixed slot order, cycled past 8 codes.

    Identity is never color-alone (each embed also shows the code + name as
    text) so reuse past the 8th language is an acceptable, documented trade-off.
    """
    index = _LANGUAGE_ORDER.index(iso_code) if iso_code in _LANGUAGE_ORDER else 0
    return LANGUAGE_COLORS[index % len(LANGUAGE_COLORS)]
