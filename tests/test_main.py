# pylint: disable=protected-access
# White-box tests deliberately reach into main.py's internal helpers.
import asyncio
from unittest.mock import AsyncMock, MagicMock

import discord

from app import main as bot_main
from app import storage


def _use_tmp_store(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    monkeypatch.setattr(storage, "USER_LANGUAGES_PATH", tmp_path / "user_languages.json")
    monkeypatch.setattr(storage, "ROLE_LANGUAGES_PATH", tmp_path / "role_languages.json")


def _make_member(guild_id, user_id, role_ids=()):
    member = MagicMock()
    member.id = user_id
    member.guild.id = guild_id
    member.roles = [MagicMock(id=rid) for rid in role_ids]
    return member


def _make_message(guild_id, author_id, content="hello", author_is_bot=False):
    message = MagicMock()
    message.author.id = author_id
    message.author.bot = author_is_bot
    message.author.display_name = "Author"
    message.guild.id = guild_id
    message.guild.members = []
    message.content = content
    message.channel.name = "general"
    return message


def test_intents_enable_message_content():
    """Auto-translate needs the privileged message content intent enabled."""
    assert bot_main.intents.message_content is True


def test_client_and_tree_are_wired():
    """The command tree must be bound to the same client instance we run."""
    assert isinstance(bot_main.client, discord.Client)
    assert isinstance(bot_main.tree, discord.app_commands.CommandTree)
    assert bot_main.tree.client is bot_main.client


def test_commands_are_registered():
    """Slash commands and the context menu command are all registered."""
    names = {command.name for command in bot_main.tree.get_commands()}
    assert "setlanguage" in names
    assert "setuserlanguage" in names
    assert "setrolelanguage" in names
    assert "languages" in names
    assert "help" in names
    assert "Translate Message" in names


def test_setlanguage_rejects_unsupported_code(tmp_path, monkeypatch):
    """Unmapped language codes are rejected before ever touching storage."""
    _use_tmp_store(tmp_path, monkeypatch)
    interaction = MagicMock()
    interaction.guild_id = 1
    interaction.user.id = 100
    interaction.response.send_message = AsyncMock()

    asyncio.run(bot_main.setlanguage.callback(interaction, "xx"))

    interaction.response.send_message.assert_awaited_once()
    assert storage.get_user_language(1, 100) is None


def test_setlanguage_stores_supported_code(tmp_path, monkeypatch):
    """A supported code is normalized to lowercase and persisted."""
    _use_tmp_store(tmp_path, monkeypatch)
    interaction = MagicMock()
    interaction.guild_id = 1
    interaction.user.id = 100
    interaction.response.send_message = AsyncMock()

    asyncio.run(bot_main.setlanguage.callback(interaction, "ES"))

    assert storage.get_user_language(1, 100) == "es"


def test_setuserlanguage_stores_for_target_member(tmp_path, monkeypatch):
    """An admin can set someone else's language on their behalf."""
    _use_tmp_store(tmp_path, monkeypatch)
    interaction = MagicMock()
    interaction.response.send_message = AsyncMock()
    target = _make_member(1, 100)

    asyncio.run(bot_main.setuserlanguage.callback(interaction, target, "es"))

    assert storage.get_user_language(1, 100) == "es"


def test_setrolelanguage_stores_for_role(tmp_path, monkeypatch):
    """An admin can map a role to a language."""
    _use_tmp_store(tmp_path, monkeypatch)
    interaction = MagicMock()
    interaction.response.send_message = AsyncMock()
    role = MagicMock()
    role.id = 10
    role.guild.id = 1

    asyncio.run(bot_main.setrolelanguage.callback(interaction, role, "fr"))

    assert storage.get_role_language(1, 10) == "fr"


def test_admin_command_error_reports_missing_permissions():
    """A permissions failure gets a clean, specific message."""
    interaction = MagicMock()
    interaction.response.send_message = AsyncMock()
    error = discord.app_commands.MissingPermissions(["manage_guild"])

    asyncio.run(bot_main._admin_command_error(interaction, error))

    interaction.response.send_message.assert_awaited_once()
    assert "Manage Server" in interaction.response.send_message.call_args.args[0]


def test_admin_command_error_reports_generic_failure():
    """Any other error still gets a response instead of failing silently."""
    interaction = MagicMock()
    interaction.response.send_message = AsyncMock()

    asyncio.run(bot_main._admin_command_error(interaction, RuntimeError("boom")))

    interaction.response.send_message.assert_awaited_once()


def test_resolve_member_language_prefers_explicit_over_role(tmp_path, monkeypatch):
    """An explicit /setlanguage wins even if the member also has a mapped role."""
    _use_tmp_store(tmp_path, monkeypatch)
    storage.set_role_language(1, 10, "fr")
    storage.set_user_language(1, 100, "es")
    member = _make_member(1, 100, role_ids=[10])

    assert bot_main._resolve_member_language(member) == "es"


def test_resolve_member_language_falls_back_to_role(tmp_path, monkeypatch):
    """No explicit language set -> the member's mapped role decides."""
    _use_tmp_store(tmp_path, monkeypatch)
    storage.set_role_language(1, 10, "fr")
    member = _make_member(1, 100, role_ids=[10])

    assert bot_main._resolve_member_language(member) == "fr"


def test_resolve_member_language_none_when_unmapped(tmp_path, monkeypatch):
    """No explicit language and no mapped role -> no language is guessed."""
    _use_tmp_store(tmp_path, monkeypatch)
    member = _make_member(1, 100)

    assert bot_main._resolve_member_language(member) is None


def test_resolve_guild_recipients_merges_roles_and_explicit(tmp_path, monkeypatch):
    """Role holders and explicit users both show up; explicit overrides role for the same user."""
    _use_tmp_store(tmp_path, monkeypatch)
    storage.set_role_language(1, 10, "fr")
    storage.set_user_language(1, 200, "es")
    storage.set_user_language(1, 300, "de")
    member_role_only = _make_member(1, 100, role_ids=[10])
    member_explicit_overrides_role = _make_member(1, 300, role_ids=[10])

    guild = MagicMock()
    guild.id = 1
    guild.members = [member_role_only, member_explicit_overrides_role]

    recipients = bot_main._resolve_guild_recipients(guild)

    assert recipients[100] == "fr"
    assert recipients[300] == "de"
    assert recipients[200] == "es"


def test_report_language_change_noop_when_unconfigured(monkeypatch):
    """No LOG_CHANNEL_ID set -> the client is never touched."""
    monkeypatch.setattr(bot_main, "LOG_CHANNEL_ID", None)
    monkeypatch.setattr(
        bot_main.client, "get_channel", MagicMock(side_effect=AssertionError("should not run"))
    )

    asyncio.run(bot_main._report_language_change("hello"))


def test_report_language_change_sends_to_configured_channel(monkeypatch):
    """A configured channel receives the message verbatim."""
    monkeypatch.setattr(bot_main, "LOG_CHANNEL_ID", 999)
    channel = MagicMock()
    channel.send = AsyncMock()
    monkeypatch.setattr(bot_main.client, "get_channel", MagicMock(return_value=channel))

    asyncio.run(bot_main._report_language_change("hello"))

    channel.send.assert_awaited_once_with("hello")


def test_report_language_change_swallows_send_failures(monkeypatch):
    """A permission error posting to the log channel never propagates to the caller."""
    monkeypatch.setattr(bot_main, "LOG_CHANNEL_ID", 999)
    response = MagicMock(status=403, reason="Forbidden")
    channel = MagicMock()
    channel.send = AsyncMock(side_effect=discord.Forbidden(response, "missing permissions"))
    monkeypatch.setattr(bot_main.client, "get_channel", MagicMock(return_value=channel))

    asyncio.run(bot_main._report_language_change("hello"))  # must not raise


def test_clearlanguage_removes_stored_preference(tmp_path, monkeypatch):
    """Clearing removes a previously stored self-service preference."""
    _use_tmp_store(tmp_path, monkeypatch)
    storage.set_user_language(1, 100, "es")
    interaction = MagicMock()
    interaction.guild_id = 1
    interaction.user.id = 100
    interaction.response.send_message = AsyncMock()

    asyncio.run(bot_main.clearlanguage.callback(interaction))

    assert storage.get_user_language(1, 100) is None


def test_clearuserlanguage_removes_target_member(tmp_path, monkeypatch):
    """An admin can remove another member's stored language."""
    _use_tmp_store(tmp_path, monkeypatch)
    storage.set_user_language(1, 100, "es")
    interaction = MagicMock()
    interaction.response.send_message = AsyncMock()
    target = _make_member(1, 100)

    asyncio.run(bot_main.clearuserlanguage.callback(interaction, target))

    assert storage.get_user_language(1, 100) is None


def test_clearrolelanguage_removes_role_mapping(tmp_path, monkeypatch):
    """An admin can remove a role's language mapping."""
    _use_tmp_store(tmp_path, monkeypatch)
    storage.set_role_language(1, 10, "fr")
    interaction = MagicMock()
    interaction.response.send_message = AsyncMock()
    role = MagicMock()
    role.id = 10
    role.guild.id = 1

    asyncio.run(bot_main.clearrolelanguage.callback(interaction, role))

    assert storage.get_role_language(1, 10) is None


def test_languages_command_lists_known_codes():
    """The /languages command surfaces codes together with their language name."""
    interaction = MagicMock()
    interaction.response.send_message = AsyncMock()

    asyncio.run(bot_main.languages.callback(interaction))

    sent = interaction.response.send_message.call_args.args[0]
    assert "`es` — Spanish" in sent
    assert "`en` — English" in sent


def test_help_command_lists_every_command():
    """/help mentions every user-facing and admin command."""
    interaction = MagicMock()
    interaction.response.send_message = AsyncMock()

    asyncio.run(bot_main.help_command.callback(interaction))

    sent = interaction.response.send_message.call_args.args[0]
    for command in (
        "/setlanguage",
        "/clearlanguage",
        "/languages",
        "/setuserlanguage",
        "/clearuserlanguage",
        "/setrolelanguage",
        "/clearrolelanguage",
    ):
        assert command in sent


def test_on_message_ignores_bot_authors(tmp_path, monkeypatch):
    """Messages from other bots never trigger auto-translate."""
    _use_tmp_store(tmp_path, monkeypatch)
    message = _make_message(1, 100, author_is_bot=True)
    translate_mock = AsyncMock()
    monkeypatch.setattr(bot_main.translator, "translate", translate_mock)

    asyncio.run(bot_main.on_message(message))

    translate_mock.assert_not_awaited()


def test_on_message_dms_recipient_with_translation(tmp_path, monkeypatch):
    """A recipient with a configured language gets a DM with the translation."""
    _use_tmp_store(tmp_path, monkeypatch)
    storage.set_user_language(1, 200, "es")
    message = _make_message(1, 100, content="hello")
    recipient = MagicMock()
    recipient.send = AsyncMock()
    monkeypatch.setattr(bot_main.client, "get_user", MagicMock(return_value=recipient))
    monkeypatch.setattr(bot_main.translator, "translate", AsyncMock(return_value=("hola", "en")))

    asyncio.run(bot_main.on_message(message))

    recipient.send.assert_awaited_once()
    assert "hola" in recipient.send.call_args.args[0]


def test_on_message_skips_dm_when_already_target_language(tmp_path, monkeypatch):
    """No DM noise when the detected language already matches the recipient's."""
    _use_tmp_store(tmp_path, monkeypatch)
    storage.set_user_language(1, 200, "en")
    message = _make_message(1, 100, content="hello")
    recipient = MagicMock()
    recipient.send = AsyncMock()
    monkeypatch.setattr(bot_main.client, "get_user", MagicMock(return_value=recipient))
    monkeypatch.setattr(bot_main.translator, "translate", AsyncMock(return_value=("hello", "en")))

    asyncio.run(bot_main.on_message(message))

    recipient.send.assert_not_awaited()


def test_on_message_handles_forbidden_dm_gracefully(tmp_path, monkeypatch):
    """A recipient with closed DMs doesn't break processing for anyone else."""
    _use_tmp_store(tmp_path, monkeypatch)
    storage.set_user_language(1, 200, "es")
    message = _make_message(1, 100, content="hello")
    response = MagicMock(status=403, reason="Forbidden")
    recipient = MagicMock()
    recipient.send = AsyncMock(side_effect=discord.Forbidden(response, "cannot send"))
    monkeypatch.setattr(bot_main.client, "get_user", MagicMock(return_value=recipient))
    monkeypatch.setattr(bot_main.translator, "translate", AsyncMock(return_value=("hola", "en")))

    asyncio.run(bot_main.on_message(message))  # must not raise
