"""Build the ephemeral Block Kit responses the Slack adapter sends."""

from core.lang_codes import ISO_TO_NAME

# Slack caps a section block's mrkdwn text at 3000 characters -- long
# translations get split across as many blocks as they need, never truncated.
_SECTION_TEXT_LIMIT = 3000
# The original is shown in small context text after the translation; context
# elements have a lower practical limit than sections.
_CONTEXT_TEXT_LIMIT = 2000


def _chunk(text: str, limit: int) -> list[str]:
    """Split text into limit-sized pieces; a blank text still yields one piece."""
    return [text[i : i + limit] for i in range(0, len(text), limit)] or [""]


def translation_blocks(detected: str, target: str, original: str, translated: str) -> list[dict]:
    """One ephemeral payload: language header, the translation prominently,
    then the original in de-emphasized context text for side-by-side trust."""
    detected_name = ISO_TO_NAME.get(detected, detected)
    target_name = ISO_TO_NAME.get(target, target)
    blocks: list[dict] = [
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"*{detected}* ({detected_name}) → *{target}* ({target_name})",
                }
            ],
        }
    ]
    for part in _chunk(translated, _SECTION_TEXT_LIMIT):
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": part}})
    blocks.append({"type": "divider"})
    for index, part in enumerate(_chunk(original, _CONTEXT_TEXT_LIMIT)):
        label = "Original: " if index == 0 else ""
        blocks.append(
            {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": f"{label}{part}"}],
            }
        )
    return blocks
