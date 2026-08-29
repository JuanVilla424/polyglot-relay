from slack_app import logic


def test_translation_blocks_lead_with_the_language_pair():
    """The first block names both languages so the reader knows what happened."""
    blocks = logic.translation_blocks("en", "es", "hello", "hola")
    header = blocks[0]["elements"][0]["text"]
    assert "*en* (English)" in header
    assert "*es* (Spanish)" in header


def test_translation_blocks_carry_translation_then_original():
    """The translation reads prominently as a section; the original follows
    de-emphasized after a divider, for side-by-side verification."""
    blocks = logic.translation_blocks("en", "es", "hello", "hola")
    section_texts = [b["text"]["text"] for b in blocks if b["type"] == "section"]
    assert section_texts == ["hola"]
    assert any(b["type"] == "divider" for b in blocks)
    context_texts = [
        element["text"]
        for block in blocks
        if block["type"] == "context"
        for element in block["elements"]
    ]
    assert any(text == "Original: hello" for text in context_texts)


def test_translation_blocks_split_a_long_translation_instead_of_truncating():
    """A translation past Slack's per-section cap splits across sections with
    every character preserved -- chunked, never cut."""
    long_translation = "x" * 7000
    blocks = logic.translation_blocks("en", "es", "hi", long_translation)
    section_texts = [b["text"]["text"] for b in blocks if b["type"] == "section"]
    assert len(section_texts) == 3
    assert "".join(section_texts) == long_translation


def test_translation_blocks_split_a_long_original_too():
    """The original is chunked by the same rule, at the context-block limit."""
    long_original = "y" * 4500
    blocks = logic.translation_blocks("en", "es", long_original, "ok")
    context_texts = [
        element["text"]
        for block in blocks
        if block["type"] == "context"
        for element in block["elements"]
    ]
    original_parts = [text for text in context_texts if "→" not in text]
    assert original_parts[0].startswith("Original: ")
    rejoined = original_parts[0][len("Original: ") :] + "".join(original_parts[1:])
    assert rejoined == long_original


def test_translation_blocks_name_unknown_codes_by_the_code_itself():
    """A code without a display name still renders, as the bare code."""
    blocks = logic.translation_blocks("xx", "yy", "a", "b")
    header = blocks[0]["elements"][0]["text"]
    assert "*xx* (xx)" in header
    assert "*yy* (yy)" in header
