# pylint: disable=protected-access
import asyncio
from unittest.mock import AsyncMock, MagicMock

import discord

from app import storage as core_storage
from app.modules.activity import commands, handlers, logic, scheduler, storage


def _use_tmp_store(tmp_path, monkeypatch):
    monkeypatch.setattr(core_storage, "DATA_DIR", tmp_path)
    monkeypatch.setattr(core_storage, "ENABLED_MODULES_PATH", tmp_path / "enabled_modules.json")
    monkeypatch.setattr(storage, "ACTIVITY_PATH", tmp_path / "activity.json")
    monkeypatch.setattr(storage, "ACTIVITY_DIGEST_PATH", tmp_path / "activity_digest.json")


def _make_member(user_id, bot=False):
    member = MagicMock()
    member.id = user_id
    member.bot = bot
    return member


def _make_guild(guild_id, members, name="Aegis of Wrath"):
    guild = MagicMock()
    guild.id = guild_id
    guild.name = name
    guild.members = members
    return guild


def _make_reaction_payload(user_id, guild_id, channel_id, message_id, emoji):
    payload = MagicMock()
    payload.user_id = user_id
    payload.guild_id = guild_id
    payload.channel_id = channel_id
    payload.message_id = message_id
    payload.emoji = discord.PartialEmoji(name=emoji)
    return payload


# --- storage -----------------------------------------------------------------------


def test_record_and_get_last_active_round_trips(tmp_path, monkeypatch):
    """A recorded timestamp for a member comes back exactly, scoped to its guild."""
    _use_tmp_store(tmp_path, monkeypatch)
    storage.record_activity(guild_id=1, user_id=100, timestamp=5000)

    assert storage.get_last_active(1) == {100: 5000}


def test_get_last_active_excludes_other_guilds(tmp_path, monkeypatch):
    """Activity recorded for one guild never leaks into another's report."""
    _use_tmp_store(tmp_path, monkeypatch)
    storage.record_activity(guild_id=1, user_id=100, timestamp=5000)
    storage.record_activity(guild_id=2, user_id=200, timestamp=6000)

    assert storage.get_last_active(1) == {100: 5000}


def test_record_activity_overwrites_the_previous_timestamp(tmp_path, monkeypatch):
    """A newer activity event replaces the stored one instead of stacking up."""
    _use_tmp_store(tmp_path, monkeypatch)
    storage.record_activity(guild_id=1, user_id=100, timestamp=5000)
    storage.record_activity(guild_id=1, user_id=100, timestamp=9000)

    assert storage.get_last_active(1) == {100: 9000}


def test_get_last_digest_sent_at_is_none_when_never_set(tmp_path, monkeypatch):
    """A guild that's never had a digest sent has no stored timestamp yet."""
    _use_tmp_store(tmp_path, monkeypatch)

    assert storage.get_last_digest_sent_at(1) is None


def test_set_and_get_last_digest_sent_at_round_trips(tmp_path, monkeypatch):
    """The digest timestamp just set for a guild comes back exactly."""
    _use_tmp_store(tmp_path, monkeypatch)
    storage.set_last_digest_sent_at(1, 12345)

    assert storage.get_last_digest_sent_at(1) == 12345


# --- logic.is_digest_due -------------------------------------------------------------


def test_is_digest_due_false_before_the_interval_elapses():
    """Less than a week since the last digest -- not due yet."""
    now = 1_000_000
    last_sent = now - 3 * 86400
    assert logic.is_digest_due(last_sent, now) is False


def test_is_digest_due_true_once_the_interval_elapses():
    """A full week (or more) since the last digest -- due."""
    now = 1_000_000
    last_sent = now - logic.DIGEST_INTERVAL_DAYS * 86400
    assert logic.is_digest_due(last_sent, now) is True


# --- logic.build_activity_report ------------------------------------------------------


