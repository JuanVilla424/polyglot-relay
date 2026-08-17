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
    monkeypatch.setattr(storage, "SERVER_LANGUAGE_PATH", tmp_path / "server_language.json")
    monkeypatch.setattr(storage, "DELIVERY_MODE_PATH", tmp_path / "delivery_mode.json")


def _make_member(guild_id, user_id, role_ids=()):
    member = MagicMock()
    member.id = user_id
    member.bot = False
    member.guild.id = guild_id
    member.roles = [MagicMock(id=rid) for rid in role_ids]
    return member


def _make_channel(members=(), hidden_from=(), channel_cls=discord.TextChannel):
    """A TextChannel- or Thread-spec'd mock; members in hidden_from can't view_channel."""
    channel = MagicMock(spec=channel_cls)
    channel.guild.members = list(members)
    hidden = set(hidden_from)

    def _perms_for(member):
        perms = MagicMock()
        perms.view_channel = member not in hidden
        return perms

    channel.permissions_for.side_effect = _perms_for
    return channel


def _make_message(author_id, content="hello", author_is_bot=False, channel=None):
    message = MagicMock()
    message.author.id = author_id
    message.author.bot = author_is_bot
    message.author.display_name = "Author"
    message.content = content
    message.channel = channel if channel is not None else _make_channel()
    message.guild = message.channel.guild
    message.reply = AsyncMock()
    message.create_thread = AsyncMock()
    message.add_reaction = AsyncMock()
    return message


def _make_reaction_payload(user_id, guild_id, channel_id, message_id, emoji):
    """A RawReactionActionEvent-shaped mock; emoji is a plain unicode flag string."""
    payload = MagicMock()
    payload.user_id = user_id
    payload.guild_id = guild_id
    payload.channel_id = channel_id
    payload.message_id = message_id
    payload.emoji = discord.PartialEmoji(name=emoji)
    return payload


def _set_bot_user_id(monkeypatch, user_id):
    """discord.Client.user is a read-only property; patch it at the class level."""
    monkeypatch.setattr(discord.Client, "user", property(lambda self: MagicMock(id=user_id)))


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
    assert "setserverlanguage" in names
    assert "clearserverlanguage" in names
    assert "setbehavior" in names
    assert "clearbehavior" in names
    assert "languages" in names
    assert "help" in names
    assert "Translate Message" in names
    assert "Retry Translation" in names


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


def test_setserverlanguage_stores_for_guild(tmp_path, monkeypatch):
    """An admin can set the server's fallback translation language."""
    _use_tmp_store(tmp_path, monkeypatch)
    interaction = MagicMock()
    interaction.guild_id = 1
    interaction.response.send_message = AsyncMock()

    asyncio.run(bot_main.setserverlanguage.callback(interaction, "fr"))

    assert storage.get_server_language(1) == "fr"


def test_setserverlanguage_rejects_unsupported_code(tmp_path, monkeypatch):
    """Unmapped language codes are rejected before ever touching storage."""
    _use_tmp_store(tmp_path, monkeypatch)
    interaction = MagicMock()
    interaction.guild_id = 1
    interaction.response.send_message = AsyncMock()

    asyncio.run(bot_main.setserverlanguage.callback(interaction, "xx"))

    interaction.response.send_message.assert_awaited_once()
    assert storage.get_server_language(1) is None


def test_setbehavior_stores_for_guild(tmp_path, monkeypatch):
    """An admin can choose reply-in-channel or thread delivery for the server."""
    _use_tmp_store(tmp_path, monkeypatch)
    interaction = MagicMock()
    interaction.guild_id = 1
    interaction.response.send_message = AsyncMock()
    mode = discord.app_commands.Choice(name="Open a thread", value="thread")

    asyncio.run(bot_main.setbehavior.callback(interaction, mode))

    assert storage.get_delivery_mode(1) == "thread"


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


def test_channel_member_languages_maps_each_member_to_their_language(tmp_path, monkeypatch):
    """Unlike the deduplicated set, this keeps the per-member mapping needed for DM delivery."""
    _use_tmp_store(tmp_path, monkeypatch)
    storage.set_role_language(1, 10, "fr")
    storage.set_user_language(1, 200, "es")
    member_role_only = _make_member(1, 100, role_ids=[10])
    member_es = _make_member(1, 200)
    channel = _make_channel(members=[member_role_only, member_es])

    mapping = bot_main._channel_member_languages(channel, exclude_user_id=999)

    assert mapping == {member_role_only: "fr", member_es: "es"}


