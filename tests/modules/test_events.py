# pylint: disable=protected-access
import asyncio
import datetime as dt
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from app import storage as core_storage
from app.modules.checks import ModuleDisabledError, module_enabled_predicate
from app.modules.events import commands, handlers, logic, scheduler, storage, views


def _use_tmp_store(tmp_path, monkeypatch):
    monkeypatch.setattr(core_storage, "DATA_DIR", tmp_path)
    monkeypatch.setattr(core_storage, "ENABLED_MODULES_PATH", tmp_path / "enabled_modules.json")
    monkeypatch.setattr(storage, "EVENTS_PATH", tmp_path / "events.json")
    monkeypatch.setattr(
        storage, "GAME_EVENT_ANNOUNCEMENTS_PATH", tmp_path / "game_event_announcements.json"
    )
    monkeypatch.setattr(storage, "CANCELLED_EVENTS_PATH", tmp_path / "cancelled_events.json")


def _make_event(guild_id=1, channel_id=10, timestamp=9_999_999_999, **overrides):
    event = {
        "guild_id": guild_id,
        "channel_id": channel_id,
        "title": "Conquest of Level 1 Pass",
        "description": "Coordinates: X:413 Y:740",
        "image_url": None,
        "timestamp": timestamp,
        "created_by": 1,
        "rsvps": {},
        "reminders_sent": [],
    }
    event.update(overrides)
    return event


def _make_announcement(guild_id=1, channel_id=10, timestamp=9_999_999_999, **overrides):
    announcement = {
        "guild_id": guild_id,
        "channel_id": channel_id,
        "title": "Strongest Lord",
        "timestamp": timestamp,
        "reminder_minutes_before": 30,
        "duration_minutes": 60,
        "reminded": False,
        "discord_event_id": None,
    }
    announcement.update(overrides)
    return announcement


def _make_reaction_payload(user_id, guild_id, channel_id, message_id, emoji):
    payload = MagicMock()
    payload.user_id = user_id
    payload.guild_id = guild_id
    payload.channel_id = channel_id
    payload.message_id = message_id
    payload.emoji = discord.PartialEmoji(name=emoji)
    return payload


# --- storage.save_announcement / get_announcement / all_announcements ----------------


def test_save_and_get_announcement_round_trips(tmp_path, monkeypatch):
    """A saved announcement reads back exactly as stored."""
    _use_tmp_store(tmp_path, monkeypatch)
    storage.save_announcement(42, _make_announcement(title="Strongest Lord"))

    saved = storage.get_announcement(42)

    assert saved["title"] == "Strongest Lord"


def test_get_announcement_returns_none_when_not_tracked(tmp_path, monkeypatch):
    """A message that was never a tracked announcement returns None, not an error."""
    _use_tmp_store(tmp_path, monkeypatch)

    assert storage.get_announcement(999) is None


def test_all_announcements_returns_every_tracked_announcement(tmp_path, monkeypatch):
    """Every saved announcement shows up, keyed by its message id."""
    _use_tmp_store(tmp_path, monkeypatch)
    storage.save_announcement(1, _make_announcement(title="A"))
    storage.save_announcement(2, _make_announcement(title="B"))

    assert set(storage.all_announcements().keys()) == {"1", "2"}


# --- storage.record_cancellation / pop_recent_cancellation ----------------------------


def test_pop_recent_cancellation_matches_and_consumes_the_record(tmp_path, monkeypatch):
    """A recorded cancellation matches once, then is consumed -- only the first
    re-creation of that title announces as rescheduled."""
    _use_tmp_store(tmp_path, monkeypatch)
    storage.record_cancellation(1, "necrogiant capture", 1000, 100)

    assert storage.pop_recent_cancellation(1, "necrogiant capture", 1050, 100) is True
    assert storage.pop_recent_cancellation(1, "necrogiant capture", 1050, 100) is False


def test_pop_recent_cancellation_ignores_expired_records(tmp_path, monkeypatch):
    """A cancellation older than the window is not a reschedule -- it's a new event."""
    _use_tmp_store(tmp_path, monkeypatch)
    storage.record_cancellation(1, "Rally", 1000, 100)

    assert storage.pop_recent_cancellation(1, "Rally", 1101, 100) is False


def test_pop_recent_cancellation_normalizes_the_title(tmp_path, monkeypatch):
    """Retyped titles still match: case and surrounding whitespace are ignored."""
    _use_tmp_store(tmp_path, monkeypatch)
    storage.record_cancellation(1, "necrogiant capture", 1000, 100)

    assert storage.pop_recent_cancellation(1, "  Necrogiant CAPTURE ", 1050, 100) is True


def test_pop_recent_cancellation_is_scoped_per_guild(tmp_path, monkeypatch):
    """A cancellation in one server never marks another server's event as rescheduled."""
    _use_tmp_store(tmp_path, monkeypatch)
    storage.record_cancellation(1, "Rally", 1000, 100)

    assert storage.pop_recent_cancellation(2, "Rally", 1050, 100) is False


def test_record_cancellation_prunes_expired_records(tmp_path, monkeypatch):
    """Old records don't pile up in the store forever -- each write prunes them."""
    _use_tmp_store(tmp_path, monkeypatch)
    storage.record_cancellation(1, "Old", 1000, 100)
    storage.record_cancellation(1, "New", 2000, 100)

    data = core_storage.read_json(storage.CANCELLED_EVENTS_PATH)
    assert "old" not in data.get("1", {})
    assert "new" in data.get("1", {})


# --- logic.parse_event_timestamp -------------------------------------------------


def test_parse_event_timestamp_accepts_a_valid_future_date():
    """A well-formed date/time/offset in the future parses to a unix timestamp."""
    timestamp = logic.parse_event_timestamp("2099-01-01", "18:00", "0")

    assert isinstance(timestamp, int)
    assert timestamp > 0


def test_parse_event_timestamp_rejects_a_malformed_date():
    """A date not in YYYY-MM-DD form is rejected with a clear message."""
    with pytest.raises(ValueError, match="valid date"):
        logic.parse_event_timestamp("01-01-2099", "18:00", "0")


