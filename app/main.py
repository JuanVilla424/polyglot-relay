from pathlib import Path

import discord
from discord import app_commands
from discord.ext import tasks

from app import discord_utils, honeypot, storage
from app.config import DISCORD_BOT_TOKEN
from app.logger import logger
from app.modules import MODULES, checks
from app.modules.activity.scheduler import activity_digest_loop
from app.modules.events.scheduler import reminder_loop
from app.modules.events.views import EventView
from app.modules.translation.scheduler import cleanup_loop

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

HEARTBEAT_PATH = Path("/tmp/healthy")


@tasks.loop(seconds=30)
async def _heartbeat() -> None:
    """Touch a file the Docker healthcheck watches, proving the gateway is alive."""
    HEARTBEAT_PATH.touch()


def _active_modules(guild_id: int) -> list:
    """Every module enabled for this guild, in registry order."""
    return [module for name, module in MODULES.items() if storage.is_module_enabled(guild_id, name)]


@client.event
async def on_ready():
    """Sync application commands, and start the background loops, once logged in."""
    await tree.sync()
    client.add_view(EventView())
    if not _heartbeat.is_running():
        _heartbeat.start()
    if not reminder_loop.is_running():
        reminder_loop.start(client)
    if not activity_digest_loop.is_running():
        activity_digest_loop.start(client)
    if not cleanup_loop.is_running():
        cleanup_loop.start()
    logger.info("logged in as %s", client.user)


def _reaction_member(payload: discord.RawReactionActionEvent):
    """Resolve who reacted: the payload carries the member on adds; removals
    only carry ids, so fall back to the guild cache (Members Intent is on)."""
    if payload.member is not None:
        return payload.member
    guild = client.get_guild(payload.guild_id)
    return guild.get_member(payload.user_id) if guild else None


@client.event
async def on_message(message: discord.Message):
    """Dispatch a new message to every module active in this guild.

    Quarantined members (subject role) are dropped before any module runs:
    their content must never be translated, counted, or amplified.
    """
    if message.author.bot or message.guild is None:
        return
    if await honeypot.handle_honeypot_message(client, message):
        return
    if checks.is_subject(message.author):
        return
    for module in _active_modules(message.guild.id):
        handler = getattr(module.handlers, "handle_message", None)
        if handler:
            await handler(client, message)


@client.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent) -> None:
    """Dispatch a reaction add to the first active module that claims it.

    Ignores the bot's own reactions -- both translation (flag emojis) and
    events (RSVP emojis) add reactions automatically, and without this guard
    each would immediately re-trigger its own handler off its own reaction.
    """
    if payload.user_id == client.user.id or payload.guild_id is None:
        return
    if checks.is_subject(_reaction_member(payload)):
        return
    for module in _active_modules(payload.guild_id):
        handler = getattr(module.handlers, "handle_reaction_add", None)
        if handler and await handler(client, payload):
            return


@client.event
async def on_raw_reaction_remove(payload: discord.RawReactionActionEvent) -> None:
    """Dispatch a reaction removal to the first active module that claims it."""
    if payload.user_id == client.user.id or payload.guild_id is None:
        return
    if checks.is_subject(_reaction_member(payload)):
        return
    for module in _active_modules(payload.guild_id):
        handler = getattr(module.handlers, "handle_reaction_remove", None)
        if handler and await handler(client, payload):
            return


@tree.command(
    name="polyglot-modules", description="Admin: enable or disable a bot module in this server"
)
@app_commands.describe(action="Enable or disable", module="Which module")
@app_commands.choices(
    action=[
        app_commands.Choice(name="Enable", value="enable"),
        app_commands.Choice(name="Disable", value="disable"),
    ],
    module=[app_commands.Choice(name=name.capitalize(), value=name) for name in MODULES],
)
@app_commands.default_permissions(manage_guild=True)
@app_commands.checks.has_permissions(manage_guild=True)
async def polyglot_modules(
    interaction: discord.Interaction,
    action: app_commands.Choice[str],
    module: app_commands.Choice[str],
):
    """Let an admin turn a module on or off for this guild."""
    if interaction.guild_id is None:
        await interaction.response.send_message(
            "This command only works inside a server.", ephemeral=True
        )
        return
    enabled = action.value == "enable"
    storage.set_module_enabled(interaction.guild_id, module.value, enabled)
    await interaction.response.send_message(
        f"`{module.value}` module {'enabled' if enabled else 'disabled'} for this server.",
        ephemeral=True,
    )
    await discord_utils.report_to_log_channel(
        interaction.client,
        f"🌐 {interaction.user.mention} {'enabled' if enabled else 'disabled'} "
        f"the `{module.value}` module",
    )