def test_channel_active_languages_deduplicates_and_merges_roles(tmp_path, monkeypatch):
    """Three members sharing 'es' count once; role and explicit languages both count."""
    _use_tmp_store(tmp_path, monkeypatch)
    storage.set_role_language(1, 10, "fr")
    storage.set_user_language(1, 200, "es")
    storage.set_user_language(1, 300, "es")
    member_role_only = _make_member(1, 100, role_ids=[10])
    member_es_a = _make_member(1, 200)
    member_es_b = _make_member(1, 300)
    channel = _make_channel(members=[member_role_only, member_es_a, member_es_b])

    active = bot_main._channel_active_languages(channel, exclude_user_id=999)

    assert active == {"fr", "es"}


def test_channel_active_languages_excludes_the_author(tmp_path, monkeypatch):
    """The message author's own language never counts as a target."""
    _use_tmp_store(tmp_path, monkeypatch)
    storage.set_user_language(1, 100, "es")
    member = _make_member(1, 100)
    channel = _make_channel(members=[member])

    active = bot_main._channel_active_languages(channel, exclude_user_id=100)

    assert active == set()


def test_channel_active_languages_excludes_members_who_cant_view_it(tmp_path, monkeypatch):
    """Someone with a language set but no access to this specific channel doesn't count."""
    _use_tmp_store(tmp_path, monkeypatch)
    storage.set_user_language(1, 100, "es")
    member = _make_member(1, 100)
    channel = _make_channel(members=[member], hidden_from=[member])

    active = bot_main._channel_active_languages(channel, exclude_user_id=999)

    assert active == set()


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


def test_clearserverlanguage_resets_to_default(tmp_path, monkeypatch):
    """An admin can drop the guild's override and go back to the built-in default."""
    _use_tmp_store(tmp_path, monkeypatch)
    storage.set_server_language(1, "fr")
    interaction = MagicMock()
    interaction.guild_id = 1
    interaction.response.send_message = AsyncMock()

    asyncio.run(bot_main.clearserverlanguage.callback(interaction))

    assert storage.get_server_language(1) is None


def test_clearbehavior_resets_to_default(tmp_path, monkeypatch):
    """An admin can drop the guild's delivery override and go back to the default."""
    _use_tmp_store(tmp_path, monkeypatch)
    storage.set_delivery_mode(1, "thread")
    interaction = MagicMock()
    interaction.guild_id = 1
    interaction.response.send_message = AsyncMock()

    asyncio.run(bot_main.clearbehavior.callback(interaction))

    assert storage.get_delivery_mode(1) is None


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
        "/setserverlanguage",
        "/clearserverlanguage",
        "/setbehavior",
        "/clearbehavior",
    ):
        assert command in sent


def test_on_message_ignores_bot_authors(tmp_path, monkeypatch):
    """Messages from other bots never trigger auto-translate."""
    _use_tmp_store(tmp_path, monkeypatch)
    message = _make_message(100, author_is_bot=True)
    translate_mock = AsyncMock()
    monkeypatch.setattr(bot_main.translator, "translate", translate_mock)

    asyncio.run(bot_main.on_message(message))

    translate_mock.assert_not_awaited()


def test_on_message_replies_with_combined_translations(tmp_path, monkeypatch):
    """A channel with an active language gets a reply with the translation."""
    _use_tmp_store(tmp_path, monkeypatch)
    storage.set_user_language(1, 200, "es")
    storage.set_delivery_mode(1, "reply")
    member = _make_member(1, 200)
    channel = _make_channel(members=[member])
    message = _make_message(100, content="hello", channel=channel)
    message.guild.id = 1
    monkeypatch.setattr(bot_main.translator, "translate", AsyncMock(return_value=("hola", "en")))

    asyncio.run(bot_main.on_message(message))

    message.reply.assert_awaited_once()
    assert message.reply.call_args.kwargs["mention_author"] is False
    sent_embeds = message.reply.call_args.kwargs["embeds"]
    assert len(sent_embeds) == 1
    assert sent_embeds[0].title.startswith("es")
    assert sent_embeds[0].description == "hola"


