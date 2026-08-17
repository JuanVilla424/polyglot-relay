import discord


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
