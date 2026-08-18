import discord
from discord import app_commands

from app.discord_utils import report_to_log_channel as _report_language_change
from app.logger import logger
from app.modules.translation import storage, translator
from app.modules.translation.lang_codes import ISO_TO_FLORES, ISO_TO_NAME, to_flores
from app.modules.translation.logic import (
    DEFAULT_DELIVERY_MODE,
    DEFAULT_SERVER_LANGUAGE,
    _resolve_member_language,
    _translate_and_deliver,
)


async def _admin_command_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
) -> None:
    """Shared error handler for admin-only commands: clean message, no unhandled traceback."""
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            "You need the Manage Server permission to use this.", ephemeral=True
        )
        command_name = interaction.command.name if interaction.command else "?"
        await _report_language_change(
            interaction.client,
            f"⛔ {interaction.user.mention} tried to use `/{command_name}` without permission",
        )
        return
    logger.exception("admin command failed", exc_info=error)
    await interaction.response.send_message("Something went wrong.", ephemeral=True)


@app_commands.command(
    name="setlanguage", description="Set your preferred language for auto-translated replies"
)
@app_commands.describe(code="Language code, e.g. es, en, fr")
async def setlanguage(interaction: discord.Interaction, code: str):
    """Store the invoking user's preferred language for this guild."""
    if interaction.guild_id is None:
        await interaction.response.send_message(
            "This command only works inside a server.", ephemeral=True
        )
        return
    if to_flores(code) is None:
        await interaction.response.send_message(
            f"`{code}` isn't a supported language code.", ephemeral=True
        )
        await _report_language_change(
            interaction.client,
            f"⚠️ {interaction.user.mention} tried `{code}` for themselves (not supported)",
        )
        return
    storage.set_user_language(interaction.guild_id, interaction.user.id, code.lower())
    await interaction.response.send_message(
        f"Language set to `{code.lower()}`. You'll be included in translation replies from now on.",
        ephemeral=True,
    )
    await _report_language_change(
        interaction.client, f"🌐 {interaction.user.mention} set their language to `{code.lower()}`"
    )


@app_commands.command(name="clearlanguage", description="Remove your preferred language")
async def clearlanguage(interaction: discord.Interaction):
    """Stop auto-translated replies for the invoking user in this guild."""
    if interaction.guild_id is None:
        await interaction.response.send_message(
            "This command only works inside a server.", ephemeral=True
        )
        return
    storage.clear_user_language(interaction.guild_id, interaction.user.id)
    await interaction.response.send_message("Your language preference was removed.", ephemeral=True)
    await _report_language_change(
        interaction.client, f"🚫 {interaction.user.mention} cleared their language"
    )


@app_commands.command(
    name="setuserlanguage", description="Admin: set another member's translation language"
)
@app_commands.describe(user="The member to configure", code="Language code, e.g. es, en, fr")
@app_commands.default_permissions(manage_guild=True)
@app_commands.checks.has_permissions(manage_guild=True)
async def setuserlanguage(interaction: discord.Interaction, user: discord.Member, code: str):
    """Let an admin set another member's language without them running a command."""
    if to_flores(code) is None:
        await interaction.response.send_message(
            f"`{code}` isn't a supported language code.", ephemeral=True
        )
        await _report_language_change(
            interaction.client,
            f"⚠️ {interaction.user.mention} tried `{code}` for {user.mention} (not supported)",
        )
        return
    storage.set_user_language(user.guild.id, user.id, code.lower())
    await interaction.response.send_message(
        f"Language for {user.mention} set to `{code.lower()}`.", ephemeral=True
    )
    await _report_language_change(
        interaction.client,
        f"🌐 {interaction.user.mention} set {user.mention}'s language to `{code.lower()}`",
    )


setuserlanguage.error(_admin_command_error)


@app_commands.command(
    name="clearuserlanguage", description="Admin: remove a member's translation language"
)
@app_commands.describe(user="The member to clear")
@app_commands.default_permissions(manage_guild=True)
@app_commands.checks.has_permissions(manage_guild=True)
async def clearuserlanguage(interaction: discord.Interaction, user: discord.Member):
    """Let an admin remove another member's explicit language."""
    storage.clear_user_language(user.guild.id, user.id)
    await interaction.response.send_message(
        f"Language for {user.mention} was removed.", ephemeral=True
    )
    await _report_language_change(
        interaction.client, f"🚫 {interaction.user.mention} cleared {user.mention}'s language"
    )


clearuserlanguage.error(_admin_command_error)