def test_build_activity_report_all_active_returns_the_positive_message(tmp_path, monkeypatch):
    """Nobody past the threshold, nobody unrecorded -> a clear all-good message."""
    _use_tmp_store(tmp_path, monkeypatch)
    now = int(discord.utils.utcnow().timestamp())
    storage.record_activity(1, 100, now)
    guild = _make_guild(1, [_make_member(100)])

    report = asyncio.run(logic.build_activity_report(guild, inactive_days=7))

    assert "active" in report.lower()
    assert "<@100>" not in report


def test_build_activity_report_flags_a_member_past_the_threshold(tmp_path, monkeypatch):
    """A member whose last activity is older than the threshold is listed with their days."""
    _use_tmp_store(tmp_path, monkeypatch)
    now = int(discord.utils.utcnow().timestamp())
    storage.record_activity(1, 100, now - 10 * 86400)
    guild = _make_guild(1, [_make_member(100)])

    report = asyncio.run(logic.build_activity_report(guild, inactive_days=7))

    assert "<@100>" in report
    assert "10 days" in report


def test_build_activity_report_excludes_a_member_under_the_threshold(tmp_path, monkeypatch):
    """A member active more recently than the threshold isn't flagged as inactive."""
    _use_tmp_store(tmp_path, monkeypatch)
    now = int(discord.utils.utcnow().timestamp())
    storage.record_activity(1, 100, now - 2 * 86400)
    guild = _make_guild(1, [_make_member(100)])

    report = asyncio.run(logic.build_activity_report(guild, inactive_days=7))

    assert "<@100>" not in report


def test_build_activity_report_lists_members_with_no_recorded_activity_separately(
    tmp_path, monkeypatch
):
    """A member never recorded (joined before the module was on) gets its own section."""
    _use_tmp_store(tmp_path, monkeypatch)
    guild = _make_guild(1, [_make_member(100)])

    report = asyncio.run(logic.build_activity_report(guild, inactive_days=7))

    assert "<@100>" in report
    assert "No activity recorded" in report


def test_build_activity_report_excludes_bots(tmp_path, monkeypatch):
    """A bot account is never flagged as an inactive human member."""
    _use_tmp_store(tmp_path, monkeypatch)
    guild = _make_guild(1, [_make_member(999, bot=True)])

    report = asyncio.run(logic.build_activity_report(guild, inactive_days=7))

    assert "<@999>" not in report


def test_build_activity_report_sorts_inactive_members_longest_first(tmp_path, monkeypatch):
    """The most-inactive member should be the first one an admin sees."""
    _use_tmp_store(tmp_path, monkeypatch)
    now = int(discord.utils.utcnow().timestamp())
    storage.record_activity(1, 100, now - 8 * 86400)
    storage.record_activity(1, 200, now - 30 * 86400)
    guild = _make_guild(1, [_make_member(100), _make_member(200)])

    report = asyncio.run(logic.build_activity_report(guild, inactive_days=7))

    assert report.index("<@200>") < report.index("<@100>")


# --- handlers ------------------------------------------------------------------------


def test_handle_message_records_the_authors_activity(tmp_path, monkeypatch):
    """A regular message updates that member's last-active timestamp."""
    _use_tmp_store(tmp_path, monkeypatch)
    message = MagicMock()
    message.guild.id = 1
    message.author.id = 100
    message.created_at = discord.utils.utcnow()

    asyncio.run(handlers.handle_message(MagicMock(), message))

    assert 100 in storage.get_last_active(1)


def test_handle_reaction_add_records_activity_and_never_claims(tmp_path, monkeypatch):
    """Real architecture constraint: this handler must always return False, even on
    the happy path, so the module that actually owns a given reaction (RSVP,
    verification approval, translation flags) still gets to run afterward --
    activity tracking is a silent side effect, never a dispatch-stopping claim.
    """
    _use_tmp_store(tmp_path, monkeypatch)
    payload = _make_reaction_payload(100, 1, 10, 42, "✅")

    claimed = asyncio.run(handlers.handle_reaction_add(MagicMock(), payload))

    assert claimed is False
    assert 100 in storage.get_last_active(1)


