import discord

from app.discord_utils import resolve_text_channel
from app.logger import logger
from app.modules import checks
from app.modules.translation import storage
from app.modules.translation.logic import (
    DEFAULT_DELIVERY_MODE,
    _translate_and_deliver,
    _translate_single_language,
)
from core.lang_codes import FLAG_TO_ISO


async def handle_message(_client: discord.Client, message: discord.Message) -> None:
    """Deliver the message translated into every language active here."""
    if not message.content:
        return
    if storage.is_channel_excluded(message.guild.id, message.channel.id):
        return
    await _translate_and_deliver(message)


async def handle_reaction_add(
    client: discord.Client, payload: discord.RawReactionActionEvent
) -> bool:
    """In reactions mode, a flag reaction triggers an on-demand translation.

    Returns True if this event was a flag reaction (claiming it, so no other
    module tries to handle the same reaction), False otherwise.
    """
    target_lang = FLAG_TO_ISO.get(str(payload.emoji))
    if target_lang is None:
        return False

    mode = storage.get_delivery_mode(payload.guild_id) or DEFAULT_DELIVERY_MODE
    if mode != "reactions" or storage.is_channel_excluded(payload.guild_id, payload.channel_id):
        return False

    channel = await resolve_text_channel(client, payload.channel_id)
    if channel is None:
        return True

    try:
        message = await channel.fetch_message(payload.message_id)
    except discord.HTTPException:
        return True

    # Anti-amplification: never translate (re-publish) content written by a
    # quarantined member, no matter who reacted. Claimed so no module retries.
    if checks.is_subject(getattr(message, "author", None)):
        return True

    logger.info(
        "reaction %s from user %s on message %s -> translating to %s",
        payload.emoji,
        payload.user_id,
        payload.message_id,
        target_lang,
    )
    await _translate_single_language(message, target_lang)
    return True
