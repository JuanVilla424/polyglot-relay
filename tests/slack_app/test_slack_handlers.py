import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from slack_sdk.errors import SlackApiError

from slack_app import config, handlers, message_cache, storage


@pytest.fixture(autouse=True)
def _fresh_cache():
    """The message cache is module-level state; isolate it per test."""
    message_cache.clear()
    yield
    message_cache.clear()


def _isolate_storage(monkeypatch, tmp_path):
    """Point the preference store at a throwaway directory."""
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "USER_LANGUAGES_PATH", tmp_path / "user_languages.json")


def _flag_reaction_event(reaction="flag-es", user="U1", channel="C1", ts="1.0"):
    return {
        "reaction": reaction,
        "user": user,
        "item": {"type": "message", "channel": channel, "ts": ts},
    }


def test_message_event_caches_plain_user_messages():
    """Every plain channel message lands in the cache for later reactions."""
    asyncio.run(handlers.handle_message_event({"channel": "C1", "ts": "1.0", "text": "hello"}))
    assert message_cache.recall("C1", "1.0") == "hello"


def test_message_event_ignores_bot_and_subtyped_messages():
    """Bot posts and subtyped events (edits, joins, ...) never enter the cache --
    the same bot-loop guard as the Discord adapter's author.bot check."""
    asyncio.run(
        handlers.handle_message_event({"channel": "C1", "ts": "1.0", "text": "x", "bot_id": "B1"})
    )
    asyncio.run(
        handlers.handle_message_event(
            {"channel": "C1", "ts": "2.0", "text": "x", "subtype": "message_changed"}
        )
    )
    assert message_cache.recall("C1", "1.0") is None
    assert message_cache.recall("C1", "2.0") is None


def test_reaction_with_a_non_flag_emoji_is_ignored():
    """Only flag emoji trigger translation; anything else is someone else's reaction."""
    client = AsyncMock()
    asyncio.run(handlers.handle_reaction_added(_flag_reaction_event(reaction="thumbsup"), client))
    client.chat_postEphemeral.assert_not_called()


def test_flag_reaction_translates_the_cached_message_ephemerally():
    """The happy path: cached text, flag reaction, private translation to the reactor."""
    message_cache.remember("C1", "1.0", "hello world")
    client = AsyncMock()

    with patch("core.translator.translate", AsyncMock(return_value=("hola mundo", "en"))):
        asyncio.run(handlers.handle_reaction_added(_flag_reaction_event(), client))

    kwargs = client.chat_postEphemeral.call_args.kwargs
    assert kwargs["channel"] == "C1"
    assert kwargs["user"] == "U1"
    assert kwargs["text"] == "hola mundo"
    assert kwargs["blocks"] is not None
    client.conversations_history.assert_not_called()


def test_flag_reaction_cache_miss_falls_back_to_a_single_history_fetch():
    """A message from before the bot started isn't cached; one history call
    (the rate-limited API, hence last resort) recovers it."""
    client = AsyncMock()
    client.conversations_history.return_value = {"messages": [{"ts": "1.0", "text": "hello"}]}

    with patch("core.translator.translate", AsyncMock(return_value=("hola", "en"))):
        asyncio.run(handlers.handle_reaction_added(_flag_reaction_event(), client))

    client.conversations_history.assert_awaited_once()
    assert client.chat_postEphemeral.call_args.kwargs["text"] == "hola"


def test_flag_reaction_reports_too_old_when_history_cannot_recover_it():
    """Cache miss plus a failed/rate-limited history fetch degrades to an
    explanation, never a silent nothing."""
    client = AsyncMock()
    client.conversations_history.side_effect = SlackApiError("ratelimited", {"ok": False})

    translate = AsyncMock()
    with patch("core.translator.translate", translate):
        asyncio.run(handlers.handle_reaction_added(_flag_reaction_event(), client))

    translate.assert_not_awaited()
    assert "too old" in client.chat_postEphemeral.call_args.kwargs["text"]


def test_flag_reaction_on_a_message_already_in_that_language_says_so():
    """Detected == target: tell the reactor instead of posting a no-op translation."""
    message_cache.remember("C1", "1.0", "hola ya en español")
    client = AsyncMock()

    with patch("core.translator.translate", AsyncMock(return_value=("hola ya en español", "es"))):
        asyncio.run(handlers.handle_reaction_added(_flag_reaction_event(), client))

    assert "already in `es`" in client.chat_postEphemeral.call_args.kwargs["text"]


