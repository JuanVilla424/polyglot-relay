import asyncio
import datetime as dt
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from app import storage as core_storage
from app.modules.polls import commands, logic


def _use_tmp_store(tmp_path, monkeypatch):
    monkeypatch.setattr(core_storage, "DATA_DIR", tmp_path)
    monkeypatch.setattr(core_storage, "ENABLED_MODULES_PATH", tmp_path / "enabled_modules.json")


# --- logic.parse_poll_options --------------------------------------------------------


def test_parse_poll_options_splits_trims_and_drops_empties():
    """A normal "; "-separated string becomes a clean list of options."""
    assert logic.parse_poll_options("Yes ; No ;  Maybe") == ["Yes", "No", "Maybe"]


def test_parse_poll_options_rejects_fewer_than_two():
    """A single option isn't a real poll."""
    with pytest.raises(ValueError, match="at least 2"):
        logic.parse_poll_options("Only one")


def test_parse_poll_options_rejects_more_than_ten():
    """Discord's own poll API caps answers at 10."""
    raw = "; ".join(f"Option {i}" for i in range(11))
    with pytest.raises(ValueError, match="up to 10"):
        logic.parse_poll_options(raw)


def test_parse_poll_options_rejects_an_answer_over_the_length_limit():
    """Discord rejects any answer over 55 characters -- caught here with a clear message."""
    raw = f"Yes; {'x' * 56}"
    with pytest.raises(ValueError, match="55 characters"):
        logic.parse_poll_options(raw)


def test_parse_poll_options_accepts_an_answer_at_exactly_the_length_limit():
    """The boundary itself (55 chars) is valid, not rejected."""
    raw = f"Yes; {'x' * 55}"
    assert logic.parse_poll_options(raw) == ["Yes", "x" * 55]


# --- logic.build_poll -----------------------------------------------------------------


def test_build_poll_sets_the_question_duration_and_answers():
    """A real discord.Poll object (local construction, no network call) with the right shape."""
    poll = logic.build_poll("Attack at dawn or dusk?", ["Dawn", "Dusk"], duration_hours=8)

    assert poll.question == "Attack at dawn or dusk?"
    assert poll.duration == dt.timedelta(hours=8)
    assert poll.multiple is False
    assert [answer.text for answer in poll.answers] == ["Dawn", "Dusk"]


# --- commands.createpoll ---------------------------------------------------------------


def _make_interaction(guild_id=1, channel_id=10, user_id=555):
    interaction = MagicMock()
    interaction.guild_id = guild_id
    interaction.channel_id = channel_id
    interaction.user.id = user_id
    interaction.response.send_message = AsyncMock()
    return interaction


def test_createpoll_rejects_outside_a_server():
    """The guild-only guard mirrors createvent's -- no DM usage."""
    interaction = _make_interaction(guild_id=None)

    asyncio.run(commands.createpoll.callback(interaction, "Q?", "A; B", 24))

    assert "only works inside a server" in interaction.response.send_message.call_args.args[0]


def test_createpoll_rejects_invalid_options_without_sending_a_poll(tmp_path, monkeypatch):
    """A malformed options string is reported back to the admin, no poll ever sent."""
    _use_tmp_store(tmp_path, monkeypatch)
    interaction = _make_interaction()

    asyncio.run(commands.createpoll.callback(interaction, "Q?", "Only one", 24))

    interaction.response.send_message.assert_awaited_once()
    assert "at least 2" in interaction.response.send_message.call_args.args[0]
    assert "poll" not in interaction.response.send_message.call_args.kwargs


def test_createpoll_posts_the_poll_and_reports_to_the_log_channel(tmp_path, monkeypatch):
    """The full happy path: a real Poll is sent as the interaction response, and logged."""
    _use_tmp_store(tmp_path, monkeypatch)
    interaction = _make_interaction()
    report_mock = AsyncMock()
    monkeypatch.setattr(commands, "report_to_log_channel", report_mock)

    asyncio.run(commands.createpoll.callback(interaction, "Attack at dawn?", "Yes; No", 12))

    interaction.response.send_message.assert_awaited_once()
    sent_poll = interaction.response.send_message.call_args.kwargs["poll"]
    assert isinstance(sent_poll, discord.Poll)
    assert sent_poll.question == "Attack at dawn?"
    assert sent_poll.duration == dt.timedelta(hours=12)
    report_mock.assert_awaited_once()
    sent_text = report_mock.call_args.args[1]
    assert "555" in sent_text
    assert "Attack at dawn?" in sent_text


def test_createpoll_defaults_to_the_default_duration_when_not_specified(tmp_path, monkeypatch):
    """Not passing duration_hours falls back to the module's default."""
    _use_tmp_store(tmp_path, monkeypatch)
    interaction = _make_interaction()
    monkeypatch.setattr(commands, "report_to_log_channel", AsyncMock())

    asyncio.run(commands.createpoll.callback(interaction, "Q?", "A; B"))

    sent_poll = interaction.response.send_message.call_args.kwargs["poll"]
    assert sent_poll.duration == dt.timedelta(hours=logic.DEFAULT_POLL_DURATION_HOURS)


# --- commands.end_poll (context menu) ---------------------------------------------------


def _make_poll_message(poll):
    message = MagicMock()
    message.poll = poll
    message.end_poll = AsyncMock()
    return message


def test_end_poll_reports_when_the_message_has_no_poll(tmp_path, monkeypatch):
    """Right-clicking a random message that isn't a poll is reported clearly."""
    _use_tmp_store(tmp_path, monkeypatch)
    interaction = _make_interaction()
    message = _make_poll_message(poll=None)

    asyncio.run(commands.end_poll.callback(interaction, message))

    message.end_poll.assert_not_awaited()
    assert "doesn't have an active poll" in interaction.response.send_message.call_args.args[0]


def test_end_poll_ends_the_poll_and_reports_to_the_log_channel(tmp_path, monkeypatch):
    """The happy path: a real active poll gets ended, and the action is logged."""
    _use_tmp_store(tmp_path, monkeypatch)
    interaction = _make_interaction()
    report_mock = AsyncMock()
    monkeypatch.setattr(commands, "report_to_log_channel", report_mock)
    poll = logic.build_poll("Attack at dawn?", ["Yes", "No"], duration_hours=24)
    message = _make_poll_message(poll=poll)

    asyncio.run(commands.end_poll.callback(interaction, message))

    message.end_poll.assert_awaited_once()
    interaction.response.send_message.assert_awaited_once_with("Poll ended.", ephemeral=True)
    report_mock.assert_awaited_once()
    sent_text = report_mock.call_args.args[1]
    assert "555" in sent_text
    assert "Attack at dawn?" in sent_text


def test_end_poll_reports_a_friendly_error_when_discord_rejects_it(tmp_path, monkeypatch):
    """Real case: the poll already ended on its own -- must not raise, just report cleanly."""
    _use_tmp_store(tmp_path, monkeypatch)
    interaction = _make_interaction()
    poll = logic.build_poll("Q?", ["A", "B"], duration_hours=24)
    message = _make_poll_message(poll=poll)
    response = MagicMock(status=400, reason="Bad Request")
    message.end_poll = AsyncMock(side_effect=discord.HTTPException(response, "poll already ended"))

    asyncio.run(commands.end_poll.callback(interaction, message))

    assert "already ended" in interaction.response.send_message.call_args.args[0]
