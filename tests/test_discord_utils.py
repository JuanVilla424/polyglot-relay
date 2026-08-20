# pylint: disable=protected-access
import asyncio
from unittest.mock import AsyncMock, MagicMock

import discord

from app import discord_utils


def test_resolve_text_channel_returns_a_cached_channel():
    """A channel already in the client's cache is returned without a fetch."""
    channel = MagicMock(spec=discord.TextChannel)
    client = MagicMock(get_channel=MagicMock(return_value=channel))

    resolved = asyncio.run(discord_utils.resolve_text_channel(client, 10))

    assert resolved is channel


def test_resolve_text_channel_falls_back_to_fetch_when_not_cached():
    """An uncached channel is fetched over the API instead of being skipped."""
    channel = MagicMock(spec=discord.TextChannel)
    client = MagicMock(
        get_channel=MagicMock(return_value=None), fetch_channel=AsyncMock(return_value=channel)
    )

    resolved = asyncio.run(discord_utils.resolve_text_channel(client, 10))

    assert resolved is channel


def test_resolve_text_channel_returns_none_when_fetch_fails():
    """A deleted/inaccessible channel returns None instead of raising."""
    response = MagicMock(status=404, reason="Not Found")
    client = MagicMock(
        get_channel=MagicMock(return_value=None),
        fetch_channel=AsyncMock(side_effect=discord.NotFound(response, "Unknown Channel")),
    )

    assert asyncio.run(discord_utils.resolve_text_channel(client, 10)) is None


def test_resolve_text_channel_returns_none_for_a_non_text_channel():
    """A voice channel (or any non-text channel) is rejected, not returned as-is."""
    voice_channel = MagicMock(spec=discord.VoiceChannel)
    client = MagicMock(get_channel=MagicMock(return_value=voice_channel))

    assert asyncio.run(discord_utils.resolve_text_channel(client, 10)) is None


def test_report_to_log_channel_noop_when_unconfigured(monkeypatch):
    """No LOG_CHANNEL_ID set -> the client is never touched (still logs locally, see caller)."""
    monkeypatch.setattr(discord_utils, "LOG_CHANNEL_ID", None)
    client = MagicMock(get_channel=MagicMock(side_effect=AssertionError("should not run")))

    asyncio.run(discord_utils.report_to_log_channel(client, "hello"))


def test_report_to_log_channel_sends_to_configured_channel(monkeypatch):
    """A configured channel receives the message verbatim."""
    monkeypatch.setattr(discord_utils, "LOG_CHANNEL_ID", 999)
    channel = MagicMock()
    channel.send = AsyncMock()
    client = MagicMock(get_channel=MagicMock(return_value=channel))

    asyncio.run(discord_utils.report_to_log_channel(client, "hello"))

    channel.send.assert_awaited_once_with("hello")


def test_report_to_log_channel_swallows_send_failures(monkeypatch):
    """A permission error posting to the log channel never propagates to the caller."""
    monkeypatch.setattr(discord_utils, "LOG_CHANNEL_ID", 999)
    response = MagicMock(status=403, reason="Forbidden")
    channel = MagicMock()
    channel.send = AsyncMock(side_effect=discord.Forbidden(response, "missing permissions"))
    client = MagicMock(get_channel=MagicMock(return_value=channel))

    asyncio.run(discord_utils.report_to_log_channel(client, "hello"))  # must not raise