# --- commands.activityreport -----------------------------------------------------------


def _make_interaction(guild_id=1, user_id=555):
    interaction = MagicMock()
    interaction.guild_id = guild_id
    interaction.guild = _make_guild(guild_id, [])
    interaction.user.id = user_id
    interaction.response.send_message = AsyncMock()
    return interaction


def test_activityreport_rejects_outside_a_server():
    """The guild-only guard mirrors every other admin command in this bot."""
    interaction = _make_interaction(guild_id=None)

    asyncio.run(commands.activityreport.callback(interaction, 7))

    assert "only works inside a server" in interaction.response.send_message.call_args.args[0]


def test_activityreport_replies_ephemerally_with_the_report(tmp_path, monkeypatch):
    """The happy path: the built report is sent back, visible only to the admin."""
    _use_tmp_store(tmp_path, monkeypatch)
    interaction = _make_interaction()

    asyncio.run(commands.activityreport.callback(interaction, 7))

    interaction.response.send_message.assert_awaited_once()
    assert interaction.response.send_message.call_args.kwargs["ephemeral"] is True


# --- scheduler -------------------------------------------------------------------------


def test_process_guild_digest_seeds_silently_on_first_run(tmp_path, monkeypatch):
    """Enabling the module for the first time must not immediately post a digest."""
    _use_tmp_store(tmp_path, monkeypatch)
    core_storage.set_module_enabled(1, "activity", True)
    guild = _make_guild(1, [])
    report_mock = AsyncMock()
    monkeypatch.setattr(scheduler, "report_to_log_channel", report_mock)

    asyncio.run(scheduler._process_guild_digest(MagicMock(), guild, now=1_000_000))

    report_mock.assert_not_awaited()
    assert storage.get_last_digest_sent_at(1) == 1_000_000


def test_process_guild_digest_posts_once_due_and_updates_the_timestamp(tmp_path, monkeypatch):
    """A guild whose interval has elapsed gets its digest posted and the clock reset."""
    _use_tmp_store(tmp_path, monkeypatch)
    core_storage.set_module_enabled(1, "activity", True)
    now = 1_000_000
    storage.set_last_digest_sent_at(1, now - logic.DIGEST_INTERVAL_DAYS * 86400)
    guild = _make_guild(1, [])
    report_mock = AsyncMock()
    monkeypatch.setattr(scheduler, "report_to_log_channel", report_mock)

    asyncio.run(scheduler._process_guild_digest(MagicMock(), guild, now))

    report_mock.assert_awaited_once()
    assert storage.get_last_digest_sent_at(1) == now


def test_process_guild_digest_does_nothing_before_its_due(tmp_path, monkeypatch):
    """A guild digested recently doesn't get a second one before the interval passes."""
    _use_tmp_store(tmp_path, monkeypatch)
    core_storage.set_module_enabled(1, "activity", True)
    now = 1_000_000
    storage.set_last_digest_sent_at(1, now - 1 * 86400)
    guild = _make_guild(1, [])
    report_mock = AsyncMock()
    monkeypatch.setattr(scheduler, "report_to_log_channel", report_mock)

    asyncio.run(scheduler._process_guild_digest(MagicMock(), guild, now))

    report_mock.assert_not_awaited()


def test_process_guild_digest_skips_a_guild_with_the_module_disabled(tmp_path, monkeypatch):
    """A guild that never enabled activity tracking never gets a digest, even if due."""
    _use_tmp_store(tmp_path, monkeypatch)
    now = 1_000_000
    storage.set_last_digest_sent_at(1, now - logic.DIGEST_INTERVAL_DAYS * 86400)
    guild = _make_guild(1, [])
    report_mock = AsyncMock()
    monkeypatch.setattr(scheduler, "report_to_log_channel", report_mock)

    asyncio.run(scheduler._process_guild_digest(MagicMock(), guild, now))

    report_mock.assert_not_awaited()
