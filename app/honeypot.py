"""Honeypot channel gate: the trap channel is open to everyone and clearly
labeled "do not type here" -- humans read the warning, compromised accounts
and spam bots post into every visible channel without reading. One message
there self-identifies the account.

Action on trigger (leadership's chosen policy): delete the message, quarantine
the author (subject role on, Member/Verified off -- reversible, unlike a ban),
and alert the log channel so leadership decides the ban.
"""

import discord

from app.config import HONEYPOT_CHANNEL_ID, MEMBER_ROLE_ID, SUBJECT_ROLE_ID, VERIFIED_ROLE_ID
from app.discord_utils import report_to_log_channel
from app.logger import logger


async def handle_honeypot_message(client: discord.Client, message: discord.Message) -> bool:
    """True when the message hit the honeypot and was handled -- callers must
    stop all further processing (no translation, no activity count)."""
    if HONEYPOT_CHANNEL_ID is None or message.channel.id != HONEYPOT_CHANNEL_ID:
        return False

    try:
        await message.delete()
    except discord.HTTPException:
        logger.warning("honeypot: could not delete message %s", message.id)

    author = message.author
    subject_role = message.guild.get_role(SUBJECT_ROLE_ID) if SUBJECT_ROLE_ID else None
    try:
        if subject_role is not None:
            await author.add_roles(subject_role, reason="honeypot trigger")
        to_remove = [role for role in author.roles if role.id in (MEMBER_ROLE_ID, VERIFIED_ROLE_ID)]
        if to_remove:
            await author.remove_roles(*to_remove, reason="honeypot trigger")
    except discord.HTTPException:
        logger.warning("honeypot: could not quarantine user %s", author.id)

    await report_to_log_channel(
        client,
        f"🍯 Honeypot triggered: <@{author.id}> posted in the trap channel — "
        "quarantined (subject role) and message deleted. Leadership decides the ban.",
    )
    logger.info("honeypot triggered by user %s in channel %s", author.id, message.channel.id)
    return True
