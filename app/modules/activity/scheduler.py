import discord
from discord.ext import tasks

from app import storage as core_storage
from app.discord_utils import report_to_log_channel
from app.modules.activity import storage
from app.modules.activity.logic import DEFAULT_INACTIVE_DAYS, build_activity_report, is_digest_due


async def _process_guild_digest(client: discord.Client, guild: discord.Guild, now: int) -> None:
    """Post the weekly digest for one guild if it's due, and mark it sent.

    A guild with no stored digest timestamp yet (module just enabled) seeds
    silently instead of posting immediately -- same "first run seeds, doesn't
    announce" pattern used for the deploy-SHA announcer.
    """
    if not core_storage.is_module_enabled(guild.id, "activity"):
        return

    last_sent = storage.get_last_digest_sent_at(guild.id)
    if last_sent is None:
        storage.set_last_digest_sent_at(guild.id, now)
        return
    if not is_digest_due(last_sent, now):
        return

    report = await build_activity_report(guild, DEFAULT_INACTIVE_DAYS)
    await report_to_log_channel(client, f"📋 **Weekly activity report — {guild.name}**\n{report}")
    storage.set_last_digest_sent_at(guild.id, now)


@tasks.loop(hours=1)
async def activity_digest_loop(client: discord.Client) -> None:
    """Check every guild the bot is in for a weekly activity digest that's now due."""
    now = int(discord.utils.utcnow().timestamp())
    for guild in client.guilds:
        await _process_guild_digest(client, guild, now)
