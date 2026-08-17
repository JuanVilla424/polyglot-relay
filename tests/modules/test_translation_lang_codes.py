from app.modules.translation.lang_codes import (
    ISO_TO_FLORES,
    ISO_TO_NAME,
    LANGUAGE_COLORS,
    color_for,
    to_flores,
)


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


def test_color_for_returns_one_of_the_validated_palette_slots():
    """Every code maps to a real slot in the validated categorical palette."""
    assert color_for("es") in LANGUAGE_COLORS


def test_color_for_is_stable_for_the_same_code():
    """Color assignment doesn't depend on context, only on the code itself."""
    assert color_for("fr") == color_for("fr")


def test_color_for_unknown_code_still_returns_a_valid_color():
    """An unmapped code degrades to a real palette color rather than raising."""
    assert color_for("xx") in LANGUAGE_COLORS
