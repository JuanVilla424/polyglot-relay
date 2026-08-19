import discord

from app.modules.activity import storage


async def handle_message(_client: discord.Client, message: discord.Message) -> None:
    """Every real message updates its author's last-active timestamp."""
    storage.record_activity(
        message.guild.id, message.author.id, int(message.created_at.timestamp())
    )


async def handle_reaction_add(
    _client: discord.Client, payload: discord.RawReactionActionEvent
) -> bool:
    """Record activity but never claim the reaction.

    Unlike every other module's handle_reaction_add, this one always returns
    False on purpose -- activity tracking is a silent side effect that must
    never stop the dispatch chain, or the module that actually owns a given
    reaction (RSVP, verification approval, translation flags) would never run.
    """
    storage.record_activity(
        payload.guild_id, payload.user_id, int(discord.utils.utcnow().timestamp())
    )
    return False
