import discord
from discord import app_commands

from app.logger import logger
from app.modules.activity.logic import DEFAULT_INACTIVE_DAYS, build_activity_report
from app.modules.checks import ModuleDisabledError, require_enabled


async def _admin_command_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
) -> None:
    """Shared error handler for activity commands: clean message, no unhandled traceback."""
    if isinstance(error, ModuleDisabledError):
        await interaction.response.send_message(
            f"{error} An admin can enable it with `/polyglot-modules enable {error.module_name}`.",
            ephemeral=True,
        )
        return
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            "You need the Manage Server permission to use this.", ephemeral=True
        )
        return
    logger.exception("activity command failed", exc_info=error)
    await interaction.response.send_message("Something went wrong.", ephemeral=True)


@app_commands.command(
    name="activityreport", description="Admin: see which members haven't been active recently"
)
@app_commands.describe(
    inactive_days="Flag members inactive for at least this many days -- default 7"
)
@require_enabled("activity")
@app_commands.default_permissions(manage_guild=True)
@app_commands.checks.has_permissions(manage_guild=True)
async def activityreport(
    interaction: discord.Interaction,
    inactive_days: app_commands.Range[int, 1, 365] = DEFAULT_INACTIVE_DAYS,
):
    """Report members past the inactivity threshold, and members never recorded at all."""
    if interaction.guild_id is None:
        await interaction.response.send_message(
            "This command only works inside a server.", ephemeral=True
        )
        return

    report = await build_activity_report(interaction.guild, inactive_days)
    await interaction.response.send_message(report, ephemeral=True)


activityreport.error(_admin_command_error)


def register(tree: app_commands.CommandTree) -> None:
    """Register every activity slash command on the shared tree."""
    tree.add_command(activityreport)
