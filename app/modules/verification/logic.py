import discord

from app.config import (
    MEMBER_ROLE_ID,
    VERIFIED_ROLE_ID,
    VERIFY_APPROVER_ROLE_IDS,
    VERIFY_CHANNEL_ID,
)
from app.discord_utils import report_to_log_channel
from app.logger import logger

APPROVAL_EMOJI = "✅"


def is_configured() -> bool:
    """Whether every setting this module needs is present in .env."""
    return bool(
        VERIFY_CHANNEL_ID and VERIFIED_ROLE_ID and MEMBER_ROLE_ID and VERIFY_APPROVER_ROLE_IDS
    )


def is_approver(member: discord.Member) -> bool:
    """Whether this member holds one of the roles allowed to approve a verification photo."""
    return any(role.id in VERIFY_APPROVER_ROLE_IDS for role in member.roles)


def has_image_attachment(message: discord.Message) -> bool:
    """Whether this message has at least one image attached."""
    return any(
        (attachment.content_type or "").startswith("image/") for attachment in message.attachments
    )


async def approve_and_assign_roles(
    client: discord.Client, message: discord.Message, approver: discord.Member
) -> None:
    """Grant the verified + member roles to whoever posted this photo, and
    record who approved it.

    The visual check (is this screenshot legit) stays with the approver --
    this only automates the two role assignments and the confirmation
    reaction that used to be done by hand.
    """
    guild = message.guild
    author = guild.get_member(message.author.id) or await guild.fetch_member(message.author.id)

    verified_role = guild.get_role(VERIFIED_ROLE_ID)
    member_role = guild.get_role(MEMBER_ROLE_ID)
    if verified_role is None or member_role is None:
        logger.warning("verification roles not found in guild %s", guild.id)
        await report_to_log_channel(
            client, "⚠️ Verification roles aren't configured correctly (missing from the server)."
        )
        return

    author_role_ids = {role.id for role in author.roles}
    if VERIFIED_ROLE_ID not in author_role_ids or MEMBER_ROLE_ID not in author_role_ids:
        try:
            await author.add_roles(verified_role, member_role, reason=f"Verified by {approver}")
        except discord.Forbidden:
            logger.warning(
                "missing permission or role hierarchy to add verification roles to %s", author.id
            )
            await report_to_log_channel(
                client,
                "⚠️ Could not assign verification roles -- check the bot's Manage Roles "
                "permission and that its role is above Verified/Member in the hierarchy.",
            )
            return

    try:
        await message.add_reaction(APPROVAL_EMOJI)
    except discord.HTTPException:
        logger.warning(
            "could not add the confirmation reaction on verification message %s", message.id
        )

    await report_to_log_channel(client, f"✅ {approver.mention} verified {author.mention}")
    logger.info("verified %s (approved by %s)", author.id, approver.id)
