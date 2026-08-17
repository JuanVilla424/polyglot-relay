import re
from datetime import datetime, timedelta, timezone

import discord

RSVP_EMOJIS = {"✅": "going", "❓": "maybe", "❌": "not_going"}
RSVP_LABELS = {"going": "✅ Going", "maybe": "❓ Maybe", "not_going": "❌ Not going"}

# Reminders fire this many minutes before the event (0 = at the event itself).
REMINDER_OFFSETS_MINUTES = [60, 30, 10, 0]

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME_RE = re.compile(r"^\d{2}:\d{2}$")

EVENT_COLOR = 0x5865F2


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


def make_event_embed(event: dict) -> discord.Embed:
    """Build the event embed: title, description, time, image, and RSVP counts."""
    embed = discord.Embed(
        title=event["title"], description=event.get("description") or None, color=EVENT_COLOR
    )
    timestamp = event["timestamp"]
    embed.add_field(name="When", value=f"<t:{timestamp}:F> (<t:{timestamp}:R>)", inline=False)
    for status, label in RSVP_LABELS.items():
        user_ids = [user_id for user_id, s in event["rsvps"].items() if s == status]
        mentions = " ".join(f"<@{user_id}>" for user_id in user_ids) or "—"
        embed.add_field(name=f"{label} ({len(user_ids)})", value=mentions, inline=True)
    if event.get("image_url"):
        embed.set_image(url=event["image_url"])
    return embed
