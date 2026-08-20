import discord

from app.config import LOG_CHANNEL_ID
from app.logger import logger


async def resolve_text_channel(
    client: discord.Client, channel_id: int
) -> discord.TextChannel | discord.Thread | None:
    """Look up a channel by ID, falling back to a fetch if it isn't cached."""
    channel = client.get_channel(channel_id)
    if channel is None:
        try:
            channel = await client.fetch_channel(channel_id)
        except discord.HTTPException:
            return None
    if not isinstance(channel, (discord.TextChannel, discord.Thread)):
        return None
    return channel


async def report_to_log_channel(client: discord.Client, message: str) -> None:
    """Log an admin action, and best-effort post it to the configured channel too.

    Shared by every module's admin commands (not just translation's), so
    LOG_CHANNEL_ID reflects every config change across the whole bot.
    """
    logger.info(message)
    if LOG_CHANNEL_ID is None:
        return
    try:
        channel = client.get_channel(LOG_CHANNEL_ID) or await client.fetch_channel(LOG_CHANNEL_ID)
        await channel.send(message)
    except (discord.Forbidden, discord.NotFound, discord.HTTPException):
        logger.warning("could not post to log channel %s", LOG_CHANNEL_ID)