def test_parse_event_timestamp_rejects_a_malformed_time():
    """A time not in 24h HH:MM form is rejected with a clear message."""
    with pytest.raises(ValueError, match="valid time"):
        logic.parse_event_timestamp("2099-01-01", "6pm", "0")


def test_parse_event_timestamp_rejects_a_non_numeric_offset():
    """A UTC offset given as a timezone name (not a number) is rejected."""
    with pytest.raises(ValueError, match="UTC offset"):
        logic.parse_event_timestamp("2099-01-01", "18:00", "EST")


def test_parse_event_timestamp_rejects_an_out_of_range_offset():
    """A UTC offset outside -12..+14 is rejected."""
    with pytest.raises(ValueError, match="out of range"):
        logic.parse_event_timestamp("2099-01-01", "18:00", "99")


def test_parse_event_timestamp_rejects_a_date_already_in_the_past():
    """A well-formed date/time that's already elapsed is rejected."""
    with pytest.raises(ValueError, match="already in the past"):
        logic.parse_event_timestamp("2020-01-01", "12:00", "0")


def test_parse_event_timestamp_accounts_for_the_utc_offset():
    """The same clock time at different offsets produces different unix timestamps."""
    utc = logic.parse_event_timestamp("2099-06-01", "12:00", "0")
    plus_two = logic.parse_event_timestamp("2099-06-01", "12:00", "2")

    assert plus_two < utc  # UTC+2 at noon is earlier in absolute time than UTC noon


# --- logic.pending_reminder_offsets -----------------------------------------------


def test_pending_reminder_offsets_all_pending_for_a_far_future_event():
    """An event created well over an hour out has every offset still ahead of it."""
    created_at = 0
    event_timestamp = created_at + 3 * 3600  # 3 hours out

    assert logic.pending_reminder_offsets(created_at, event_timestamp) == [60, 30, 10, 0]


def test_pending_reminder_offsets_drops_offsets_already_elapsed_at_creation():
    """An event created 20 minutes out: the 60/30-minute marks are already in the past."""
    created_at = 0
    event_timestamp = created_at + 20 * 60

    assert logic.pending_reminder_offsets(created_at, event_timestamp) == [10, 0]


def test_pending_reminder_offsets_empty_for_an_event_created_at_zero_notice():
    """Created right at (or past) the event's own time -- nothing left to remind about."""
    created_at = 1000
    event_timestamp = 1000

    assert logic.pending_reminder_offsets(created_at, event_timestamp) == []


# --- logic.make_event_embed ---------------------------------------------------------


def test_make_event_embed_includes_title_description_and_time():
    """The embed surfaces the event's title, description, and a When field."""
    event = _make_event(title="Rally Point", description="Bring siege")

    embed = logic.make_event_embed(event)

    assert embed.title == "Rally Point"
    assert embed.description == "Bring siege"
    assert any("When" in (f.name or "") for f in embed.fields)


def test_make_event_embed_groups_rsvps_by_status():
    """Going/maybe/not-going each get their own field, with a count and mentions."""
    event = _make_event(rsvps={"1": "going", "2": "going", "3": "maybe"})

    embed = logic.make_event_embed(event)

    going_field = next(f for f in embed.fields if "Going" in f.name)
    maybe_field = next(f for f in embed.fields if "Maybe" in f.name)
    assert "(2)" in going_field.name
    assert "<@1>" in going_field.value and "<@2>" in going_field.value
    assert "(1)" in maybe_field.name and "<@3>" in maybe_field.value


def test_make_event_embed_sets_image_when_present():
    """An event created with an image gets it set as the embed's image."""
    event = _make_event(image_url="https://cdn.discordapp.com/attachments/x/y/z.png")

    embed = logic.make_event_embed(event)

    assert embed.image.url == "https://cdn.discordapp.com/attachments/x/y/z.png"


def test_make_event_embed_omits_image_when_include_image_is_false():
    """Real bug: RSVP re-renders that also set the image made Discord show it
    twice (the original upload stays visible as the message's own attachment).
    """
    event = _make_event(image_url="https://cdn.discordapp.com/attachments/x/y/z.png")

    embed = logic.make_event_embed(event, include_image=False)

    assert embed.image.url is None


# --- logic.create_scheduled_event / cancel_scheduled_event ---------------------------


def test_create_scheduled_event_calls_the_discord_api_with_external_entity_type():
    """A native Discord Scheduled Event is created alongside the bot's own embed."""
    event = _make_event(
        title="Rally Point", description="Bring siege", timestamp=9_999_999_999, duration_minutes=90
    )
    guild = MagicMock()
    scheduled_event = MagicMock(id=42)
    guild.create_scheduled_event = AsyncMock(return_value=scheduled_event)

    result = asyncio.run(logic.create_scheduled_event(guild, event, image_bytes=b"png-bytes"))

    assert result is scheduled_event
    guild.create_scheduled_event.assert_awaited_once()
    kwargs = guild.create_scheduled_event.call_args.kwargs
    assert kwargs["name"] == "Rally Point"
    assert kwargs["entity_type"] == discord.EntityType.external
    assert kwargs["location"] == logic.EVENT_LOCATION
    assert kwargs["privacy_level"] == discord.PrivacyLevel.guild_only
    assert kwargs["image"] == b"png-bytes"
    assert kwargs["end_time"] - kwargs["start_time"] == dt.timedelta(minutes=90)


def test_create_scheduled_event_omits_the_image_kwarg_when_there_is_no_image():
    """Real bug: discord.py tries to base64-encode `image` even when it's
    explicitly None and crashes with AttributeError -- the kwarg must be left
    out entirely for an event with no picture, not passed as None.
    """
    event = _make_event(timestamp=9_999_999_999, duration_minutes=60)
    guild = MagicMock()
    guild.create_scheduled_event = AsyncMock(return_value=MagicMock(id=1))

    asyncio.run(logic.create_scheduled_event(guild, event, image_bytes=None))

    assert "image" not in guild.create_scheduled_event.call_args.kwargs