def test_reaction_on_a_non_message_item_is_ignored():
    """Reactions on files or file comments have no text to translate."""
    client = AsyncMock()
    event = {"reaction": "flag-es", "user": "U1", "item": {"type": "file", "file": "F1"}}
    asyncio.run(handlers.handle_reaction_added(event, client))
    client.chat_postEphemeral.assert_not_called()


def _shortcut_body(text="hello", team="T1", user="U1", channel="C1"):
    return {
        "message": {"text": text},
        "channel": {"id": channel},
        "user": {"id": user},
        "team": {"id": team},
    }


def test_shortcut_translates_to_the_requesters_stored_language(monkeypatch, tmp_path):
    """The Translate shortcut honors /polyglot-lang over the deployment default."""
    _isolate_storage(monkeypatch, tmp_path)
    storage.set_user_language("T1", "U1", "fr")
    ack = AsyncMock()
    client = AsyncMock()

    translate = AsyncMock(return_value=("bonjour", "en"))
    with patch("core.translator.translate", translate):
        asyncio.run(handlers.handle_translate_shortcut(ack, _shortcut_body(), client))

    ack.assert_awaited_once()
    translate.assert_awaited_once_with("hello", "fr")


def test_shortcut_falls_back_to_the_deployment_default_language(monkeypatch, tmp_path):
    """No stored preference: DEFAULT_TARGET_LANGUAGE decides, mirroring the
    Discord context menu's fallback."""
    _isolate_storage(monkeypatch, tmp_path)
    ack = AsyncMock()
    client = AsyncMock()

    translate = AsyncMock(return_value=("hola", "en"))
    with patch("core.translator.translate", translate):
        asyncio.run(handlers.handle_translate_shortcut(ack, _shortcut_body(), client))

    translate.assert_awaited_once_with("hello", config.DEFAULT_TARGET_LANGUAGE)


def test_shortcut_with_no_text_says_nothing_to_translate():
    """A media-only message translates to nothing; say so instead of failing."""
    ack = AsyncMock()
    client = AsyncMock()
    asyncio.run(handlers.handle_translate_shortcut(ack, _shortcut_body(text=""), client))
    assert "Nothing to translate" in client.chat_postEphemeral.call_args.kwargs["text"]


def test_polyglot_lang_sets_a_supported_code(monkeypatch, tmp_path):
    """/polyglot-lang es stores the preference, case-insensitively."""
    _isolate_storage(monkeypatch, tmp_path)
    ack = AsyncMock()
    client = AsyncMock()

    asyncio.run(
        handlers.handle_polyglot_lang(ack, {"text": "ES", "team_id": "T1", "user_id": "U1"}, client)
    )

    assert storage.get_user_language("T1", "U1") == "es"
    assert "`es`" in ack.call_args.args[0]


def test_polyglot_lang_rejects_an_unsupported_code(monkeypatch, tmp_path):
    """An unknown code stores nothing and points at /polyglot-lang list."""
    _isolate_storage(monkeypatch, tmp_path)
    ack = AsyncMock()
    client = AsyncMock()

    asyncio.run(
        handlers.handle_polyglot_lang(ack, {"text": "xx", "team_id": "T1", "user_id": "U1"}, client)
    )

    assert storage.get_user_language("T1", "U1") is None
    assert "isn't a supported language code" in ack.call_args.args[0]


def test_polyglot_lang_clear_removes_the_preference(monkeypatch, tmp_path):
    """/polyglot-lang clear leaves the user with no stored language."""
    _isolate_storage(monkeypatch, tmp_path)
    storage.set_user_language("T1", "U1", "es")
    ack = AsyncMock()
    client = AsyncMock()

    asyncio.run(
        handlers.handle_polyglot_lang(
            ack, {"text": "clear", "team_id": "T1", "user_id": "U1"}, client
        )
    )

    assert storage.get_user_language("T1", "U1") is None


def test_polyglot_lang_list_names_the_supported_codes():
    """/polyglot-lang list shows every supported code with its language name."""
    ack = AsyncMock()
    client = AsyncMock()

    asyncio.run(
        handlers.handle_polyglot_lang(
            ack, {"text": "list", "team_id": "T1", "user_id": "U1"}, client
        )
    )

    listing = ack.call_args.args[0]
    assert "`es` — Spanish" in listing
    assert "`en` — English" in listing


def test_post_ephemeral_swallows_delivery_failures():
    """The bot may lack access (e.g. never invited to a private channel) --
    that's a log line, never a crash in an event handler."""
    client = AsyncMock()
    client.chat_postEphemeral.side_effect = SlackApiError("channel_not_found", {"ok": False})
    # pylint: disable-next=protected-access
    asyncio.run(handlers._post_ephemeral(client, "C1", "U1", "hi"))