def test_on_message_uses_thread_when_guild_configured_for_it(tmp_path, monkeypatch):
    """A guild set to thread mode via /setbehavior gets a thread, not a reply."""
    _use_tmp_store(tmp_path, monkeypatch)
    storage.set_user_language(1, 200, "es")
    storage.set_delivery_mode(1, "thread")
    member = _make_member(1, 200)
    channel = _make_channel(members=[member])
    message = _make_message(100, content="hello", channel=channel)
    message.guild.id = 1
    monkeypatch.setattr(bot_main.translator, "translate", AsyncMock(return_value=("hola", "en")))

    asyncio.run(bot_main.on_message(message))

    message.reply.assert_not_awaited()
    message.create_thread.assert_awaited_once()
    thread = message.create_thread.return_value
    thread.send.assert_awaited_once()
    sent_embeds = thread.send.call_args.kwargs["embeds"]
    assert len(sent_embeds) == 1
    assert sent_embeds[0].title.startswith("es")


def test_on_message_dms_each_member_in_their_own_language(tmp_path, monkeypatch):
    """A guild set to dm mode sends a private DM to each configured member, not a public reply."""
    _use_tmp_store(tmp_path, monkeypatch)
    storage.set_user_language(1, 200, "es")
    storage.set_delivery_mode(1, "dm")
    member = _make_member(1, 200)
    member.send = AsyncMock()
    channel = _make_channel(members=[member])
    message = _make_message(100, content="hello", channel=channel)
    message.guild.id = 1
    monkeypatch.setattr(bot_main.translator, "translate", AsyncMock(return_value=("hola", "en")))

    asyncio.run(bot_main.on_message(message))

    message.reply.assert_not_awaited()
    message.create_thread.assert_not_awaited()
    member.send.assert_awaited_once()
    sent_embeds = member.send.call_args.kwargs["embeds"]
    assert len(sent_embeds) == 1
    assert sent_embeds[0].title.startswith("es")


def test_on_message_dm_mode_skips_members_without_a_language(tmp_path, monkeypatch):
    """In dm mode, nobody gets an unsolicited DM just because they can see the channel."""
    _use_tmp_store(tmp_path, monkeypatch)
    storage.set_delivery_mode(1, "dm")
    member_no_lang = _make_member(1, 200)
    member_no_lang.send = AsyncMock()
    channel = _make_channel(members=[member_no_lang])
    message = _make_message(100, content="hello", channel=channel)
    message.guild.id = 1
    translate_mock = AsyncMock()
    monkeypatch.setattr(bot_main.translator, "translate", translate_mock)

    asyncio.run(bot_main.on_message(message))

    translate_mock.assert_not_awaited()
    member_no_lang.send.assert_not_awaited()


def test_deliver_as_dm_continues_after_one_member_has_dms_closed():
    """One member with DMs closed doesn't stop the rest from receiving theirs."""
    member_ok = _make_member(1, 200)
    member_ok.send = AsyncMock()
    response = MagicMock(status=403, reason="Forbidden")
    member_closed = _make_member(1, 300)
    member_closed.send = AsyncMock(
        side_effect=discord.Forbidden(response, "cannot send to this user")
    )
    embed = bot_main._make_language_embed("es", "hola")

    status = asyncio.run(
        bot_main._deliver_as_dm({member_ok: "es", member_closed: "es"}, {"es": [embed]})
    )

    member_ok.send.assert_awaited_once()
    member_closed.send.assert_awaited_once()
    assert status == "Sent 1 DM(s), 1 failed (DMs closed)."


def test_on_message_translates_inside_a_thread(tmp_path, monkeypatch):
    """A message posted inside a thread (e.g. a forum post) is translated too."""
    _use_tmp_store(tmp_path, monkeypatch)
    storage.set_user_language(1, 200, "es")
    member = _make_member(1, 200)
    channel = _make_channel(members=[member], channel_cls=discord.Thread)
    message = _make_message(100, content="hello", channel=channel)
    monkeypatch.setattr(bot_main.translator, "translate", AsyncMock(return_value=("hola", "en")))

    asyncio.run(bot_main.on_message(message))

    message.reply.assert_awaited_once()
    sent_embeds = message.reply.call_args.kwargs["embeds"]
    assert sent_embeds[0].title.startswith("es")


def test_on_message_inside_a_thread_ignores_thread_delivery_mode(tmp_path, monkeypatch):
    """Can't nest a thread in a thread: falls back to reply even if the guild wants thread mode."""
    _use_tmp_store(tmp_path, monkeypatch)
    storage.set_user_language(1, 200, "es")
    storage.set_delivery_mode(1, "thread")
    member = _make_member(1, 200)
    channel = _make_channel(members=[member], channel_cls=discord.Thread)
    message = _make_message(100, content="hello", channel=channel)
    message.guild.id = 1
    monkeypatch.setattr(bot_main.translator, "translate", AsyncMock(return_value=("hola", "en")))

    asyncio.run(bot_main.on_message(message))

    message.reply.assert_awaited_once()
    message.create_thread.assert_not_awaited()