def test_create_scheduled_event_falls_back_to_the_default_duration_when_missing():
    """Real case: events created before this feature existed have no stored
    duration_minutes at all -- must not KeyError, just use the default.
    """
    event = _make_event(timestamp=9_999_999_999)
    assert "duration_minutes" not in event
    guild = MagicMock()
    guild.create_scheduled_event = AsyncMock(return_value=MagicMock(id=1))

    asyncio.run(logic.create_scheduled_event(guild, event, image_bytes=None))

    kwargs = guild.create_scheduled_event.call_args.kwargs
    assert kwargs["end_time"] - kwargs["start_time"] == dt.timedelta(
        minutes=logic.DEFAULT_EVENT_DURATION_MINUTES
    )


def test_create_scheduled_event_returns_none_when_forbidden():
    """Missing Manage Events permission doesn't block the rest of event creation."""
    event = _make_event(duration_minutes=60)
    guild = MagicMock()
    response = MagicMock(status=403, reason="Forbidden")
    guild.create_scheduled_event = AsyncMock(
        side_effect=discord.Forbidden(response, "missing access")
    )

    result = asyncio.run(logic.create_scheduled_event(guild, event, image_bytes=None))

    assert result is None


def test_cancel_scheduled_event_cancels_the_fetched_event():
    """Cancelling the bot's event also cancels the linked native Discord event."""
    guild = MagicMock()
    scheduled_event = MagicMock()
    scheduled_event.cancel = AsyncMock()
    guild.fetch_scheduled_event = AsyncMock(return_value=scheduled_event)

    asyncio.run(logic.cancel_scheduled_event(guild, 42))

    guild.fetch_scheduled_event.assert_awaited_once_with(42)
    scheduled_event.cancel.assert_awaited_once()


def test_cancel_scheduled_event_is_best_effort_on_failure():
    """A native event already deleted by hand doesn't blow up cancellation."""
    guild = MagicMock()
    response = MagicMock(status=404, reason="Not Found")
    guild.fetch_scheduled_event = AsyncMock(
        side_effect=discord.NotFound(response, "Unknown Scheduled Event")
    )

    asyncio.run(logic.cancel_scheduled_event(guild, 42))  # must not raise


# --- app.modules.checks.require_enabled ---------------------------------------------


def test_require_enabled_raises_when_module_disabled(tmp_path, monkeypatch):
    """A guild that never enabled events gets ModuleDisabledError from the predicate."""
    _use_tmp_store(tmp_path, monkeypatch)
    predicate = module_enabled_predicate("events")
    interaction = MagicMock()
    interaction.guild_id = 1

    with pytest.raises(ModuleDisabledError):
        asyncio.run(predicate(interaction))


def test_require_enabled_passes_when_module_enabled(tmp_path, monkeypatch):
    """An explicit enable lets the predicate pass."""
    _use_tmp_store(tmp_path, monkeypatch)
    core_storage.set_module_enabled(1, "events", True)
    predicate = module_enabled_predicate("events")
    interaction = MagicMock()
    interaction.guild_id = 1

    assert asyncio.run(predicate(interaction)) is True


# --- logic.build_announcement_text / build_reminder_text -----------------------------


def test_build_announcement_text_includes_title_and_native_timestamp():
    """The immediate announcement is informational, not urgent -- no @everyone ping.

    Only the reminder (build_reminder_text), sent right before the event
    starts, is worth interrupting everyone for.
    """
    text = logic.build_announcement_text("Strongest Lord", 9_999_999_999)

    assert "@everyone" not in text
    assert "Strongest Lord" in text
    assert "<t:9999999999:F>" in text
    assert "<t:9999999999:R>" in text


def test_build_reminder_text_includes_title_and_native_timestamp():
    """The reminder also pings everyone and shows a relative native timestamp."""
    text = logic.build_reminder_text("Strongest Lord", 9_999_999_999)

    assert "@everyone" in text
    assert "Strongest Lord" in text
    assert "<t:9999999999:R>" in text


def test_build_reschedule_text_says_rescheduled_without_pinging_everyone():
    """A reschedule is informational too -- the new date is shown, nobody gets pinged."""
    text = logic.build_reschedule_text("necrogiant capture", 9_999_999_999)

    assert "@everyone" not in text
    assert "necrogiant capture" in text
    assert "rescheduled" in text
    assert "<t:9999999999:F>" in text
    assert "<t:9999999999:R>" in text


# --- logic.cancel_event_and_notify ----------------------------------------------------


def test_cancel_event_and_notify_announces_without_pinging_everyone(tmp_path, monkeypatch):
    """The cancellation notice stays informational -- only reminders ping @everyone."""
    _use_tmp_store(tmp_path, monkeypatch)
    storage.save_event(42, _make_event(title="Rally"))
    sent_texts = []

    async def _capture(_client, text):
        sent_texts.append(text)
        return MagicMock()

    monkeypatch.setattr(logic, "send_to_announcements_channel", _capture)
    monkeypatch.setattr(logic, "report_to_log_channel", AsyncMock())
    message = MagicMock()
    message.id = 42
    message.reply = AsyncMock()

    asyncio.run(logic.cancel_event_and_notify(MagicMock(), message, 555))

    assert sent_texts == ["🚫 **Rally** was cancelled."]


def test_cancel_event_and_notify_records_the_cancellation_for_reschedule_matching(
    tmp_path, monkeypatch
):
    """Cancelling leaves a record so re-creating the same title announces as rescheduled."""
    _use_tmp_store(tmp_path, monkeypatch)
    storage.save_event(42, _make_event(guild_id=7, title="Rally"))
    monkeypatch.setattr(logic, "send_to_announcements_channel", AsyncMock())
    monkeypatch.setattr(logic, "report_to_log_channel", AsyncMock())
    message = MagicMock()
    message.id = 42
    message.reply = AsyncMock()

    asyncio.run(logic.cancel_event_and_notify(MagicMock(), message, 555))

    now = int(discord.utils.utcnow().timestamp())
    assert storage.pop_recent_cancellation(7, "Rally", now, logic.RESCHEDULE_WINDOW_SECONDS)


# --- logic.send_to_announcements_channel ----------------------------------------------


