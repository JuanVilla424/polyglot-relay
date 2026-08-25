import discord
from discord.ext import tasks

from app.discord_utils import resolve_text_channel
from app.logger import logger
from app.modules.events import storage
from app.modules.events.logic import (
    EVERYONE_REMINDER_OFFSET_MINUTES,
    REMINDER_OFFSETS_MINUTES,
    build_reminder_text,
    send_to_announcements_channel,
)


async def _send_reminder(channel: discord.abc.Messageable, event: dict, offset: int) -> None:
    """Post one reminder, mentioning only the members who RSVP'd going --
    except the single EVERYONE_REMINDER_OFFSET_MINUTES mark, which pings
    @everyone instead (no individual mentions on top: the ping covers them).
    """
    if offset == EVERYONE_REMINDER_OFFSET_MINUTES:
        text = f"@everyone ⏰ **{event['title']}** starts <t:{event['timestamp']}:R>!"
        allowed_mentions = discord.AllowedMentions(everyone=True)
    else:
        going = [user_id for user_id, status in event["rsvps"].items() if status == "going"]
        mentions = " ".join(f"<@{user_id}>" for user_id in going)
        if offset == 0:
            text = f"🔥 **{event['title']}** is starting now! {mentions}".strip()
        else:
            text = f"⏰ **{event['title']}** starts <t:{event['timestamp']}:R> {mentions}".strip()
        allowed_mentions = None
    try:
        if allowed_mentions is not None:
            await channel.send(text, allowed_mentions=allowed_mentions)
        else:
            await channel.send(text)
        logger.info("sent the %s-minute reminder for event %r", offset, event["title"])
    except discord.HTTPException:
        logger.warning("could not send a reminder for event %s", event["title"])


async def _process_event_reminders(
    client: discord.Client, message_id: int, event: dict, now: int
) -> None:
    """Send every reminder offset that's now due for this event, and mark it sent."""
    already_sent = set(event.get("reminders_sent", []))
    due_offsets = [
        offset
        for offset in REMINDER_OFFSETS_MINUTES
        if offset not in already_sent and now >= event["timestamp"] - offset * 60
    ]
    if not due_offsets:
        return

    channel = await resolve_text_channel(client, event["channel_id"])
    for offset in due_offsets:
        if channel is not None:
            await _send_reminder(channel, event, offset)
        event.setdefault("reminders_sent", []).append(offset)
    storage.save_event(message_id, event)


async def _process_announcement_reminder(
    client: discord.Client, message_id: int, announcement: dict, now: int
) -> None:
    """Post the single reminder for one game-event announcement, if it's now due."""
    if announcement.get("reminded"):
        return
    reminder_at = announcement["timestamp"] - announcement["reminder_minutes_before"] * 60
    if now < reminder_at:
        return

    await send_to_announcements_channel(
        client, build_reminder_text(announcement["title"], announcement["timestamp"])
    )
    announcement["reminded"] = True
    storage.save_announcement(message_id, announcement)


@tasks.loop(minutes=1)
async def reminder_loop(client: discord.Client) -> None:
    """Check every tracked event and game-event announcement for what's now due."""
    now = int(discord.utils.utcnow().timestamp())
    for message_id_str, event in list(storage.all_events().items()):
        await _process_event_reminders(client, int(message_id_str), event, now)
    for message_id_str, announcement in list(storage.all_announcements().items()):
        await _process_announcement_reminder(client, int(message_id_str), announcement, now)