def test_on_message_no_reply_when_detected_already_matches(tmp_path, monkeypatch):
    """No reply noise when the detected language already matches the only active one."""
    _use_tmp_store(tmp_path, monkeypatch)
    storage.set_user_language(1, 200, "en")
    storage.set_delivery_mode(1, "reply")
    member = _make_member(1, 200)
    channel = _make_channel(members=[member])
    message = _make_message(100, content="hello", channel=channel)
    message.guild.id = 1
    monkeypatch.setattr(bot_main.translator, "translate", AsyncMock(return_value=("hello", "en")))

    asyncio.run(bot_main.on_message(message))

    message.reply.assert_not_awaited()


def test_on_message_falls_back_to_server_language_with_no_configured_members(tmp_path, monkeypatch):
    """An empty channel still gets a server-language reply for a non-server-language message."""
    _use_tmp_store(tmp_path, monkeypatch)
    storage.set_delivery_mode(1, "reply")
    message = _make_message(100, content="hola")
    message.guild.id = 1
    monkeypatch.setattr(bot_main.translator, "translate", AsyncMock(return_value=("Hello", "es")))

    asyncio.run(bot_main.on_message(message))

    message.reply.assert_awaited_once()
    sent_embeds = message.reply.call_args.kwargs["embeds"]
    assert len(sent_embeds) == 1
    assert sent_embeds[0].title.startswith(bot_main.DEFAULT_SERVER_LANGUAGE)
    assert sent_embeds[0].description == "Hello"


def test_on_message_no_reply_when_already_in_server_language(tmp_path, monkeypatch):
    """A message already in the server language, with no one else configured, gets no reply."""
    _use_tmp_store(tmp_path, monkeypatch)
    storage.set_delivery_mode(1, "reply")
    message = _make_message(100, content="hello")
    message.guild.id = 1
    translate_mock = AsyncMock(return_value=("hello", bot_main.DEFAULT_SERVER_LANGUAGE))
    monkeypatch.setattr(bot_main.translator, "translate", translate_mock)

    asyncio.run(bot_main.on_message(message))

    message.reply.assert_not_awaited()


def test_on_message_uses_guild_server_language_override(tmp_path, monkeypatch):
    """A guild-configured server language wins over the built-in default."""
    _use_tmp_store(tmp_path, monkeypatch)
    storage.set_server_language(1, "es")
    storage.set_delivery_mode(1, "reply")
    message = _make_message(100, content="hello")
    message.guild.id = 1
    monkeypatch.setattr(bot_main.translator, "translate", AsyncMock(return_value=("hola", "en")))

    asyncio.run(bot_main.on_message(message))

    message.reply.assert_awaited_once()
    sent_embeds = message.reply.call_args.kwargs["embeds"]
    assert len(sent_embeds) == 1
    assert sent_embeds[0].title.startswith("es")
    assert sent_embeds[0].description == "hola"


def test_on_message_handles_reply_failure_gracefully(tmp_path, monkeypatch):
    """A permission error sending the reply doesn't raise out of the handler."""
    _use_tmp_store(tmp_path, monkeypatch)
    storage.set_user_language(1, 200, "es")
    storage.set_delivery_mode(1, "reply")
    member = _make_member(1, 200)
    channel = _make_channel(members=[member])
    message = _make_message(100, content="hello", channel=channel)
    message.guild.id = 1
    response = MagicMock(status=403, reason="Forbidden")
    message.reply = AsyncMock(side_effect=discord.Forbidden(response, "no perms"))
    monkeypatch.setattr(bot_main.translator, "translate", AsyncMock(return_value=("hola", "en")))

    asyncio.run(bot_main.on_message(message))  # must not raise


def test_retry_translation_rejects_empty_message(tmp_path, monkeypatch):
    """An admin can't retry a message with no content."""
    _use_tmp_store(tmp_path, monkeypatch)
    interaction = MagicMock()
    interaction.response.send_message = AsyncMock()
    message = _make_message(100, content="")

    asyncio.run(bot_main.retry_translation.callback(interaction, message))

    interaction.response.send_message.assert_awaited_once()
    message.reply.assert_not_awaited()


