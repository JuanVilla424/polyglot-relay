from core.lang_codes import (
    FLAG_TO_ISO,
    ISO_TO_FLAG,
    ISO_TO_FLORES,
    ISO_TO_NAME,
    LANGUAGE_COLORS,
    color_for,
    flag_to_slack_emoji,
    slack_emoji_to_flag,
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


def test_flag_to_iso_recognizes_a_countrys_own_flag_not_just_the_representative_one():
    """Real report: many members react with their own country's flag (e.g. a
    Mexican reacting with the Mexico flag) instead of the one representative
    flag ISO_TO_FLAG uses for Spanish (Spain) -- both must resolve to "es".
    """
    assert FLAG_TO_ISO["🇲🇽"] == "es"
    assert FLAG_TO_ISO["🇦🇷"] == "es"
    assert FLAG_TO_ISO["🇨🇴"] == "es"
    assert FLAG_TO_ISO["🇧🇷"] == "pt"
    assert FLAG_TO_ISO["🇺🇸"] == "en"


def test_flag_to_iso_still_recognizes_every_representative_flag():
    """Expanding FLAG_TO_ISO with extra country flags must not drop the
    original one-flag-per-language entries ISO_TO_FLAG still relies on.
    """
    for iso, flag in ISO_TO_FLAG.items():
        assert FLAG_TO_ISO[flag] == iso


def test_iso_to_flag_stays_one_flag_per_language():
    """The outgoing "add these reactions" side is deliberately unchanged --
    a message should never get spammed with a dozen near-duplicate flags.
    """
    assert len(ISO_TO_FLAG) == len(set(ISO_TO_FLAG.values()))


def test_slack_emoji_to_flag_derives_the_unicode_flag():
    """Slack reports emoji by name; the Unicode flag is pure arithmetic away."""
    assert slack_emoji_to_flag("flag-co") == "🇨🇴"
    assert slack_emoji_to_flag("flag-es") == "🇪🇸"


def test_slack_emoji_to_flag_accepts_slacks_bare_short_names():
    """Slack's canonical name for a few classic flags is the bare country code
    ("us", "gb", ...), with "flag-xx" as the alias -- both must resolve."""
    assert slack_emoji_to_flag("us") == "🇺🇸"
    assert slack_emoji_to_flag("gb") == "🇬🇧"


def test_slack_emoji_to_flag_rejects_non_flag_names():
    """Anything that isn't two ASCII letters (after the optional prefix) is not a flag."""
    assert slack_emoji_to_flag("thumbsup") is None
    assert slack_emoji_to_flag("flag-") is None
    assert slack_emoji_to_flag("") is None


def test_flag_to_slack_emoji_round_trips_every_known_flag():
    """Every flag FLAG_TO_ISO understands survives the Unicode -> name -> Unicode trip."""
    for flag in FLAG_TO_ISO:
        name = flag_to_slack_emoji(flag)
        assert name is not None
        assert slack_emoji_to_flag(name) == flag


def test_flag_to_slack_emoji_rejects_non_flags():
    """A non-flag emoji has no Slack flag name."""
    assert flag_to_slack_emoji("🎉") is None
