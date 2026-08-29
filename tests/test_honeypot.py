"""Tests for the honeypot channel gate: posting there quarantines the author."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from app import honeypot


def _make_message(channel_id=777, author_id=100):
    message = MagicMock()
    message.channel.id = channel_id
    message.author.id = author_id
    message.author.add_roles = AsyncMock()
    message.author.remove_roles = AsyncMock()
    message.author.roles = []
    message.delete = AsyncMock()
    message.guild.get_role = MagicMock(side_effect=lambda role_id: MagicMock(id=role_id))
    return message


def test_noop_when_unconfigured(monkeypatch):
    """No HONEYPOT_CHANNEL_ID -> the gate never claims anything."""
    monkeypatch.setattr(honeypot, "HONEYPOT_CHANNEL_ID", None)
    message = _make_message()

    claimed = asyncio.run(honeypot.handle_honeypot_message(MagicMock(), message))

    assert claimed is False
    message.delete.assert_not_awaited()


def test_noop_outside_the_honeypot_channel(monkeypatch):
    """A message in any other channel passes through untouched."""
    monkeypatch.setattr(honeypot, "HONEYPOT_CHANNEL_ID", 777)
    message = _make_message(channel_id=123)

    claimed = asyncio.run(honeypot.handle_honeypot_message(MagicMock(), message))

    assert claimed is False
    message.delete.assert_not_awaited()


def test_trigger_deletes_quarantines_and_alerts(monkeypatch):
    """The full trap: delete the message, apply subject, strip Member/Verified, alert."""
    monkeypatch.setattr(honeypot, "HONEYPOT_CHANNEL_ID", 777)
    monkeypatch.setattr(honeypot, "SUBJECT_ROLE_ID", 555)
    monkeypatch.setattr(honeypot, "MEMBER_ROLE_ID", 601)
    monkeypatch.setattr(honeypot, "VERIFIED_ROLE_ID", 602)
    report = AsyncMock()
    monkeypatch.setattr(honeypot, "report_to_log_channel", report)
    message = _make_message(channel_id=777, author_id=100)
    member_role = MagicMock(id=601)
    message.author.roles = [member_role]

    claimed = asyncio.run(honeypot.handle_honeypot_message(MagicMock(), message))

    assert claimed is True
    message.delete.assert_awaited_once()
    message.author.add_roles.assert_awaited_once()
    added = message.author.add_roles.await_args.args[0]
    assert added.id == 555
    message.author.remove_roles.assert_awaited_once()
    assert [r.id for r in message.author.remove_roles.await_args.args] == [601]
    report.assert_awaited_once()
    assert "<@100>" in report.await_args.args[1]


def test_failed_delete_still_quarantines(monkeypatch):
    """A delete failure (e.g. race with another mod bot) must not skip the quarantine."""
    monkeypatch.setattr(honeypot, "HONEYPOT_CHANNEL_ID", 777)
    monkeypatch.setattr(honeypot, "SUBJECT_ROLE_ID", 555)
    report = AsyncMock()
    monkeypatch.setattr(honeypot, "report_to_log_channel", report)
    message = _make_message(channel_id=777)
    message.delete = AsyncMock(side_effect=honeypot.discord.HTTPException(MagicMock(), "gone"))

    claimed = asyncio.run(honeypot.handle_honeypot_message(MagicMock(), message))

    assert claimed is True
    message.author.add_roles.assert_awaited_once()
    report.assert_awaited_once()
