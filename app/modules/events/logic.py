import re
from datetime import datetime, timedelta, timezone

import discord

from app.config import ANNOUNCEMENTS_CHANNEL_ID
from app.discord_utils import report_to_log_channel, resolve_text_channel
from app.logger import logger
from app.modules.events import storage

RSVP_EMOJIS = {"✅": "going", "❓": "maybe", "❌": "not_going"}
RSVP_LABELS = {"going": "✅ Going", "maybe": "❓ Maybe", "not_going": "❌ Not going"}

# Reminders fire this many minutes before the event (0 = at the event itself).
REMINDER_OFFSETS_MINUTES = [60, 30, 10, 0]

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME_RE = re.compile(r"^\d{2}:\d{2}$")

EVENT_COLOR = 0x5865F2

# Native Discord Scheduled Events (the server's own "Events" tab) require an
# entity_type; these events aren't tied to a voice/stage channel, so
# "external" is the right fit, and that entity type requires a location
# string plus an end_time -- there's no in-game channel to point at.
EVENT_LOCATION = "In-game"
DEFAULT_EVENT_DURATION_MINUTES = 60


def parse_event_timestamp(date: str, time: str, utc_offset: str) -> int:
    """Parse date/time/utc_offset into a unix timestamp.

    Raises ValueError with a user-facing message on any invalid input,
    including a date/time that's already in the past.
    """
    if not _DATE_RE.match(date):
        raise ValueError(f"`{date}` isn't a valid date (expected YYYY-MM-DD).")
    if not _TIME_RE.match(time):
        raise ValueError(f"`{time}` isn't a valid time (expected HH:MM, 24h).")
    try:
        offset_hours = float(utc_offset)
    except ValueError as exc:
        raise ValueError(f"`{utc_offset}` isn't a valid UTC offset (e.g. -5, 0, +2).") from exc
    if not -12 <= offset_hours <= 14:
        raise ValueError(f"`{utc_offset}` is out of range for a UTC offset (-12 to +14).")

    try:
        naive = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
    except ValueError as exc:
        raise ValueError(f"`{date} {time}` isn't a valid date/time.") from exc

    aware = naive.replace(tzinfo=timezone(timedelta(hours=offset_hours)))
    event_timestamp = int(aware.timestamp())

    if event_timestamp <= int(datetime.now(timezone.utc).timestamp()):
        raise ValueError("That date/time is already in the past.")

    return event_timestamp


def pending_reminder_offsets(created_at: int, event_timestamp: int) -> list[int]:
    """Offsets still in the future as of `created_at` -- the rest get pre-marked as sent
    so creating an event with less than an hour's notice doesn't spam past reminders.
    """
    return [
        offset for offset in REMINDER_OFFSETS_MINUTES if event_timestamp - offset * 60 > created_at
    ]


def make_event_embed(event: dict, include_image: bool = True) -> discord.Embed:
    """Build the event embed: title, description, time, image, and RSVP counts.

    include_image=False skips the image field on re-renders (RSVP updates):
    the original upload stays visible as the message's own attachment, and
    setting the same image on the embed too made Discord display it twice.
    """
    embed = discord.Embed(
        title=event["title"], description=event.get("description") or None, color=EVENT_COLOR
    )
    timestamp = event["timestamp"]
    embed.add_field(name="When", value=f"<t:{timestamp}:F> (<t:{timestamp}:R>)", inline=False)
    for status, label in RSVP_LABELS.items():
        user_ids = [user_id for user_id, s in event["rsvps"].items() if s == status]
        mentions = " ".join(f"<@{user_id}>" for user_id in user_ids) or "—"
        embed.add_field(name=f"{label} ({len(user_ids)})", value=mentions, inline=True)
    if include_image and event.get("image_url"):
        embed.set_image(url=event["image_url"])
    return embed


async def create_scheduled_event(
    guild: discord.Guild, event: dict, image_bytes: bytes | None
) -> discord.ScheduledEvent | None:
    """Best-effort: also create a native Discord Scheduled Event so this shows
    up in the server's own Events tab, not just as a channel message.

    Needs the bot's Manage Events permission -- if missing, this quietly
    skips instead of blocking the rest of event creation (the embed/RSVP
    flow this bot already has works independently of this).
    """
    start_time = datetime.fromtimestamp(event["timestamp"], tz=timezone.utc)
    duration_minutes = event.get("duration_minutes", DEFAULT_EVENT_DURATION_MINUTES)
    end_time = start_time + timedelta(minutes=duration_minutes)
    kwargs = {
        "name": event["title"],
        "description": event.get("description") or None,
        "start_time": start_time,
        "end_time": end_time,
        "entity_type": discord.EntityType.external,
        "location": EVENT_LOCATION,
    }
    # discord.py tries to base64-encode `image` unconditionally, even when
    # it's None, and crashes -- only pass it at all when there's a real image.
    if image_bytes is not None:
        kwargs["image"] = image_bytes
    try:
        return await guild.create_scheduled_event(**kwargs)
    except discord.Forbidden:
        logger.warning("missing Manage Events permission, skipping the native Discord event")
        return None


async def cancel_scheduled_event(guild: discord.Guild, discord_event_id: int) -> None:
    """Best-effort: cancel the native Discord event tied to this event, if any."""
    try:
        scheduled_event = await guild.fetch_scheduled_event(discord_event_id)
        await scheduled_event.cancel()
    except discord.HTTPException:
        logger.warning("could not cancel the native Discord event %s", discord_event_id)


async def cancel_event_and_notify(
    client: discord.Client, message: discord.Message, actor_id: int
) -> str:
    """Stop tracking an event, notify its origin channel, and announce it if configured.

    Shared by the "Cancel Event" context-menu command and the on-message
    button so both stay in sync instead of duplicating this logic.
    """
    event = storage.get_event(message.id)
    if event is None:
        return "That message isn't a tracked event."

    storage.delete_event(message.id)
    if event.get("discord_event_id"):
        await cancel_scheduled_event(message.guild, event["discord_event_id"])
    try:
        await message.reply("🚫 This event was cancelled.", mention_author=False)
    except discord.HTTPException:
        logger.warning("could not post the cancellation notice for event %s", message.id)

    await _announce_cancellation(client, event)
    await report_to_log_channel(
        client, f"🚫 <@{actor_id}> cancelled the event **{event['title']}**"
    )

    logger.info("event %s cancelled by %s", message.id, actor_id)
    return "Event cancelled."


async def _announce_cancellation(client: discord.Client, event: dict) -> None:
    """Best-effort @everyone ping in the announcements channel, if one is configured."""
    if ANNOUNCEMENTS_CHANNEL_ID is None:
        return
    channel = await resolve_text_channel(client, ANNOUNCEMENTS_CHANNEL_ID)
    if channel is None:
        return
    try:
        await channel.send(
            f"@everyone 🚫 **{event['title']}** was cancelled.",
            allowed_mentions=discord.AllowedMentions(everyone=True),
        )
    except discord.HTTPException:
        logger.warning("could not post the cancellation announcement for %r", event["title"])
