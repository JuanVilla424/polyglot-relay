import discord

from app.discord_utils import resolve_text_channel
from app.modules.verification import logic


async def handle_reaction_add(
    client: discord.Client, payload: discord.RawReactionActionEvent
) -> bool:
    """An Admin/Officer/Leader reacting the approval emoji on a verification
    photo grants the verified + member roles to whoever posted it.

    Returns True once it acts (claiming the reaction so no other module tries
    it), False otherwise -- same contract as translation/events.
    """
    is_relevant = (
        logic.is_configured()
        and str(payload.emoji) == logic.APPROVAL_EMOJI
        and payload.channel_id == logic.VERIFY_CHANNEL_ID
        and payload.member is not None
        and logic.is_approver(payload.member)
    )
    if not is_relevant:
        return False

    channel = await resolve_text_channel(client, payload.channel_id)
    if channel is None:
        return True
    try:
        message = await channel.fetch_message(payload.message_id)
    except discord.HTTPException:
        return True

    if not logic.has_image_attachment(message):
        return False

    await logic.approve_and_assign_roles(client, message, payload.member)
    return True
