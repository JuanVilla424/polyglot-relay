import discord
from discord import app_commands

from app.discord_utils import report_to_log_channel
from app.logger import logger
from app.modules.checks import ModuleDisabledError, require_enabled
from app.modules.polls.logic import (
    DEFAULT_POLL_DURATION_HOURS,
    MAX_POLL_DURATION_HOURS,
    build_poll,
    parse_poll_options,
)


async def _admin_command_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
) -> None:
    """Shared error handler for polls commands: clean message, no unhandled traceback."""
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
    logger.exception("polls command failed", exc_info=error)
    await interaction.response.send_message("Something went wrong.", ephemeral=True)


@app_commands.command(name="createpoll", description="Admin: post a poll with up to 10 options")
@app_commands.describe(
    question="The poll question",
    options='Answer options, separated by ";" (2-10, e.g. "Yes; No; Maybe")',
    duration_hours="How long the poll runs, in hours -- default 24, max 168 (1 week)",
)
@require_enabled("polls")
@app_commands.default_permissions(manage_guild=True)
@app_commands.checks.has_permissions(manage_guild=True)
async def createpoll(
    interaction: discord.Interaction,
    question: app_commands.Range[str, 1, 300],
    options: str,
    duration_hours: app_commands.Range[
        int, 1, MAX_POLL_DURATION_HOURS
    ] = DEFAULT_POLL_DURATION_HOURS,
):
    """Post a native Discord poll with the given question, options, and duration."""
    if interaction.guild_id is None:
        await interaction.response.send_message(
            "This command only works inside a server.", ephemeral=True
        )
        return

    try:
        parsed_options = parse_poll_options(options)
    except ValueError as exc:
        await interaction.response.send_message(str(exc), ephemeral=True)
        return

    poll = build_poll(question, parsed_options, duration_hours)
    await interaction.response.send_message(poll=poll)

    await report_to_log_channel(
        interaction.client, f"📊 <@{interaction.user.id}> created the poll **{question}**"
    )
    logger.info(
        "poll %r created by %s in guild %s, %s options, %sh duration",
        question,
        interaction.user.id,
        interaction.guild_id,
        len(parsed_options),
        duration_hours,
    )


createpoll.error(_admin_command_error)


@app_commands.context_menu(name="End Poll")
@require_enabled("polls")
@app_commands.default_permissions(manage_guild=True)
@app_commands.checks.has_permissions(manage_guild=True)
async def end_poll(interaction: discord.Interaction, message: discord.Message):
    """Admin: end a poll before its configured duration elapses on its own."""
    if message.poll is None:
        await interaction.response.send_message(
            "That message doesn't have an active poll.", ephemeral=True
        )
        return

    try:
        await message.end_poll()
    except discord.HTTPException:
        await interaction.response.send_message(
            "Could not end that poll (it may have already ended).", ephemeral=True
        )
        return

    await report_to_log_channel(
        interaction.client,
        f"🔒 <@{interaction.user.id}> ended the poll **{message.poll.question}**",
    )
    await interaction.response.send_message("Poll ended.", ephemeral=True)


end_poll.error(_admin_command_error)


def register(tree: app_commands.CommandTree) -> None:
    """Register every polls slash/context-menu command on the shared tree."""
    for command in (createpoll, end_poll):
        tree.add_command(command)