async def _polyglot_modules_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
) -> None:
    """Clean error message for /polyglot-modules instead of an unhandled traceback."""
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            "You need the Manage Server permission to use this.", ephemeral=True
        )
        return
    logger.exception("polyglot-modules command failed", exc_info=error)
    await interaction.response.send_message("Something went wrong.", ephemeral=True)


polyglot_modules.error(_polyglot_modules_error)


@tree.command(name="help", description="List everything this bot can do")
async def help_command(interaction: discord.Interaction):
    """Summarize every command in one place, grouped by module, instead of relying on Discord's picker."""
    lines = [
        "**Core**",
        "`/polyglot-modules <enable|disable> <module>` — turn a module on or off for this server",
        "",
        "**Translation** — for yourself",
        "`/setlanguage <code>` — set your language for auto-translated replies",
        "`/clearlanguage` — remove your language",
        "`/languages` — list every supported language code",
        'Right-click a message → Apps → "Translate Message" — one-off translation, works for anyone',
        "",
        "**Translation** — admin (Manage Server permission)",
        "`/setuserlanguage <member> <code>` — set someone else's language for them",
        "`/clearuserlanguage <member>` — remove another member's language",
        "`/setrolelanguage <role> <code>` — anyone with that role defaults to this language",
        "`/clearrolelanguage <role>` — remove a role's language mapping",
        "`/setserverlanguage <code>` — set this server's fallback translation language",
        "`/clearserverlanguage` — reset the server's fallback language to the default",
        "`/setbehavior <mode>` — choose reply-in-channel, thread, DM, or flag-reactions delivery",
        "`/clearbehavior` — reset translation delivery to the default (reply)",
        "`/channeltranslation <enable|disable> [channel]` — opt a channel out of translation "
        "(e.g. a flag-reaction role-picker)",
        "",
        "**Events** (module, disabled by default — `/polyglot-modules enable events`)",
        "`/createvent <title> <date> <time> <utc_offset> [duration_minutes] [description] "
        "[image]` — admin: create an event (also posts it to Discord's own Events tab)",
        "React ✅/❓/❌ on an event to RSVP — reminders go out to everyone who reacted ✅",
        "`/listevents` — list this server's upcoming events",
        'Right-click an event message → Apps → "Cancel Event" — admin: stop tracking it',
        "`/announceevent <title> <date> <time> <utc_offset> [reminder_minutes_before] "
        "[duration_minutes]` — admin: announce a real-world game event (e.g. Strongest "
        "Lord) to the announcements channel now, plus one reminder before it starts",
        "",
        "**Verification** (module, disabled by default — "
        "`/polyglot-modules enable verification`)",
        "React ✅ on a member's photo in the verify channel — admin (Admin/Officer/Leader "
        "role): grants the verified + member roles to whoever posted it",
        "",
        "**Polls** (module, disabled by default — `/polyglot-modules enable polls`)",
        "`/createpoll <question> <options> [duration_hours]` — admin: post a native Discord "
        "poll (`options` separated by `;`, 2-10 answers, default duration 24h, max 168h)",
        'Right-click a poll message → Apps → "End Poll" — admin: end it before it expires',
        "",
        "**Activity** (module, disabled by default — `/polyglot-modules enable activity`)",
        "`/activityreport [inactive_days]` — admin: list members inactive for at least "
        "N days (default 7), plus members with no recorded activity yet",
        "A weekly digest also posts automatically to the log channel once the module's "
        "been on for a week",
    ]
    await interaction.response.send_message("\n".join(lines), ephemeral=True)


def _register_module_commands() -> None:
    """Register every enabled module's slash/context-menu commands on the shared tree."""
    for module in MODULES.values():
        module.commands.register(tree)


_register_module_commands()


def main():
    """Entry point: run the Discord client."""
    client.run(DISCORD_BOT_TOKEN)


if __name__ == "__main__":
    main()