@app_commands.command(
    name="setrolelanguage", description="Admin: assign a translation language to a role"
)
@app_commands.describe(role="The role to configure", code="Language code, e.g. es, en, fr")
@app_commands.default_permissions(manage_guild=True)
@app_commands.checks.has_permissions(manage_guild=True)
async def setrolelanguage(interaction: discord.Interaction, role: discord.Role, code: str):
    """Members with this role default to this language unless they set their own."""
    if to_flores(code) is None:
        await interaction.response.send_message(
            f"`{code}` isn't a supported language code.", ephemeral=True
        )
        await _report_language_change(
            interaction.client,
            f"⚠️ {interaction.user.mention} tried `{code}` for {role.mention} (not supported)",
        )
        return
    storage.set_role_language(role.guild.id, role.id, code.lower())
    await interaction.response.send_message(
        f"Members with {role.mention} now default to `{code.lower()}` "
        "unless they set their own language.",
        ephemeral=True,
    )
    await _report_language_change(
        interaction.client,
        f"🌐 {interaction.user.mention} mapped {role.mention} to `{code.lower()}`",
    )


setrolelanguage.error(_admin_command_error)


@app_commands.command(
    name="clearrolelanguage", description="Admin: remove a role's translation language"
)
@app_commands.describe(role="The role to clear")
@app_commands.default_permissions(manage_guild=True)
@app_commands.checks.has_permissions(manage_guild=True)
async def clearrolelanguage(interaction: discord.Interaction, role: discord.Role):
    """Let an admin remove a role's language mapping."""
    storage.clear_role_language(role.guild.id, role.id)
    await interaction.response.send_message(
        f"Language mapping for {role.mention} was removed.", ephemeral=True
    )
    await _report_language_change(
        interaction.client, f"🚫 {interaction.user.mention} cleared {role.mention}'s language"
    )


clearrolelanguage.error(_admin_command_error)


@app_commands.command(
    name="setserverlanguage",
    description="Admin: set this server's fallback translation language",
)
@app_commands.describe(code="Language code, e.g. es, en, fr")
@app_commands.default_permissions(manage_guild=True)
@app_commands.checks.has_permissions(manage_guild=True)
async def setserverlanguage(interaction: discord.Interaction, code: str):
    """Every translation reply always includes this language, on top of members/roles."""
    if interaction.guild_id is None:
        await interaction.response.send_message(
            "This command only works inside a server.", ephemeral=True
        )
        return
    if to_flores(code) is None:
        await interaction.response.send_message(
            f"`{code}` isn't a supported language code.", ephemeral=True
        )
        await _report_language_change(
            interaction.client,
            f"⚠️ {interaction.user.mention} tried `{code}` for the server language (not supported)",
        )
        return
    storage.set_server_language(interaction.guild_id, code.lower())
    await interaction.response.send_message(
        f"Server fallback language set to `{code.lower()}`.", ephemeral=True
    )
    await _report_language_change(
        interaction.client,
        f"🌐 {interaction.user.mention} set the server language to `{code.lower()}`",
    )


setserverlanguage.error(_admin_command_error)


@app_commands.command(
    name="clearserverlanguage",
    description=f"Admin: reset the server's fallback language to the default ({DEFAULT_SERVER_LANGUAGE})",
)
@app_commands.default_permissions(manage_guild=True)
@app_commands.checks.has_permissions(manage_guild=True)
async def clearserverlanguage(interaction: discord.Interaction):
    """Let an admin drop the guild's override and go back to the built-in default."""
    if interaction.guild_id is None:
        await interaction.response.send_message(
            "This command only works inside a server.", ephemeral=True
        )
        return
    storage.clear_server_language(interaction.guild_id)
    await interaction.response.send_message(
        f"Server fallback language reset to the default (`{DEFAULT_SERVER_LANGUAGE}`).",
        ephemeral=True,
    )
    await _report_language_change(
        interaction.client, f"🚫 {interaction.user.mention} cleared the server language"
    )


clearserverlanguage.error(_admin_command_error)


@app_commands.command(
    name="setbehavior",
    description="Admin: choose how translations are delivered in this server",
)
@app_commands.describe(
    mode="Reply inline in the channel, open a thread, DM each person, or use flag reactions"
)
@app_commands.choices(
    mode=[
        app_commands.Choice(name="Reply in the channel", value="reply"),
        app_commands.Choice(name="Open a thread", value="thread"),
        app_commands.Choice(name="DM each person privately", value="dm"),
        app_commands.Choice(
            name="Flag reactions, translate on demand (default)", value="reactions"
        ),
    ]
)
@app_commands.default_permissions(manage_guild=True)
@app_commands.checks.has_permissions(manage_guild=True)
async def setbehavior(interaction: discord.Interaction, mode: app_commands.Choice[str]):
    """Let an admin pick reply-in-channel, thread, DM, or flag-reactions delivery for this guild."""
    if interaction.guild_id is None:
        await interaction.response.send_message(
            "This command only works inside a server.", ephemeral=True
        )
        return
    storage.set_delivery_mode(interaction.guild_id, mode.value)
    await interaction.response.send_message(
        f"Translation delivery set to **{mode.name}**.", ephemeral=True
    )
    await _report_language_change(
        interaction.client,
        f"🌐 {interaction.user.mention} set translation delivery to `{mode.value}`",
    )