def test_send_to_announcements_channel_noop_when_unconfigured(monkeypatch):
    """No ANNOUNCEMENTS_CHANNEL_ID set -> the client is never touched, returns None."""
    monkeypatch.setattr(logic, "ANNOUNCEMENTS_CHANNEL_ID", None)
    client = MagicMock(get_channel=MagicMock(side_effect=AssertionError("should not run")))

    result = asyncio.run(logic.send_to_announcements_channel(client, "hello"))

    assert result is None


def test_send_to_announcements_channel_sends_to_the_configured_channel(monkeypatch):
    """A configured channel gets the exact text sent, with allowed_mentions for @everyone."""
    monkeypatch.setattr(logic, "ANNOUNCEMENTS_CHANNEL_ID", 999)
    channel = MagicMock(spec=discord.TextChannel)
    sent_message = MagicMock()
    channel.send = AsyncMock(return_value=sent_message)
    client = MagicMock(get_channel=MagicMock(return_value=channel))

    result = asyncio.run(logic.send_to_announcements_channel(client, "@everyone hi"))

    assert result is sent_message
    channel.send.assert_awaited_once()
    assert channel.send.call_args.args[0] == "@everyone hi"
    assert channel.send.call_args.kwargs["allowed_mentions"].everyone is True


def test_send_to_announcements_channel_swallows_send_failures(monkeypatch):
    """A permission error posting never propagates to the caller, returns None."""
    monkeypatch.setattr(logic, "ANNOUNCEMENTS_CHANNEL_ID", 999)
    channel = MagicMock(spec=discord.TextChannel)
    response = MagicMock(status=403, reason="Forbidden")
    channel.send = AsyncMock(side_effect=discord.Forbidden(response, "missing permissions"))
    client = MagicMock(get_channel=MagicMock(return_value=channel))

    result = asyncio.run(logic.send_to_announcements_channel(client, "hi"))  # must not raise

    assert result is None


# --- commands.createvent / listevents / cancel_event ---------------------------------


def test_createvent_rejects_an_invalid_date(tmp_path, monkeypatch):
    """A bad date is reported back to the admin instead of creating a broken event."""
    _use_tmp_store(tmp_path, monkeypatch)
    interaction = MagicMock()
    interaction.guild_id = 1
    interaction.response.send_message = AsyncMock()

    asyncio.run(commands.createvent.callback(interaction, "Title", "not-a-date", "18:00", "0"))

    interaction.response.send_message.assert_awaited_once()
    assert "valid date" in interaction.response.send_message.call_args.args[0]


def test_createvent_posts_the_embed_adds_rsvp_reactions_and_saves_the_event(tmp_path, monkeypatch):
    """The full happy path: embed posted, RSVP flags added, event tracked in storage."""
    _use_tmp_store(tmp_path, monkeypatch)
    interaction = MagicMock()
    interaction.guild_id = 1
    interaction.channel_id = 10
    interaction.user.id = 555
    interaction.response.send_message = AsyncMock()
    interaction.guild.create_scheduled_event = AsyncMock(return_value=MagicMock(id=888))
    sent_message = MagicMock()
    sent_message.id = 777
    sent_message.embeds = []
    sent_message.add_reaction = AsyncMock()
    interaction.original_response = AsyncMock(return_value=sent_message)

    asyncio.run(
        commands.createvent.callback(
            interaction, "Rally Point", "2099-01-01", "18:00", "0", 60, "Bring siege", None
        )
    )

    interaction.response.send_message.assert_awaited_once()
    assert sent_message.add_reaction.await_count == len(logic.RSVP_EMOJIS)
    saved = storage.get_event(777)
    assert saved["title"] == "Rally Point"
    assert saved["guild_id"] == 1
    assert saved["created_by"] == 555
    assert saved["duration_minutes"] == 60
    assert saved["discord_event_id"] == 888


def test_createvent_pre_marks_reminders_already_elapsed_at_creation(tmp_path, monkeypatch):
    """Creating an event with only 5 minutes' notice shouldn't queue the 60/30-minute reminders."""
    _use_tmp_store(tmp_path, monkeypatch)
    interaction = MagicMock()
    interaction.guild_id = 1
    interaction.channel_id = 10
    interaction.user.id = 555
    interaction.response.send_message = AsyncMock()
    interaction.guild.create_scheduled_event = AsyncMock(return_value=MagicMock(id=889))
    sent_message = MagicMock()
    sent_message.id = 888
    sent_message.embeds = []
    sent_message.add_reaction = AsyncMock()
    interaction.original_response = AsyncMock(return_value=sent_message)

    near_future = discord.utils.utcnow().timestamp() + 5 * 60
    when = dt.datetime.fromtimestamp(near_future, tz=dt.timezone.utc)

    asyncio.run(
        commands.createvent.callback(
            interaction,
            "Soon",
            when.strftime("%Y-%m-%d"),
            when.strftime("%H:%M"),
            "0",
        )
    )

    # 5 minutes' notice: the 60/30/10-minute marks are all already in the past
    # at creation time -- only the "at the event" (0) mark is still ahead.
    saved = storage.get_event(888)
    assert saved["reminders_sent"] == [60, 30, 10]


def test_listevents_reports_no_upcoming_events_when_empty(tmp_path, monkeypatch):
    """No events tracked for this guild -> a clear "nothing here" message, not a blank list."""
    _use_tmp_store(tmp_path, monkeypatch)
    interaction = MagicMock()
    interaction.guild_id = 1
    interaction.response.send_message = AsyncMock()

    asyncio.run(commands.listevents.callback(interaction))

    assert "No upcoming events" in interaction.response.send_message.call_args.args[0]


def test_listevents_lists_upcoming_events_soonest_first(tmp_path, monkeypatch):
    """Multiple events are sorted chronologically, not by insertion order."""
    _use_tmp_store(tmp_path, monkeypatch)
    storage.save_event(1, _make_event(timestamp=9_999_999_999, **{"title": "Later"}))
    storage.save_event(2, _make_event(timestamp=9_999_999_000, **{"title": "Sooner"}))
    interaction = MagicMock()
    interaction.guild_id = 1
    interaction.response.send_message = AsyncMock()

    asyncio.run(commands.listevents.callback(interaction))

    sent = interaction.response.send_message.call_args.args[0]
    assert sent.index("Sooner") < sent.index("Later")