def test_retry_translation_replies_and_reports_status(tmp_path, monkeypatch):
    """A successful retry defers, runs the same logic as on_message, then reports success."""
    _use_tmp_store(tmp_path, monkeypatch)
    storage.set_user_language(1, 200, "es")
    storage.set_delivery_mode(1, "reply")
    member = _make_member(1, 200)
    channel = _make_channel(members=[member])
    message = _make_message(100, content="hello", channel=channel)
    message.guild.id = 1
    interaction = MagicMock()
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()
    monkeypatch.setattr(bot_main.translator, "translate", AsyncMock(return_value=("hola", "en")))

    asyncio.run(bot_main.retry_translation.callback(interaction, message))

    interaction.response.defer.assert_awaited_once()
    message.reply.assert_awaited_once()
    interaction.followup.send.assert_awaited_once_with("Translation sent.", ephemeral=True)


def test_retry_translation_reports_when_nothing_to_translate(tmp_path, monkeypatch):
    """No active languages -> the admin gets told nothing happened, not silence."""
    _use_tmp_store(tmp_path, monkeypatch)
    storage.set_delivery_mode(1, "reply")
    message = _make_message(100, content="hello")
    message.guild.id = 1
    interaction = MagicMock()
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()
    monkeypatch.setattr(
        bot_main.translator,
        "translate",
        AsyncMock(return_value=("hello", bot_main.DEFAULT_SERVER_LANGUAGE)),
    )

    asyncio.run(bot_main.retry_translation.callback(interaction, message))

    message.reply.assert_not_awaited()
    interaction.followup.send.assert_awaited_once()
    assert "Nothing to translate" in interaction.followup.send.call_args.args[0]


def test_make_language_embed_sets_title_description_and_color():
    """Each embed carries the language code+name as title and a deterministic color."""
    embed = bot_main._make_language_embed("es", "hola")

    assert embed.title == "es — Spanish"
    assert embed.description == "hola"
    assert embed.color.value == bot_main.color_for("es")


def test_make_language_embeds_returns_one_embed_for_short_text():
    """Text under the 4096-char limit stays a single embed, no part suffix."""
    embeds = bot_main._make_language_embeds("es", "hola")

    assert len(embeds) == 1
    assert embeds[0].title == "es — Spanish"
    assert embeds[0].description == "hola"


def test_make_language_embeds_splits_long_text_without_losing_any_of_it():
    """A translation over 4096 chars splits into numbered embeds, content fully preserved."""
    long_text = "a" * 5000

    embeds = bot_main._make_language_embeds("es", long_text)

    assert len(embeds) == 2
    assert embeds[0].title == "es — Spanish (1/2)"
    assert embeds[1].title == "es — Spanish (2/2)"
    assert embeds[0].description + embeds[1].description == long_text


def test_color_for_is_deterministic_and_reused_past_eight_codes():
    """Same code -> same color every time; the 8-slot palette cycles for the 9th+ code."""
    codes = list(bot_main.ISO_TO_FLORES)
    assert bot_main.color_for(codes[0]) == bot_main.color_for(codes[0])
    if len(codes) > 8:
        assert bot_main.color_for(codes[0]) == bot_main.color_for(codes[8])


def test_chunk_embeds_fits_a_few_embeds_in_one_batch():
    """A handful of short embeds -> a single batch, one reply."""
    embeds = [bot_main._make_language_embed(code, "short") for code in ("es", "en", "fr")]

    batches = bot_main._chunk_embeds(embeds)

    assert len(batches) == 1
    assert len(batches[0]) == 3


def test_chunk_embeds_splits_past_the_ten_embed_cap():
    """Discord allows at most 10 embeds per message -> more than that needs multiple batches."""
    embeds = [bot_main._make_language_embed(f"x{i}", "short") for i in range(11)]

    batches = bot_main._chunk_embeds(embeds)

    assert [len(b) for b in batches] == [10, 1]


def test_chunk_embeds_splits_when_combined_length_exceeds_the_limit():
    """Real crash case (Discord error 50035), now avoided by batching embeds by size too."""
    embeds = [bot_main._make_language_embed(f"x{i}", "a" * 1900) for i in range(4)]

    batches = bot_main._chunk_embeds(embeds)

    assert len(batches) > 1
    for batch in batches:
        total = sum(len(e.title or "") + len(e.description or "") for e in batch)
        assert total <= bot_main.DISCORD_EMBED_TOTAL_CHAR_LIMIT


