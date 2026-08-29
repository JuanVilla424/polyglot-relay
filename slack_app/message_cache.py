"""Bounded in-memory cache of recent channel messages.

Slack's reaction_added event doesn't carry the message text, and since May
2025 conversations.history is limited to ~1 request/minute for new apps
distributed outside the Slack Marketplace -- far too slow to fetch on every
flag reaction. The bot already receives every message in the channels it's
been invited to, so remembering the recent ones locally makes reaction-driven
translation free; the history API stays as a rare last-resort fallback.
"""

from collections import OrderedDict

_MAX_MESSAGES = 5000

_messages: OrderedDict[tuple[str, str], str] = OrderedDict()


def remember(channel_id: str, ts: str, text: str) -> None:
    """Store a message's text, evicting the oldest entries past the size cap."""
    key = (channel_id, ts)
    _messages[key] = text
    _messages.move_to_end(key)
    while len(_messages) > _MAX_MESSAGES:
        _messages.popitem(last=False)


def recall(channel_id: str, ts: str) -> str | None:
    """Return the remembered text for a message, if it's still in the cache."""
    return _messages.get((channel_id, ts))


def clear() -> None:
    """Empty the cache (used by tests to isolate module-level state)."""
    _messages.clear()