def test_listevents_excludes_other_guilds_events(tmp_path, monkeypatch):
    """An event tracked for a different guild never leaks into this one's list."""
    _use_tmp_store(tmp_path, monkeypatch)
    storage.save_event(1, _make_event(guild_id=2, title="Other server's event"))
    interaction = MagicMock()
    interaction.guild_id = 1
    interaction.response.send_message = AsyncMock()

    asyncio.run(commands.listevents.callback(interaction))

    assert "No upcoming events" in interaction.response.send_message.call_args.args[0]


def test_cancel_event_removes_a_tracked_event(tmp_path, monkeypatch):
    """Cancelling a real event stops tracking it and posts a cancellation notice."""
    _use_tmp_store(tmp_path, monkeypatch)
    storage.save_event(42, _make_event())
    interaction = MagicMock()
    interaction.response.send_message = AsyncMock()
    message = MagicMock()
    message.id = 42
    message.reply = AsyncMock()

    asyncio.run(commands.cancel_event.callback(interaction, message))

    assert storage.get_event(42) is None
    message.reply.assert_awaited_once()


def test_cancel_event_reports_when_message_is_not_a_tracked_event(tmp_path, monkeypatch):
    """Right-clicking a random message that isn't an event is reported clearly, not silently."""
    _use_tmp_store(tmp_path, monkeypatch)
    interaction = MagicMock()
    interaction.response.send_message = AsyncMock()
    message = MagicMock()
    message.id = 999

    asyncio.run(commands.cancel_event.callback(interaction, message))

    assert "isn't a tracked event" in interaction.response.send_message.call_args.args[0]


# --- commands.createvent -> announcements channel --------------------------------------


def _make_createvent_interaction():
    interaction = MagicMock()
    interaction.guild_id = 1
    interaction.channel_id = 10
    interaction.user.id = 555
    interaction.response.send_message = AsyncMock()
    interaction.guild.create_scheduled_event = AsyncMock(return_value=MagicMock(id=888))
    sent_message = MagicMock()
    sent_message.id = 777
    sent_message.embeds = []
    sent_message.jump_url = "https://discord.com/channels/1/10/777"
    sent_message.add_reaction = AsyncMock()
    interaction.original_response = AsyncMock(return_value=sent_message)
    return interaction


def _capture_announcements(monkeypatch):
    sent_texts = []

    async def _capture(_client, text):
        sent_texts.append(text)
        return MagicMock()

    monkeypatch.setattr(commands, "send_to_announcements_channel", _capture)
    return sent_texts


def test_createvent_announces_the_schedule_to_the_announcements_channel(tmp_path, monkeypatch):
    """Creating an event posts an informational line in announcements -- no @everyone,
    with a jump link straight to the RSVP embed."""
    _use_tmp_store(tmp_path, monkeypatch)
    monkeypatch.setattr(commands, "ANNOUNCEMENTS_CHANNEL_ID", 999)
    sent_texts = _capture_announcements(monkeypatch)
    interaction = _make_createvent_interaction()

    asyncio.run(
        commands.createvent.callback(interaction, "Rally Point", "2099-01-01", "18:00", "0")
    )

    assert len(sent_texts) == 1
    assert "Rally Point" in sent_texts[0]
    assert "@everyone" not in sent_texts[0]
    assert "rescheduled" not in sent_texts[0]
    assert "https://discord.com/channels/1/10/777" in sent_texts[0]


def test_createvent_announces_a_reschedule_when_the_same_title_was_just_cancelled(
    tmp_path, monkeypatch
):
    """Cancel + re-create with the same title reads as a reschedule, not a new event,
    and the cancellation record is consumed by the match."""
    _use_tmp_store(tmp_path, monkeypatch)
    monkeypatch.setattr(commands, "ANNOUNCEMENTS_CHANNEL_ID", 999)
    sent_texts = _capture_announcements(monkeypatch)
    now = int(discord.utils.utcnow().timestamp())
    storage.record_cancellation(1, "Rally Point", now, logic.RESCHEDULE_WINDOW_SECONDS)
    interaction = _make_createvent_interaction()

    asyncio.run(
        commands.createvent.callback(interaction, "Rally Point", "2099-01-01", "18:00", "0")
    )

    assert len(sent_texts) == 1
    assert "was rescheduled" in sent_texts[0]
    assert "@everyone" not in sent_texts[0]
    assert not storage.pop_recent_cancellation(
        1, "Rally Point", now, logic.RESCHEDULE_WINDOW_SECONDS
    )


def test_createvent_skips_the_announcement_inside_the_announcements_channel(tmp_path, monkeypatch):
    """An event created in the announcements channel itself isn't announced twice."""
    _use_tmp_store(tmp_path, monkeypatch)
    monkeypatch.setattr(commands, "ANNOUNCEMENTS_CHANNEL_ID", 10)
    sent_texts = _capture_announcements(monkeypatch)
    interaction = _make_createvent_interaction()

    asyncio.run(
        commands.createvent.callback(interaction, "Rally Point", "2099-01-01", "18:00", "0")
    )

    assert not sent_texts


# --- commands.announceevent -----------------------------------------------------------


def test_announceevent_rejects_outside_a_server(tmp_path, monkeypatch):
    """The guild-only guard mirrors createvent's -- no DM usage."""
    _use_tmp_store(tmp_path, monkeypatch)
    monkeypatch.setattr(commands, "ANNOUNCEMENTS_CHANNEL_ID", 999)
    interaction = MagicMock()
    interaction.guild_id = None
    interaction.response.send_message = AsyncMock()

    asyncio.run(
        commands.announceevent.callback(interaction, "Strongest Lord", "2099-01-01", "18:00", "0")
    )

    assert "only works inside a server" in interaction.response.send_message.call_args.args[0]