def test_on_message_batches_embeds_past_the_ten_language_cap(tmp_path, monkeypatch):
    """More than 10 active languages -> multiple replies, all embeds still delivered."""
    _use_tmp_store(tmp_path, monkeypatch)
    storage.set_delivery_mode(1, "reply")
    codes = ["es", "fr", "de", "pt", "it", "ja", "ko", "zh", "ru", "ar", "hi"]
    members = []
    for i, lang in enumerate(codes):
        storage.set_user_language(1, 200 + i, lang)
        members.append(_make_member(1, 200 + i))
    channel = _make_channel(members=members)
    message = _make_message(100, content="hello", channel=channel)
    message.guild.id = 1
    monkeypatch.setattr(
        bot_main.translator, "translate", AsyncMock(return_value=("translated", "en"))
    )

    asyncio.run(bot_main.on_message(message))  # must not raise

    assert message.reply.await_count == 2
    total_embeds = sum(len(call.kwargs["embeds"]) for call in message.reply.call_args_list)
    assert total_embeds == len(codes)


def test_setbehavior_stores_reactions_mode_for_guild(tmp_path, monkeypatch):
    """An admin can choose flag-reactions delivery for the server."""
    _use_tmp_store(tmp_path, monkeypatch)
    interaction = MagicMock()
    interaction.guild_id = 1
    interaction.response.send_message = AsyncMock()
    mode = discord.app_commands.Choice(
        name="Flag reactions (translate on demand)", value="reactions"
    )

    asyncio.run(bot_main.setbehavior.callback(interaction, mode))

    assert storage.get_delivery_mode(1) == "reactions"


def test_deliver_as_reactions_adds_one_flag_per_language(monkeypatch):
    """Each active language with a known flag gets its own reaction, nothing translated upfront."""
    message = _make_message(100, content="hello")
    translate_mock = AsyncMock()
    monkeypatch.setattr(bot_main.translator, "translate", translate_mock)
    monkeypatch.setattr(bot_main.translator, "detect_language", AsyncMock(return_value="en"))

    status = asyncio.run(bot_main._deliver_as_reactions(message, {"es", "fr"}))

    assert message.add_reaction.await_count == 2
    added_flags = {call.args[0] for call in message.add_reaction.call_args_list}
    assert added_flags == {bot_main.ISO_TO_FLAG["es"], bot_main.ISO_TO_FLAG["fr"]}
    assert status == "Added 2 flag reaction(s)."
    translate_mock.assert_not_awaited()


def test_deliver_as_reactions_skips_the_flag_matching_the_detected_language(monkeypatch):
    """Real bug report: writing in a language shouldn't get offered a same-language 'translation'.

    E.g. the server's fallback language is active and someone writes in that
    exact language -- no flag for it should appear, since translating it into
    itself is a no-op.
    """
    message = _make_message(100, content="hello")
    monkeypatch.setattr(bot_main.translator, "detect_language", AsyncMock(return_value="en"))

    status = asyncio.run(bot_main._deliver_as_reactions(message, {"en", "it"}))

    added_flags = {call.args[0] for call in message.add_reaction.call_args_list}
    assert added_flags == {bot_main.ISO_TO_FLAG["it"]}
    assert status == "Added 1 flag reaction(s)."


def test_deliver_as_reactions_falls_back_to_adding_every_flag_if_detection_fails(monkeypatch):
    """A LibreTranslate hiccup shouldn't block flags entirely -- fall back to the old behavior."""
    message = _make_message(100, content="hello")
    monkeypatch.setattr(
        bot_main.translator, "detect_language", AsyncMock(side_effect=RuntimeError("boom"))
    )

    status = asyncio.run(bot_main._deliver_as_reactions(message, {"es", "fr"}))

    assert message.add_reaction.await_count == 2
    assert status == "Added 2 flag reaction(s)."


def test_deliver_as_reactions_skips_languages_without_a_known_flag(monkeypatch):
    """Catalan has no distinct flag in ISO_TO_FLAG; it's skipped, not an error."""
    message = _make_message(100, content="hello")
    monkeypatch.setattr(bot_main.translator, "detect_language", AsyncMock(return_value="en"))

    status = asyncio.run(bot_main._deliver_as_reactions(message, {"ca"}))

    message.add_reaction.assert_not_awaited()
    assert (
        status
        == "No flags to add (message already matches every active language, or no known flag)."
    )


