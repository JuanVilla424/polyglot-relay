import discord
from discord.ext import tasks

from app.logger import logger
from app.modules.translation import storage
from app.modules.translation.logic import DELIVERED_LANGUAGES_TTL_DAYS


async def _run_cleanup(now: int) -> int:
    """Prune delivered-language tracking for messages nobody's reacted to in a while.

    Pure storage maintenance -- no Discord API calls, so this needs no client.
    """
    removed = storage.prune_stale_delivered_languages(now, DELIVERED_LANGUAGES_TTL_DAYS * 86400)
    if removed:
        logger.info("pruned %d stale delivered-language entries", removed)
    return removed


@tasks.loop(hours=24)
async def cleanup_loop() -> None:
    """Daily check for delivered-language tracking that's aged out."""
    now = int(discord.utils.utcnow().timestamp())
    await _run_cleanup(now)
