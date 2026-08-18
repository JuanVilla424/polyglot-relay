import discord

from app import storage as core_storage
from app.modules.events.logic import cancel_event_and_notify


class EventView(discord.ui.View):
    """Persistent view attached to every event embed.

    timeout=None plus a fixed custom_id makes this a "persistent view": the
    button keeps responding after a bot restart, not just for the process
    that originally posted the message, as long as it's re-registered via
    client.add_view() on startup.
    """

    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Cancel Event", style=discord.ButtonStyle.danger, custom_id="polyglot:cancel_event"
    )
    async def cancel(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        """Admin-only: cancel the event this button is attached to."""
        if interaction.guild_id is None or not core_storage.is_module_enabled(
            interaction.guild_id, "events"
        ):
            await interaction.response.send_message(
                "The `events` module isn't enabled in this server.", ephemeral=True
            )
            return
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                "You need the Manage Server permission to use this.", ephemeral=True
            )
            return
        status = await cancel_event_and_notify(
            interaction.client, interaction.message, interaction.user.id
        )
        await interaction.response.send_message(status, ephemeral=True)