def test_announceevent_rejects_when_announcements_channel_unconfigured(tmp_path, monkeypatch):
    """Without ANNOUNCEMENTS_CHANNEL_ID set, this command has nothing to do -- say so clearly."""
    _use_tmp_store(tmp_path, monkeypatch)
    monkeypatch.setattr(commands, "ANNOUNCEMENTS_CHANNEL_ID", None)
    interaction = MagicMock()
    interaction.guild_id = 1
    interaction.response.send_message = AsyncMock()

    asyncio.run(
        commands.announceevent.callback(interaction, "Strongest Lord", "2099-01-01", "18:00", "0")
    )

    interaction.response.send_message.assert_awaited_once()
    assert "ANNOUNCEMENTS_CHANNEL_ID" in interaction.response.send_message.call_args.args[0]


def test_announceevent_rejects_an_invalid_date(tmp_path, monkeypatch):
    """A bad date is reported back to the admin instead of posting a broken announcement."""
    _use_tmp_store(tmp_path, monkeypatch)
    monkeypatch.setattr(commands, "ANNOUNCEMENTS_CHANNEL_ID", 999)
    interaction = MagicMock()
    interaction.guild_id = 1
    interaction.response.send_message = AsyncMock()

    asyncio.run(
        commands.announceevent.callback(interaction, "Strongest Lord", "not-a-date", "18:00", "0")
    )

    assert "valid date" in interaction.response.send_message.call_args.args[0]


def test_announceevent_posts_to_the_announcements_channel_and_saves(tmp_path, monkeypatch):
    """The full happy path: posted with @everyone, native event created, tracked in storage."""
    _use_tmp_store(tmp_path, monkeypatch)
    monkeypatch.setattr(commands, "ANNOUNCEMENTS_CHANNEL_ID", 999)
    channel = MagicMock(spec=discord.TextChannel)
    sent_message = MagicMock()
    sent_message.id = 777
    channel.send = AsyncMock(return_value=sent_message)
    interaction = MagicMock()
    interaction.guild_id = 1
    interaction.channel_id = 10
    interaction.user.id = 555
    interaction.client = MagicMock(get_channel=MagicMock(return_value=channel))
    interaction.guild.create_scheduled_event = AsyncMock(return_value=MagicMock(id=888))
    interaction.response.send_message = AsyncMock()

    asyncio.run(
        commands.announceevent.callback(
            interaction, "Strongest Lord", "2099-01-01", "18:00", "0", 30, 60
        )
    )

    channel.send.assert_awaited_once()
    sent_text = channel.send.call_args.args[0]
    assert "@everyone" not in sent_text
    assert "Strongest Lord" in sent_text
    saved = storage.get_announcement(777)
    assert saved["title"] == "Strongest Lord"
    assert saved["discord_event_id"] == 888
    interaction.response.send_message.assert_awaited_once()


def test_announceevent_duration_minutes_allows_multi_day_events():
    """Real case: Strongest Lord runs ~6 days -- must not be capped at 24h like createvent.

    Range bounds are enforced by Discord itself from the command's parameter
    schema, not from calling .callback() directly (that bypasses them
    entirely) -- so this checks the actual configured max_value.
    """
    duration_param = next(
        p for p in commands.announceevent.parameters if p.name == "duration_minutes"
    )

    assert duration_param.max_value >= 6 * 24 * 60


# --- logic.cancel_event_and_notify / _announce_cancellation --------------------------


def test_cancel_event_and_notify_removes_the_event_and_replies(tmp_path, monkeypatch):
    """The happy path: storage cleared, origin-channel notice posted, status returned."""
    _use_tmp_store(tmp_path, monkeypatch)
    storage.save_event(42, _make_event(title="Rally"))
    message = MagicMock()
    message.id = 42
    message.reply = AsyncMock()
    client = MagicMock()

    status = asyncio.run(logic.cancel_event_and_notify(client, message, actor_id=555))

    assert status == "Event cancelled."
    assert storage.get_event(42) is None
    message.reply.assert_awaited_once()


def test_cancel_event_and_notify_also_cancels_the_linked_native_event(tmp_path, monkeypatch):
    """An event created with a native Discord Scheduled Event gets it cancelled too."""
    _use_tmp_store(tmp_path, monkeypatch)
    storage.save_event(42, _make_event(title="Rally", discord_event_id=999))
    message = MagicMock()
    message.id = 42
    message.reply = AsyncMock()
    cancel_mock = AsyncMock()
    monkeypatch.setattr(logic, "cancel_scheduled_event", cancel_mock)
    client = MagicMock()

    asyncio.run(logic.cancel_event_and_notify(client, message, actor_id=555))

    cancel_mock.assert_awaited_once_with(message.guild, 999)


def test_cancel_event_and_notify_reports_when_not_tracked(tmp_path, monkeypatch):
    """A message that isn't a tracked event is reported clearly, nothing touched."""
    _use_tmp_store(tmp_path, monkeypatch)
    message = MagicMock()
    message.id = 999
    message.reply = AsyncMock()
    client = MagicMock()

    status = asyncio.run(logic.cancel_event_and_notify(client, message, actor_id=555))

    assert "isn't a tracked event" in status
    message.reply.assert_not_awaited()


def test_cancel_event_and_notify_reports_to_the_configured_log_channel(tmp_path, monkeypatch):
    """Real gap: cancelling an event never reached LOG_CHANNEL_ID, unlike every
    other admin action in this bot (/polyglot-modules, /setlanguage, etc.).
    """
    _use_tmp_store(tmp_path, monkeypatch)
    storage.save_event(42, _make_event(title="Rally"))
    monkeypatch.setattr(logic, "report_to_log_channel", AsyncMock())
    message = MagicMock()
    message.id = 42
    message.reply = AsyncMock()
    client = MagicMock()

    asyncio.run(logic.cancel_event_and_notify(client, message, actor_id=555))

    logic.report_to_log_channel.assert_awaited_once()
    sent_text = logic.report_to_log_channel.call_args.args[1]
    assert "555" in sent_text
    assert "Rally" in sent_text


def test_announce_cancellation_noop_when_unconfigured(monkeypatch):
    """No ANNOUNCEMENTS_CHANNEL_ID set -> the client is never touched."""
    monkeypatch.setattr(logic, "ANNOUNCEMENTS_CHANNEL_ID", None)
    client = MagicMock(get_channel=MagicMock(side_effect=AssertionError("should not run")))

    asyncio.run(logic._announce_cancellation(client, _make_event(title="Rally")))