def test_deliver_as_reactions_continues_after_one_reaction_fails(monkeypatch):
    """One flag failing to add (e.g. a permission hiccup) doesn't stop the rest."""
    message = _make_message(100, content="hello")
    monkeypatch.setattr(bot_main.translator, "detect_language", AsyncMock(return_value="en"))
    response = MagicMock(status=403, reason="Forbidden")
    message.add_reaction = AsyncMock(side_effect=[discord.Forbidden(response, "no perms"), None])

    status = asyncio.run(bot_main._deliver_as_reactions(message, {"es", "fr"}))

    assert message.add_reaction.await_count == 2
    assert status == "Added 1 flag reaction(s)."


def test_on_message_reactions_mode_adds_flags_without_translating_upfront(tmp_path, monkeypatch):
    """/setbehavior reactions: flags appear immediately, nothing is translated until someone reacts."""
    _use_tmp_store(tmp_path, monkeypatch)
    storage.set_user_language(1, 200, "es")
    storage.set_delivery_mode(1, "reactions")
    member = _make_member(1, 200)
    channel = _make_channel(members=[member])
    message = _make_message(100, content="hello", channel=channel)
    message.guild.id = 1
    translate_mock = AsyncMock()
    monkeypatch.setattr(bot_main.translator, "translate", translate_mock)
    monkeypatch.setattr(bot_main.translator, "detect_language", AsyncMock(return_value="fr"))

    asyncio.run(bot_main.on_message(message))

    message.reply.assert_not_awaited()
    message.create_thread.assert_not_awaited()
    translate_mock.assert_not_awaited()
    added_flags = {call.args[0] for call in message.add_reaction.call_args_list}
    assert bot_main.ISO_TO_FLAG["es"] in added_flags
    assert bot_main.ISO_TO_FLAG[bot_main.DEFAULT_SERVER_LANGUAGE] in added_flags


def test_on_message_uses_reactions_by_default_when_guild_unconfigured(tmp_path, monkeypatch):
    """No /setbehavior ever run for this guild -> flag reactions, not a reply (the new default)."""
    _use_tmp_store(tmp_path, monkeypatch)
    storage.set_user_language(1, 200, "es")
    member = _make_member(1, 200)
    channel = _make_channel(members=[member])
    message = _make_message(100, content="hello", channel=channel)
    message.guild.id = 1
    translate_mock = AsyncMock()
    monkeypatch.setattr(bot_main.translator, "translate", translate_mock)
    monkeypatch.setattr(bot_main.translator, "detect_language", AsyncMock(return_value="fr"))

    asyncio.run(bot_main.on_message(message))

    message.reply.assert_not_awaited()
    translate_mock.assert_not_awaited()
    added_flags = {call.args[0] for call in message.add_reaction.call_args_list}
    assert bot_main.ISO_TO_FLAG["es"] in added_flags


def test_on_raw_reaction_add_ignores_the_bots_own_reaction(tmp_path, monkeypatch):
    """The bot's own flag-adding must never trigger its own translation (explicit requirement)."""
    _use_tmp_store(tmp_path, monkeypatch)
    storage.set_delivery_mode(1, "reactions")
    _set_bot_user_id(monkeypatch, 999)
    payload = _make_reaction_payload(
        user_id=999, guild_id=1, channel_id=10, message_id=20, emoji="🇪🇸"
    )
    monkeypatch.setattr(
        bot_main.client, "get_channel", MagicMock(side_effect=AssertionError("should not run"))
    )

    asyncio.run(bot_main.on_raw_reaction_add(payload))  # must not raise or look anything up


def test_on_raw_reaction_add_ignores_reactions_outside_a_guild(monkeypatch):
    """A flag reaction on a DM message (no guild) is ignored, not looked up."""
    _set_bot_user_id(monkeypatch, 999)
    payload = _make_reaction_payload(
        user_id=100, guild_id=None, channel_id=10, message_id=20, emoji="🇪🇸"
    )
    monkeypatch.setattr(
        bot_main.client, "get_channel", MagicMock(side_effect=AssertionError("should not run"))
    )

    asyncio.run(bot_main.on_raw_reaction_add(payload))  # must not raise


