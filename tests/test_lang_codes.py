from app.lang_codes import ISO_TO_FLORES, ISO_TO_NAME, to_flores


def test_to_flores_maps_known_codes():
    """Known ISO 639-1 codes resolve to their FLORES-200 equivalent."""
    assert to_flores("es") == "spa_Latn"
    assert to_flores("en") == "eng_Latn"
    assert to_flores("ca") == "cat_Latn"


def test_to_flores_is_case_insensitive():
    """Users may type language codes in any case."""
    assert to_flores("ES") == "spa_Latn"


def test_to_flores_returns_none_for_unknown_code():
    """Unmapped codes return None instead of raising, letting callers decide."""
    assert to_flores("xx") is None


def test_every_flores_code_has_a_display_name():
    """/languages should never fall back to '?' for a code we actually support."""
    assert ISO_TO_FLORES.keys() == ISO_TO_NAME.keys()