def test_announce_cancellation_posts_to_the_configured_channel_without_everyone(monkeypatch):
    """A configured channel gets an informational notice naming the cancelled event --
    no @everyone: a cancellation isn't urgent enough to interrupt everyone."""
    monkeypatch.setattr(logic, "ANNOUNCEMENTS_CHANNEL_ID", 999)
    channel = MagicMock(spec=discord.TextChannel)
    channel.send = AsyncMock()
    client = MagicMock(get_channel=MagicMock(return_value=channel))

    asyncio.run(logic._announce_cancellation(client, _make_event(title="Rally")))

    channel.send.assert_awaited_once()
    sent_text = channel.send.call_args.args[0]
    assert "@everyone" not in sent_text
    assert "Rally" in sent_text


def test_announce_cancellation_swallows_send_failures(monkeypatch):
    """A permission error posting the announcement never propagates to the caller."""
    monkeypatch.setattr(logic, "ANNOUNCEMENTS_CHANNEL_ID", 999)
    channel = MagicMock(spec=discord.TextChannel)
    response = MagicMock(status=403, reason="Forbidden")
    channel.send = AsyncMock(side_effect=discord.Forbidden(response, "missing permissions"))
    client = MagicMock(get_channel=MagicMock(return_value=channel))

    asyncio.run(logic._announce_cancellation(client, _make_event(title="Rally")))  # must not raise


# --- views.EventView (the on-message Cancel Event button) ----------------------------


def _make_button_interaction(guild_id, user_id, message, manage_guild):
    interaction = MagicMock()
    interaction.guild_id = guild_id
    interaction.user.id = user_id
    interaction.user.guild_permissions.manage_guild = manage_guild
    interaction.message = message
    interaction.client = MagicMock()
    interaction.response.send_message = AsyncMock()
    return interaction


def test_event_view_cancel_blocks_when_module_disabled(tmp_path, monkeypatch):
    """events isn't enabled for this guild -> ephemeral notice, nothing cancelled."""
    _use_tmp_store(tmp_path, monkeypatch)
    storage.save_event(42, _make_event(guild_id=1))
    message = MagicMock()
    message.id = 42
    interaction = _make_button_interaction(
        guild_id=1, user_id=555, message=message, manage_guild=True
    )
    view = views.EventView()

    asyncio.run(view.cancel.callback(interaction))

    interaction.response.send_message.assert_awaited_once()
    assert "isn't enabled" in interaction.response.send_message.call_args.args[0]
    assert storage.get_event(42) is not None


def test_event_view_cancel_blocks_without_manage_guild_permission(tmp_path, monkeypatch):
    """Any member can see the button, but only Manage Server can actually use it."""
    _use_tmp_store(tmp_path, monkeypatch)
    core_storage.set_module_enabled(1, "events", True)
    storage.save_event(42, _make_event(guild_id=1))
    message = MagicMock()
    message.id = 42
    interaction = _make_button_interaction(
        guild_id=1, user_id=555, message=message, manage_guild=False
    )
    view = views.EventView()

    asyncio.run(view.cancel.callback(interaction))

    interaction.response.send_message.assert_awaited_once()
    assert "Manage Server" in interaction.response.send_message.call_args.args[0]
    assert storage.get_event(42) is not None


def test_event_view_cancel_removes_the_event_when_authorized(tmp_path, monkeypatch):
    """An admin, with the module enabled, successfully cancels via the button."""
    _use_tmp_store(tmp_path, monkeypatch)
    core_storage.set_module_enabled(1, "events", True)
    storage.save_event(42, _make_event(guild_id=1))
    message = MagicMock()
    message.id = 42
    message.reply = AsyncMock()
    interaction = _make_button_interaction(
        guild_id=1, user_id=555, message=message, manage_guild=True
    )
    view = views.EventView()

    asyncio.run(view.cancel.callback(interaction))

    assert storage.get_event(42) is None
    interaction.response.send_message.assert_awaited_once_with("Event cancelled.", ephemeral=True)


# --- handlers.handle_reaction_add / handle_reaction_remove ---------------------------


def test_handle_reaction_add_ignores_a_non_rsvp_emoji(tmp_path, monkeypatch):
    """A flag emoji (translation's territory) is unclaimed by the events handler."""
    _use_tmp_store(tmp_path, monkeypatch)
    payload = _make_reaction_payload(100, 1, 10, 42, "🇪🇸")

    claimed = asyncio.run(handlers.handle_reaction_add(MagicMock(), payload))

    assert claimed is False


def test_handle_reaction_add_ignores_a_message_that_isnt_a_tracked_event(tmp_path, monkeypatch):
    """An RSVP emoji on a message that isn't a tracked event is left unclaimed."""
    _use_tmp_store(tmp_path, monkeypatch)
    payload = _make_reaction_payload(100, 1, 10, 42, "✅")

    claimed = asyncio.run(handlers.handle_reaction_add(MagicMock(), payload))

    assert claimed is False


def test_handle_reaction_add_records_the_rsvp_and_refreshes_the_embed(tmp_path, monkeypatch):
    """Reacting ✅ on a tracked event stores the RSVP and re-renders the embed."""
    _use_tmp_store(tmp_path, monkeypatch)
    storage.save_event(42, _make_event())
    message = MagicMock()
    message.edit = AsyncMock()
    channel = MagicMock(spec=discord.TextChannel)
    channel.fetch_message = AsyncMock(return_value=message)
    client = MagicMock(get_channel=MagicMock(return_value=channel))
    payload = _make_reaction_payload(100, 1, 10, 42, "✅")

    claimed = asyncio.run(handlers.handle_reaction_add(client, payload))

    assert claimed is True
    assert storage.get_event(42)["rsvps"]["100"] == "going"
    message.edit.assert_awaited_once()


