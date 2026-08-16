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
}


def to_flores(iso_code: str) -> str | None:
    """Map an ISO 639-1 code to its FLORES-200 equivalent, if supported."""
    return ISO_TO_FLORES.get(iso_code.lower())
