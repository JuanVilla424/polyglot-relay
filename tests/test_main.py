# pylint: disable=protected-access
# White-box tests deliberately reach into main.py's internal dispatcher.
import asyncio
import types
from unittest.mock import AsyncMock, MagicMock

import discord

from app import main as bot_main
from app import storage
from app.modules import checks


def _use_tmp_store(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    monkeypatch.setattr(storage, "ENABLED_MODULES_PATH", tmp_path / "enabled_modules.json")


def _set_bot_user_id(monkeypatch, user_id):
    """discord.Client.user is a read-only property; patch it at the class level."""
    monkeypatch.setattr(discord.Client, "user", property(lambda self: MagicMock(id=user_id)))


def _make_message(author_id, guild_id=1, author_is_bot=False):
    message = MagicMock()
    message.author.id = author_id
    message.author.bot = author_is_bot
    message.guild.id = guild_id
    return message


def _make_reaction_payload(user_id, guild_id):
    payload = MagicMock()
    payload.user_id = user_id
    payload.guild_id = guild_id
    return payload


def _make_fake_module(**handlers):
    """A module stand-in exposing only the handlers passed in (others are absent, not falsy)."""
    return types.SimpleNamespace(handlers=types.SimpleNamespace(**handlers))


def test_intents_enable_message_content():
    """Auto-translate needs the privileged message content intent enabled."""
    assert bot_main.intents.message_content is True


def test_client_and_tree_are_wired():
    """The command tree must be bound to the same client instance we run."""
    assert isinstance(bot_main.client, discord.Client)
    assert isinstance(bot_main.tree, discord.app_commands.CommandTree)
    assert bot_main.tree.client is bot_main.client


def test_commands_are_registered():
    """Every module's commands, plus the core commands, are on the shared tree."""
    names = {command.name for command in bot_main.tree.get_commands()}
    # core
    assert "polyglot-modules" in names
    assert "help" in names
    # translation module
    assert "setlanguage" in names
    assert "setbehavior" in names
    assert "Translate Message" in names
    assert "Retry Translation" in names
    # events module
    assert "createvent" in names
    assert "listevents" in names
    assert "Cancel Event" in names


def test_active_modules_defaults_to_translation_only(tmp_path, monkeypatch):
    """No /polyglot-modules ever run for this guild -> only translation (the built-in default)."""
    _use_tmp_store(tmp_path, monkeypatch)

    active = bot_main._active_modules(1)

    assert active == [bot_main.MODULES["translation"]]


def test_active_modules_includes_events_once_enabled(tmp_path, monkeypatch):
    """/polyglot-modules enable events adds it to the active list for that guild."""
    _use_tmp_store(tmp_path, monkeypatch)
    storage.set_module_enabled(1, "events", True)

    active = bot_main._active_modules(1)

    assert bot_main.MODULES["events"] in active


def test_active_modules_isolates_by_guild(tmp_path, monkeypatch):
    """Enabling events in one guild doesn't turn it on for another."""
    _use_tmp_store(tmp_path, monkeypatch)
    storage.set_module_enabled(1, "events", True)

    assert bot_main.MODULES["events"] not in bot_main._active_modules(2)


def test_on_message_ignores_bot_authors(tmp_path, monkeypatch):
    """Messages from other bots are never dispatched to any module."""
    _use_tmp_store(tmp_path, monkeypatch)
    handle_message = AsyncMock()
    monkeypatch.setattr(
        bot_main, "MODULES", {"fake": _make_fake_module(handle_message=handle_message)}
    )
    storage.set_module_enabled(1, "fake", True)
    message = _make_message(100, author_is_bot=True)

    asyncio.run(bot_main.on_message(message))

    handle_message.assert_not_awaited()


def test_on_message_ignores_messages_outside_a_guild(tmp_path, monkeypatch):
    """A DM (no guild) is never dispatched to any module."""
    _use_tmp_store(tmp_path, monkeypatch)
    handle_message = AsyncMock()
    monkeypatch.setattr(
        bot_main, "MODULES", {"fake": _make_fake_module(handle_message=handle_message)}
    )
    message = MagicMock()
    message.author.bot = False
    message.guild = None

    asyncio.run(bot_main.on_message(message))

    handle_message.assert_not_awaited()


def test_on_message_dispatches_to_every_active_modules_handler(tmp_path, monkeypatch):
    """Every module active in this guild that implements handle_message gets called."""
    _use_tmp_store(tmp_path, monkeypatch)
    handle_a = AsyncMock()
    handle_b = AsyncMock()
    monkeypatch.setattr(
        bot_main,
        "MODULES",
        {
            "a": _make_fake_module(handle_message=handle_a),
            "b": _make_fake_module(handle_message=handle_b),
        },
    )
    storage.set_module_enabled(1, "a", True)
    storage.set_module_enabled(1, "b", True)
    message = _make_message(100, guild_id=1)

    asyncio.run(bot_main.on_message(message))

    handle_a.assert_awaited_once_with(bot_main.client, message)
    handle_b.assert_awaited_once_with(bot_main.client, message)


def test_on_message_ignores_subject_members(tmp_path, monkeypatch):
    """A member carrying the quarantine role is never dispatched to any module --
    their messages don't get translated, counted, or otherwise amplified."""
    _use_tmp_store(tmp_path, monkeypatch)
    monkeypatch.setattr(checks, "SUBJECT_ROLE_ID", 555)
    handle_message = AsyncMock()
    monkeypatch.setattr(
        bot_main, "MODULES", {"fake": _make_fake_module(handle_message=handle_message)}
    )
    storage.set_module_enabled(1, "fake", True)
    message = _make_message(100, guild_id=1)
    message.author.roles = [MagicMock(id=555)]

    asyncio.run(bot_main.on_message(message))

    handle_message.assert_not_awaited()


def test_on_raw_reaction_add_ignores_subject_members(tmp_path, monkeypatch):
    """A quarantined member's reactions trigger nothing: no on-demand translation,
    no RSVP, no verification approval."""
    _use_tmp_store(tmp_path, monkeypatch)
    _set_bot_user_id(monkeypatch, 999)
    monkeypatch.setattr(checks, "SUBJECT_ROLE_ID", 555)
    handle_reaction_add = AsyncMock()
    monkeypatch.setattr(
        bot_main, "MODULES", {"fake": _make_fake_module(handle_reaction_add=handle_reaction_add)}
    )
    storage.set_module_enabled(1, "fake", True)
    payload = _make_reaction_payload(user_id=100, guild_id=1)
    payload.member.roles = [MagicMock(id=555)]

    asyncio.run(bot_main.on_raw_reaction_add(payload))

    handle_reaction_add.assert_not_awaited()


def test_on_raw_reaction_remove_ignores_subject_members(tmp_path, monkeypatch):
    """Reaction removals resolve the member through the guild cache (the raw
    payload carries no member on removals) and are gated the same way."""
    _use_tmp_store(tmp_path, monkeypatch)
    _set_bot_user_id(monkeypatch, 999)
    monkeypatch.setattr(checks, "SUBJECT_ROLE_ID", 555)
    handler = AsyncMock()
    monkeypatch.setattr(
        bot_main, "MODULES", {"fake": _make_fake_module(handle_reaction_remove=handler)}
    )
    storage.set_module_enabled(1, "fake", True)
    payload = _make_reaction_payload(user_id=100, guild_id=1)
    payload.member = None
    quarantined = MagicMock()
    quarantined.roles = [MagicMock(id=555)]
    guild = MagicMock()
    guild.get_member.return_value = quarantined
    monkeypatch.setattr(bot_main.client, "get_guild", MagicMock(return_value=guild), raising=False)

    asyncio.run(bot_main.on_raw_reaction_remove(payload))

    handler.assert_not_awaited()


def test_is_subject_false_when_unconfigured_or_memberless():
    """Unset SUBJECT_ROLE_ID or a missing/roleless member never quarantines anyone."""
    assert checks.is_subject(None) is False
    member = MagicMock()
    member.roles = [MagicMock(id=1)]
    assert checks.is_subject(member) is False  # SUBJECT_ROLE_ID unset in tests


def test_is_subject_matches_only_the_configured_role(monkeypatch):
    """True exactly when the member carries the configured quarantine role."""
    monkeypatch.setattr(checks, "SUBJECT_ROLE_ID", 555)
    marked = MagicMock()
    marked.roles = [MagicMock(id=1), MagicMock(id=555)]
    clean = MagicMock()
    clean.roles = [MagicMock(id=1)]

    assert checks.is_subject(marked) is True
    assert checks.is_subject(clean) is False


def test_on_message_skips_modules_without_a_message_handler(tmp_path, monkeypatch):
    """A module that doesn't implement handle_message (e.g. events) is silently skipped."""
    _use_tmp_store(tmp_path, monkeypatch)
    monkeypatch.setattr(bot_main, "MODULES", {"no_handler": _make_fake_module()})
    storage.set_module_enabled(1, "no_handler", True)
    message = _make_message(100, guild_id=1)

    asyncio.run(bot_main.on_message(message))  # must not raise


def test_on_message_skips_modules_disabled_for_this_guild(tmp_path, monkeypatch):
    """A module not enabled for this guild never receives the message."""
    _use_tmp_store(tmp_path, monkeypatch)
    handle_message = AsyncMock()
    monkeypatch.setattr(
        bot_main, "MODULES", {"extra": _make_fake_module(handle_message=handle_message)}
    )
    message = _make_message(100, guild_id=1)

    asyncio.run(bot_main.on_message(message))

    handle_message.assert_not_awaited()


def test_on_raw_reaction_add_ignores_the_bots_own_reaction(tmp_path, monkeypatch):
    """The bot's own reactions (flags, RSVP emojis) must never trigger a module's handler.

    Both translation and events add reactions automatically -- without this
    guard in the dispatcher, each would immediately re-trigger off its own
    reaction (explicit requirement, confirmed with a real production bug).
    """
    _use_tmp_store(tmp_path, monkeypatch)
    _set_bot_user_id(monkeypatch, 999)
    handle_reaction_add = AsyncMock()
    monkeypatch.setattr(
        bot_main, "MODULES", {"fake": _make_fake_module(handle_reaction_add=handle_reaction_add)}
    )
    payload = _make_reaction_payload(user_id=999, guild_id=1)

    asyncio.run(bot_main.on_raw_reaction_add(payload))

    handle_reaction_add.assert_not_awaited()


def test_on_raw_reaction_add_ignores_reactions_outside_a_guild(tmp_path, monkeypatch):
    """A reaction on a DM message (no guild) is never dispatched."""
    _use_tmp_store(tmp_path, monkeypatch)
    _set_bot_user_id(monkeypatch, 999)
    handle_reaction_add = AsyncMock()
    monkeypatch.setattr(
        bot_main, "MODULES", {"fake": _make_fake_module(handle_reaction_add=handle_reaction_add)}
    )
    payload = _make_reaction_payload(user_id=100, guild_id=None)

    asyncio.run(bot_main.on_raw_reaction_add(payload))

    handle_reaction_add.assert_not_awaited()


def test_on_raw_reaction_add_stops_at_the_first_module_that_claims_it(tmp_path, monkeypatch):
    """Once a module's handler returns True, no later module is even tried."""
    _use_tmp_store(tmp_path, monkeypatch)
    _set_bot_user_id(monkeypatch, 999)
    first = AsyncMock(return_value=True)
    second = AsyncMock(return_value=True)
    monkeypatch.setattr(
        bot_main,
        "MODULES",
        {
            "first": _make_fake_module(handle_reaction_add=first),
            "second": _make_fake_module(handle_reaction_add=second),
        },
    )
    storage.set_module_enabled(1, "first", True)
    storage.set_module_enabled(1, "second", True)
    payload = _make_reaction_payload(user_id=100, guild_id=1)

    asyncio.run(bot_main.on_raw_reaction_add(payload))

    first.assert_awaited_once()
    second.assert_not_awaited()


def test_on_raw_reaction_add_falls_through_to_the_next_module_if_unclaimed(tmp_path, monkeypatch):
    """A module returning False (didn't recognize the reaction) lets the next module try."""
    _use_tmp_store(tmp_path, monkeypatch)
    _set_bot_user_id(monkeypatch, 999)
    first = AsyncMock(return_value=False)
    second = AsyncMock(return_value=True)
    monkeypatch.setattr(
        bot_main,
        "MODULES",
        {
            "first": _make_fake_module(handle_reaction_add=first),
            "second": _make_fake_module(handle_reaction_add=second),
        },
    )
    storage.set_module_enabled(1, "first", True)
    storage.set_module_enabled(1, "second", True)
    payload = _make_reaction_payload(user_id=100, guild_id=1)

    asyncio.run(bot_main.on_raw_reaction_add(payload))

    first.assert_awaited_once()
    second.assert_awaited_once()


def test_on_raw_reaction_remove_ignores_the_bots_own_reaction(tmp_path, monkeypatch):
    """Same self-reaction guard applies to reaction removal."""
    _use_tmp_store(tmp_path, monkeypatch)
    _set_bot_user_id(monkeypatch, 999)
    handle_reaction_remove = AsyncMock()
    monkeypatch.setattr(
        bot_main,
        "MODULES",
        {"fake": _make_fake_module(handle_reaction_remove=handle_reaction_remove)},
    )
    storage.set_module_enabled(1, "fake", True)
    payload = _make_reaction_payload(user_id=999, guild_id=1)

    asyncio.run(bot_main.on_raw_reaction_remove(payload))

    handle_reaction_remove.assert_not_awaited()


def test_on_raw_reaction_remove_dispatches_to_a_claiming_module(tmp_path, monkeypatch):
    """A module implementing handle_reaction_remove gets the event."""
    _use_tmp_store(tmp_path, monkeypatch)
    _set_bot_user_id(monkeypatch, 999)
    handle_reaction_remove = AsyncMock(return_value=True)
    monkeypatch.setattr(
        bot_main,
        "MODULES",
        {"fake": _make_fake_module(handle_reaction_remove=handle_reaction_remove)},
    )
    storage.set_module_enabled(1, "fake", True)
    payload = _make_reaction_payload(user_id=100, guild_id=1)

    asyncio.run(bot_main.on_raw_reaction_remove(payload))

    handle_reaction_remove.assert_awaited_once_with(bot_main.client, payload)


def test_polyglot_modules_enables_a_module_for_the_guild(tmp_path, monkeypatch):
    """An admin can turn on a non-default module (e.g. events) for their server."""
    _use_tmp_store(tmp_path, monkeypatch)
    interaction = MagicMock()
    interaction.guild_id = 1
    interaction.response.send_message = AsyncMock()
    action = discord.app_commands.Choice(name="Enable", value="enable")
    module = discord.app_commands.Choice(name="Events", value="events")

    asyncio.run(bot_main.polyglot_modules.callback(interaction, action, module))

    assert storage.is_module_enabled(1, "events") is True


def test_polyglot_modules_reports_to_the_configured_log_channel(tmp_path, monkeypatch):
    """Real bug report: this command never reached the log channel other commands do."""
    _use_tmp_store(tmp_path, monkeypatch)
    monkeypatch.setattr(bot_main.discord_utils, "LOG_CHANNEL_ID", 999)
    log_channel = MagicMock()
    log_channel.send = AsyncMock()
    interaction = MagicMock()
    interaction.guild_id = 1
    interaction.client.get_channel = MagicMock(return_value=log_channel)
    interaction.response.send_message = AsyncMock()
    action = discord.app_commands.Choice(name="Enable", value="enable")
    module = discord.app_commands.Choice(name="Events", value="events")

    asyncio.run(bot_main.polyglot_modules.callback(interaction, action, module))

    log_channel.send.assert_awaited_once()
    assert "events" in log_channel.send.call_args.args[0]


def test_polyglot_modules_disables_a_module_for_the_guild(tmp_path, monkeypatch):
    """An admin can turn off a module (e.g. translation) for their server."""
    _use_tmp_store(tmp_path, monkeypatch)
    interaction = MagicMock()
    interaction.guild_id = 1
    interaction.response.send_message = AsyncMock()
    action = discord.app_commands.Choice(name="Disable", value="disable")
    module = discord.app_commands.Choice(name="Translation", value="translation")

    asyncio.run(bot_main.polyglot_modules.callback(interaction, action, module))

    assert storage.is_module_enabled(1, "translation") is False


def test_polyglot_modules_error_reports_missing_permissions():
    """A permissions failure gets a clean, specific message."""
    interaction = MagicMock()
    interaction.response.send_message = AsyncMock()
    error = discord.app_commands.MissingPermissions(["manage_guild"])

    asyncio.run(bot_main._polyglot_modules_error(interaction, error))

    interaction.response.send_message.assert_awaited_once()
    assert "Manage Server" in interaction.response.send_message.call_args.args[0]


def test_help_command_mentions_every_module():
    """/help surfaces core, translation, and events commands, grouped by module."""
    interaction = MagicMock()
    interaction.response.send_message = AsyncMock()

    asyncio.run(bot_main.help_command.callback(interaction))

    sent = interaction.response.send_message.call_args.args[0]
    for command in (
        "/polyglot-modules",
        "/setlanguage",
        "/setbehavior",
        "/createvent",
        "/listevents",
    ):
        assert command in sent
