import discord
from discord.ext import tasks

from app.discord_utils import resolve_text_channel
from app.logger import logger
from app.modules.events import storage
from app.modules.events.logic import REMINDER_OFFSETS_MINUTES


async def _send_reminder(channel: discord.abc.Messageable, event: dict, offset: int) -> None:
    """Post one reminder, mentioning only the members who RSVP'd going."""
    going = [user_id for user_id, status in event["rsvps"].items() if status == "going"]
    mentions = " ".join(f"<@{user_id}>" for user_id in going)
    if offset == 0:
        text = f"🔥 **{event['title']}** is starting now! {mentions}".strip()
    else:
        text = f"⏰ **{event['title']}** starts <t:{event['timestamp']}:R> {mentions}".strip()
    try:
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


@tasks.loop(minutes=1)
async def reminder_loop(client: discord.Client) -> None:
    """Check every tracked event for reminder offsets that just came due."""
    now = int(discord.utils.utcnow().timestamp())
    for message_id_str, event in list(storage.all_events().items()):
        await _process_event_reminders(client, int(message_id_str), event, now)
