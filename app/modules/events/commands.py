import discord
from discord import app_commands

from app.logger import logger
from app.modules.checks import ModuleDisabledError, require_enabled
from app.modules.events import storage
from app.modules.events.logic import (
    DEFAULT_EVENT_DURATION_MINUTES,
    REMINDER_OFFSETS_MINUTES,
    RSVP_EMOJIS,
    cancel_event_and_notify,
    create_scheduled_event,
    make_event_embed,
    parse_event_timestamp,
    pending_reminder_offsets,
)
from app.modules.events.views import EventView


async def _admin_command_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
) -> None:
    """Shared error handler for events commands: clean message, no unhandled traceback."""
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
    logger.exception("events command failed", exc_info=error)
    await interaction.response.send_message("Something went wrong.", ephemeral=True)


@app_commands.command(
    name="createvent", description="Admin: create an alliance event with RSVP and reminders"
)
@app_commands.describe(
    title="Event title",
    date="Date, in YYYY-MM-DD",
    time="Time, in HH:MM (24h)",
    utc_offset="UTC offset for that time, e.g. -5, 0, +2",
    duration_minutes="How long the event runs, in minutes -- default 60",
    description="Extra details (coordinates, notes) -- optional",
    image="Screenshot or map image -- optional",
)
@require_enabled("events")
@app_commands.default_permissions(manage_guild=True)
@app_commands.checks.has_permissions(manage_guild=True)
async def createvent(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    interaction: discord.Interaction,
    title: str,
    date: str,
    time: str,
    utc_offset: str,
    duration_minutes: app_commands.Range[int, 1, 1440] = DEFAULT_EVENT_DURATION_MINUTES,
    description: str = "",
    image: discord.Attachment | None = None,
):
    """Post an event embed, add the RSVP reactions, and schedule its reminders."""
    if interaction.guild_id is None:
        await interaction.response.send_message(
            "This command only works inside a server.", ephemeral=True
        )
        return

    try:
        event_timestamp = parse_event_timestamp(date, time, utc_offset)
    except ValueError as exc:
        await interaction.response.send_message(str(exc), ephemeral=True)
        return

    created_at = int(discord.utils.utcnow().timestamp())
    pending = set(pending_reminder_offsets(created_at, event_timestamp))
    reminders_sent = [offset for offset in REMINDER_OFFSETS_MINUTES if offset not in pending]

    event = {
        "guild_id": interaction.guild_id,
        "channel_id": interaction.channel_id,
        "title": title,
        "description": description,
        "image_url": None,
        "timestamp": event_timestamp,
        "duration_minutes": duration_minutes,
        "created_by": interaction.user.id,
        "rsvps": {},
        "reminders_sent": reminders_sent,
        "discord_event_id": None,
    }

    files = []
    image_bytes = None
    if image is not None:
        image_bytes = await image.read()
        file = await image.to_file()
        files.append(file)
        event["image_url"] = f"attachment://{file.filename}"

    await interaction.response.send_message(
        embed=make_event_embed(event), files=files, view=EventView()
    )
    sent = await interaction.original_response()

    if image is not None and sent.embeds and sent.embeds[0].image:
        # Discord's own CDN URL for the now-uploaded attachment -- stable and
        # reusable in future embed edits (RSVP changes) without re-uploading.
        event["image_url"] = sent.embeds[0].image.url

    scheduled_event = await create_scheduled_event(interaction.guild, event, image_bytes)
    if scheduled_event is not None:
        event["discord_event_id"] = scheduled_event.id

    storage.save_event(sent.id, event)
    for emoji in RSVP_EMOJIS:
        try:
            await sent.add_reaction(emoji)
        except discord.HTTPException:
            logger.warning("could not add RSVP reaction %s to event %s", emoji, sent.id)

    logger.info(
        "event %s %r created by %s in guild %s, scheduled for %s",
        sent.id,
        title,
        interaction.user.id,
        interaction.guild_id,
        event_timestamp,
    )


createvent.error(_admin_command_error)


@app_commands.command(name="listevents", description="List this server's upcoming events")
@require_enabled("events")
async def listevents(interaction: discord.Interaction):
    """Show every future event in this guild, soonest first, with a going count."""
    if interaction.guild_id is None:
        await interaction.response.send_message(
            "This command only works inside a server.", ephemeral=True
        )
        return

    now = int(discord.utils.utcnow().timestamp())
    upcoming = sorted(
        (
            event
            for event in storage.all_events().values()
            if event["guild_id"] == interaction.guild_id and event["timestamp"] > now
        ),
        key=lambda event: event["timestamp"],
    )
    if not upcoming:
        await interaction.response.send_message("No upcoming events.", ephemeral=True)
        return

    lines = [
        f"**{event['title']}** — <t:{event['timestamp']}:R> — "
        f"{sum(1 for status in event['rsvps'].values() if status == 'going')} going"
        for event in upcoming
    ]
    await interaction.response.send_message("\n".join(lines), ephemeral=True)


listevents.error(_admin_command_error)


@app_commands.context_menu(name="Cancel Event")
@require_enabled("events")
@app_commands.default_permissions(manage_guild=True)
@app_commands.checks.has_permissions(manage_guild=True)
async def cancel_event(interaction: discord.Interaction, message: discord.Message):
    """Admin: stop tracking an event (no more reminders) and mark its post cancelled."""
    status = await cancel_event_and_notify(interaction.client, message, interaction.user.id)
    await interaction.response.send_message(status, ephemeral=True)


cancel_event.error(_admin_command_error)


def register(tree: app_commands.CommandTree) -> None:
    """Register every events slash/context-menu command on the shared tree."""
    for command in (createvent, listevents, cancel_event):
        tree.add_command(command)