setbehavior.error(_admin_command_error)


@app_commands.command(
    name="clearbehavior",
    description=f"Admin: reset translation delivery to the default ({DEFAULT_DELIVERY_MODE})",
)
@app_commands.default_permissions(manage_guild=True)
@app_commands.checks.has_permissions(manage_guild=True)
async def clearbehavior(interaction: discord.Interaction):
    """Let an admin drop the guild's delivery override and go back to the default."""
    if interaction.guild_id is None:
        await interaction.response.send_message(
            "This command only works inside a server.", ephemeral=True
        )
        return
    storage.clear_delivery_mode(interaction.guild_id)
    await interaction.response.send_message(
        f"Translation delivery reset to the default (`{DEFAULT_DELIVERY_MODE}`).",
        ephemeral=True,
    )
    await _report_language_change(
        interaction.client, f"🚫 {interaction.user.mention} cleared the translation delivery mode"
    )


clearbehavior.error(_admin_command_error)


@app_commands.command(
    name="channeltranslation",
    description="Admin: turn translation on or off for a specific channel",
)
@app_commands.describe(
    action="Enable or disable",
    channel="Which channel (defaults to the one you're in)",
)
@app_commands.choices(
    action=[
        app_commands.Choice(name="Enable", value="enable"),
        app_commands.Choice(name="Disable", value="disable"),
    ]
)
@app_commands.default_permissions(manage_guild=True)
@app_commands.checks.has_permissions(manage_guild=True)
async def channeltranslation(
    interaction: discord.Interaction,
    action: app_commands.Choice[str],
    channel: discord.TextChannel | None = None,
):
    """Let an admin opt a channel out of translation, e.g. a flag-reaction role-picker."""
    target = channel or interaction.channel
    if interaction.guild_id is None or not isinstance(
        target, (discord.TextChannel, discord.Thread)
    ):
        await interaction.response.send_message(
            "This only works on a text channel inside a server.", ephemeral=True
        )
        return
    excluded = action.value == "disable"
    storage.set_channel_excluded(interaction.guild_id, target.id, excluded)
    await interaction.response.send_message(
        f"Translation {'disabled' if excluded else 'enabled'} for {target.mention}.",
        ephemeral=True,
    )
    await _report_language_change(
        interaction.client,
        f"🌐 {interaction.user.mention} {'disabled' if excluded else 'enabled'} "
        f"translation in {target.mention}",
    )


channeltranslation.error(_admin_command_error)


@app_commands.command(name="languages", description="List the language codes this bot supports")
async def languages(interaction: discord.Interaction):
    """Show every ISO 639-1 code mapped in lang_codes.py, with its language name."""
    lines = [f"`{code}` — {ISO_TO_NAME.get(code, '?')}" for code in sorted(ISO_TO_FLORES)]
    await interaction.response.send_message(
        "**Supported languages:**\n" + "\n".join(lines), ephemeral=True
    )


@app_commands.context_menu(name="Translate Message")
async def translate_message(interaction: discord.Interaction, message: discord.Message):
    """On-demand ephemeral translation, exempt from the message content intent."""
    if not message.content:
        await interaction.response.send_message(
            "Nothing to translate in that message.", ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=True)

    target = None
    if isinstance(interaction.user, discord.Member):
        target = _resolve_member_language(interaction.user)
    target = target or "en"

    try:
        translated, detected = await translator.translate(message.content, target)
    except translator.UnsupportedLanguageError:
        await interaction.followup.send(
            "That message's language isn't supported for translation.", ephemeral=True
        )
        return
    except Exception:
        logger.exception("on-demand translation failed")
        await interaction.followup.send("Translation failed, try again later.", ephemeral=True)
        return

    await interaction.followup.send(f"**{detected} → {target}**\n{translated}", ephemeral=True)


@app_commands.context_menu(name="Retry Translation")
@app_commands.default_permissions(manage_guild=True)
@app_commands.checks.has_permissions(manage_guild=True)
async def retry_translation(interaction: discord.Interaction, message: discord.Message):
    """Admin fallback: manually re-run the auto-translate logic on one message."""
    if not message.content:
        await interaction.response.send_message(
            "Nothing to translate in that message.", ephemeral=True
        )
        return
    await interaction.response.defer(ephemeral=True)
    status = await _translate_and_deliver(message)
    await interaction.followup.send(status, ephemeral=True)


retry_translation.error(_admin_command_error)


def register(tree: app_commands.CommandTree) -> None:
    """Register every translation slash/context-menu command on the shared tree."""
    for command in (
        setlanguage,
        clearlanguage,
        setuserlanguage,
        clearuserlanguage,
        setrolelanguage,
        clearrolelanguage,
        setserverlanguage,
        clearserverlanguage,
        setbehavior,
        clearbehavior,
        channeltranslation,
        languages,
        translate_message,
        retry_translation,
    ):
        tree.add_command(command)
