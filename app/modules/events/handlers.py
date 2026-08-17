import discord

from app.discord_utils import resolve_text_channel
from app.logger import logger
from app.modules.events import storage
from app.modules.events.logic import RSVP_EMOJIS, make_event_embed


async def _update_rsvp(
    client: discord.Client, payload: discord.RawReactionActionEvent, status: str | None
) -> bool:
    """Set (or, if status is None, clear) one user's RSVP and re-render the event embed.

    Returns True if this message was a tracked event (claiming the reaction event).
    """
    event = storage.get_event(payload.message_id)
    if event is None:
        return False

    if status is None:
        event["rsvps"].pop(str(payload.user_id), None)
    else:
        event["rsvps"][str(payload.user_id)] = status
    storage.save_event(payload.message_id, event)
    logger.info(
        "user %s RSVP'd %s on event %s", payload.user_id, status or "cleared", payload.message_id
    )

    channel = await resolve_text_channel(client, payload.channel_id)
    if channel is None:
        return True
    try:
        message = await channel.fetch_message(payload.message_id)
        await message.edit(embed=make_event_embed(event))
    except discord.HTTPException:
        logger.warning("could not refresh the RSVP embed for event %s", payload.message_id)
    return True


async def handle_reaction_add(
    client: discord.Client, payload: discord.RawReactionActionEvent
) -> bool:
    """A ✅/❓/❌ reaction on a tracked event sets that user's RSVP."""
    status = RSVP_EMOJIS.get(str(payload.emoji))
    if status is None:
        return False
    return await _update_rsvp(client, payload, status)


async def handle_reaction_remove(
    client: discord.Client, payload: discord.RawReactionActionEvent
) -> bool:
    """Removing a ✅/❓/❌ reaction on a tracked event clears that user's RSVP."""
    if str(payload.emoji) not in RSVP_EMOJIS:
        return False
    return await _update_rsvp(client, payload, None)