def test_on_raw_reaction_add_ignores_unrecognized_emoji(tmp_path, monkeypatch):
    """A reaction with an emoji that isn't a mapped flag is ignored."""
    _use_tmp_store(tmp_path, monkeypatch)
    storage.set_delivery_mode(1, "reactions")
    _set_bot_user_id(monkeypatch, 999)
    payload = _make_reaction_payload(
        user_id=100, guild_id=1, channel_id=10, message_id=20, emoji="👍"
    )
    monkeypatch.setattr(
        bot_main.client, "get_channel", MagicMock(side_effect=AssertionError("should not run"))
    )

    asyncio.run(bot_main.on_raw_reaction_add(payload))  # must not raise


def test_on_raw_reaction_add_ignores_when_guild_not_in_reactions_mode(tmp_path, monkeypatch):
    """A flag reaction in a guild set to reply/thread/dm mode doesn't trigger anything."""
    _use_tmp_store(tmp_path, monkeypatch)
    storage.set_delivery_mode(1, "reply")
    _set_bot_user_id(monkeypatch, 999)
    payload = _make_reaction_payload(
        user_id=100, guild_id=1, channel_id=10, message_id=20, emoji="🇪🇸"
    )
    monkeypatch.setattr(
        bot_main.client, "get_channel", MagicMock(side_effect=AssertionError("should not run"))
    )

    asyncio.run(bot_main.on_raw_reaction_add(payload))  # must not raise


def test_on_raw_reaction_add_translates_and_replies_on_a_recognized_flag(tmp_path, monkeypatch):
    """The full happy path: guild in reactions mode, a real flag -> on-demand public translation."""
    _use_tmp_store(tmp_path, monkeypatch)
    storage.set_delivery_mode(1, "reactions")
    _set_bot_user_id(monkeypatch, 999)
    message = _make_message(100, content="hello")
    channel = MagicMock(spec=discord.TextChannel)
    channel.fetch_message = AsyncMock(return_value=message)
    monkeypatch.setattr(bot_main.client, "get_channel", MagicMock(return_value=channel))
    monkeypatch.setattr(bot_main.translator, "translate", AsyncMock(return_value=("hola", "en")))
    payload = _make_reaction_payload(
        user_id=100, guild_id=1, channel_id=10, message_id=20, emoji="🇪🇸"
    )

    asyncio.run(bot_main.on_raw_reaction_add(payload))

    channel.fetch_message.assert_awaited_once_with(20)
    message.reply.assert_awaited_once()
    sent_embeds = message.reply.call_args.kwargs["embeds"]
    assert sent_embeds[0].title.startswith("es")
    assert sent_embeds[0].description == "hola"


def test_on_raw_reaction_add_handles_a_deleted_message_gracefully(tmp_path, monkeypatch):
    """If the reacted-on message was deleted before the fetch, this must not raise."""
    _use_tmp_store(tmp_path, monkeypatch)
    storage.set_delivery_mode(1, "reactions")
    _set_bot_user_id(monkeypatch, 999)
    channel = MagicMock(spec=discord.TextChannel)
    response = MagicMock(status=404, reason="Not Found")
    channel.fetch_message = AsyncMock(side_effect=discord.NotFound(response, "Unknown Message"))
    monkeypatch.setattr(bot_main.client, "get_channel", MagicMock(return_value=channel))
    payload = _make_reaction_payload(
        user_id=100, guild_id=1, channel_id=10, message_id=20, emoji="🇪🇸"
    )

    asyncio.run(bot_main.on_raw_reaction_add(payload))  # must not raise


def test_on_raw_reaction_add_falls_back_to_fetch_channel_when_not_cached(tmp_path, monkeypatch):
    """An uncached channel (e.g. an old thread) is fetched over the API instead of being skipped."""
    _use_tmp_store(tmp_path, monkeypatch)
    storage.set_delivery_mode(1, "reactions")
    _set_bot_user_id(monkeypatch, 999)
    message = _make_message(100, content="hello")
    channel = MagicMock(spec=discord.TextChannel)
    channel.fetch_message = AsyncMock(return_value=message)
    monkeypatch.setattr(bot_main.client, "get_channel", MagicMock(return_value=None))
    monkeypatch.setattr(bot_main.client, "fetch_channel", AsyncMock(return_value=channel))
    monkeypatch.setattr(bot_main.translator, "translate", AsyncMock(return_value=("hola", "en")))
    payload = _make_reaction_payload(
        user_id=100, guild_id=1, channel_id=10, message_id=20, emoji="🇪🇸"
    )

    asyncio.run(bot_main.on_raw_reaction_add(payload))

    message.reply.assert_awaited_once()