def test_handle_reaction_add_refreshes_the_embed_without_duplicating_the_image(
    tmp_path, monkeypatch
):
    """Real bug: an event with an image showed it twice after the first RSVP --
    the rebuilt embed re-set the image while the original attachment was still
    on the message. The refreshed embed must not carry the image field.
    """
    _use_tmp_store(tmp_path, monkeypatch)
    storage.save_event(
        42, _make_event(image_url="https://cdn.discordapp.com/attachments/x/y/z.png")
    )
    message = MagicMock()
    message.edit = AsyncMock()
    channel = MagicMock(spec=discord.TextChannel)
    channel.fetch_message = AsyncMock(return_value=message)
    client = MagicMock(get_channel=MagicMock(return_value=channel))
    payload = _make_reaction_payload(100, 1, 10, 42, "✅")

    asyncio.run(handlers.handle_reaction_add(client, payload))

    edited_embed = message.edit.call_args.kwargs["embed"]
    assert edited_embed.image.url is None


def test_handle_reaction_remove_clears_the_rsvp(tmp_path, monkeypatch):
    """Removing the ✅ reaction clears that user's RSVP from the event."""
    _use_tmp_store(tmp_path, monkeypatch)
    storage.save_event(42, _make_event(rsvps={"100": "going"}))
    message = MagicMock()
    message.edit = AsyncMock()
    channel = MagicMock(spec=discord.TextChannel)
    channel.fetch_message = AsyncMock(return_value=message)
    client = MagicMock(get_channel=MagicMock(return_value=channel))
    payload = _make_reaction_payload(100, 1, 10, 42, "✅")

    claimed = asyncio.run(handlers.handle_reaction_remove(client, payload))

    assert claimed is True
    assert "100" not in storage.get_event(42)["rsvps"]


# --- scheduler.reminder_loop / _process_event_reminders ------------------------------


def test_process_event_reminders_sends_the_due_offset_and_marks_it_sent(tmp_path, monkeypatch):
    """The 60/30-minute marks were already sent by earlier loop ticks; only 10 is newly due.

    Offsets elapse in order: by construction, once `now` crosses the
    10-minute threshold, the 60/30-minute thresholds already elapsed a
    while ago too -- in production the loop runs every minute and would
    already have marked them, so that's the realistic state to test.
    """
    _use_tmp_store(tmp_path, monkeypatch)
    event = _make_event(timestamp=1000, rsvps={"1": "going", "2": "maybe"}, reminders_sent=[60, 30])
    channel = MagicMock()
    channel.send = AsyncMock()
    client = MagicMock()
    monkeypatch.setattr(scheduler, "resolve_text_channel", AsyncMock(return_value=channel))

    # now == event_timestamp - 10*60 -> the 10-minute mark is exactly due
    now = 1000 - 10 * 60
    asyncio.run(scheduler._process_event_reminders(client, 42, event, now))

    channel.send.assert_awaited_once()
    sent_text = channel.send.call_args.args[0]
    assert "<@1>" in sent_text
    assert "<@2>" not in sent_text  # only "going" gets mentioned, not "maybe"
    assert 10 in event["reminders_sent"]


def test_process_event_reminders_does_not_resend_an_already_sent_offset(tmp_path, monkeypatch):
    """Every offset through the 10-minute mark was already sent -- nothing new is due yet."""
    _use_tmp_store(tmp_path, monkeypatch)
    event = _make_event(timestamp=1000, reminders_sent=[60, 30, 10])
    channel = MagicMock()
    channel.send = AsyncMock()
    monkeypatch.setattr(scheduler, "resolve_text_channel", AsyncMock(return_value=channel))

    now = 1000 - 10 * 60  # the event itself (offset 0) is still ahead
    asyncio.run(scheduler._process_event_reminders(MagicMock(), 42, event, now))

    channel.send.assert_not_awaited()


def test_process_event_reminders_noop_when_nothing_due_yet(tmp_path, monkeypatch):
    """An event far in the future sends nothing -- no offset has come due."""
    _use_tmp_store(tmp_path, monkeypatch)
    event = _make_event(timestamp=1_000_000)
    channel = MagicMock()
    channel.send = AsyncMock()
    monkeypatch.setattr(scheduler, "resolve_text_channel", AsyncMock(return_value=channel))

    asyncio.run(scheduler._process_event_reminders(MagicMock(), 42, event, now=0))

    channel.send.assert_not_awaited()


# --- scheduler._process_announcement_reminder -----------------------------------------


def test_process_announcement_reminder_noop_before_its_due(tmp_path, monkeypatch):
    """Well before reminder_minutes_before -- nothing sent, not marked reminded."""
    _use_tmp_store(tmp_path, monkeypatch)
    announcement = _make_announcement(timestamp=1_000_000, reminder_minutes_before=30)
    send_mock = AsyncMock()
    monkeypatch.setattr(scheduler, "send_to_announcements_channel", send_mock)

    asyncio.run(scheduler._process_announcement_reminder(MagicMock(), 42, announcement, now=0))

    send_mock.assert_not_awaited()
    assert announcement["reminded"] is False


def test_process_announcement_reminder_sends_once_due_and_marks_reminded(tmp_path, monkeypatch):
    """Once reminder_minutes_before is reached, the reminder goes out and is marked sent."""
    _use_tmp_store(tmp_path, monkeypatch)
    storage.save_announcement(
        42, _make_announcement(title="Strongest Lord", timestamp=1000, reminder_minutes_before=30)
    )
    send_mock = AsyncMock()
    monkeypatch.setattr(scheduler, "send_to_announcements_channel", send_mock)

    now = 1000 - 30 * 60  # exactly reminder_minutes_before ahead of the event
    asyncio.run(
        scheduler._process_announcement_reminder(MagicMock(), 42, storage.get_announcement(42), now)
    )

    send_mock.assert_awaited_once()
    assert storage.get_announcement(42)["reminded"] is True


def test_process_announcement_reminder_does_not_repeat_once_already_reminded(tmp_path, monkeypatch):
    """A second tick after the reminder already went out doesn't send it again."""
    _use_tmp_store(tmp_path, monkeypatch)
    announcement = _make_announcement(timestamp=1000, reminder_minutes_before=30, reminded=True)
    send_mock = AsyncMock()
    monkeypatch.setattr(scheduler, "send_to_announcements_channel", send_mock)

    asyncio.run(scheduler._process_announcement_reminder(MagicMock(), 42, announcement, now=1000))

    send_mock.assert_not_awaited()
