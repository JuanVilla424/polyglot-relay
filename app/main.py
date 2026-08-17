from pathlib import Path

import discord
from discord import app_commands
from discord.ext import tasks

from app import storage, translator
from app.config import DISCORD_BOT_TOKEN, LOG_CHANNEL_ID
from app.lang_codes import ISO_TO_FLORES, ISO_TO_NAME, color_for, to_flores
from app.logger import logger

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

HEARTBEAT_PATH = Path("/tmp/healthy")

# The server's own working language: always translated to, in addition to
# whatever individual members/roles have configured. An admin can override
# this per guild with /setserverlanguage; this is only the built-in fallback.
DEFAULT_SERVER_LANGUAGE = "en"

# How translations get posted: a native reply in-channel, or a thread on the
# original message. An admin can override this per guild with /setbehavior.
DEFAULT_DELIVERY_MODE = "reply"


@tasks.loop(seconds=30)
async def _heartbeat() -> None:
    """Touch a file the Docker healthcheck watches, proving the gateway is alive."""
    HEARTBEAT_PATH.touch()


def _resolve_member_language(member: discord.Member) -> str | None:
    """An explicit /setlanguage or /setuserlanguage wins; otherwise fall back to roles."""
    explicit = storage.get_user_language(member.guild.id, member.id)
    if explicit:
        return explicit
    role_languages = storage.guild_role_languages(member.guild.id)
    for role in member.roles:
        if role.id in role_languages:
            return role_languages[role.id]
    return None


def _channel_active_languages(
    channel: discord.TextChannel | discord.Thread, exclude_user_id: int
) -> set[str]:
    """Distinct languages (explicit or role-based) among members who can see this channel."""
    active_languages: set[str] = set()
    for member in channel.guild.members:
        if member.id == exclude_user_id or member.bot:
            continue
        if not channel.permissions_for(member).view_channel:
            continue
        language = _resolve_member_language(member)
        if language:
            active_languages.add(language)
    return active_languages


async def _report_language_change(message: str) -> None:
    """Best-effort post to the configured log channel; never breaks the caller."""
    if LOG_CHANNEL_ID is None:
        return
    try:
        channel = client.get_channel(LOG_CHANNEL_ID) or await client.fetch_channel(LOG_CHANNEL_ID)
        await channel.send(message)
    except (discord.Forbidden, discord.NotFound, discord.HTTPException):
        logger.warning("could not post to log channel %s", LOG_CHANNEL_ID)


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
            f"⛔ {interaction.user.mention} tried to use `/{command_name}` without permission"
        )
        return
    logger.exception("admin command failed", exc_info=error)
    await interaction.response.send_message("Something went wrong.", ephemeral=True)


@tree.command(
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
            f"⚠️ {interaction.user.mention} tried `{code}` for themselves (not supported)"
        )
        return
    storage.set_user_language(interaction.guild_id, interaction.user.id, code.lower())
    await interaction.response.send_message(
        f"Language set to `{code.lower()}`. You'll be included in translation replies from now on.",
        ephemeral=True,
    )
    await _report_language_change(
        f"🌐 {interaction.user.mention} set their language to `{code.lower()}`"
    )


@tree.command(name="clearlanguage", description="Remove your preferred language")
async def clearlanguage(interaction: discord.Interaction):
    """Stop auto-translated replies for the invoking user in this guild."""
    if interaction.guild_id is None:
        await interaction.response.send_message(
            "This command only works inside a server.", ephemeral=True
        )
        return
    storage.clear_user_language(interaction.guild_id, interaction.user.id)
    await interaction.response.send_message("Your language preference was removed.", ephemeral=True)
    await _report_language_change(f"🚫 {interaction.user.mention} cleared their language")


@tree.command(
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
            f"⚠️ {interaction.user.mention} tried `{code}` for {user.mention} (not supported)"
        )
        return
    storage.set_user_language(user.guild.id, user.id, code.lower())
    await interaction.response.send_message(
        f"Language for {user.mention} set to `{code.lower()}`.", ephemeral=True
    )
    await _report_language_change(
        f"🌐 {interaction.user.mention} set {user.mention}'s language to `{code.lower()}`"
    )


setuserlanguage.error(_admin_command_error)


@tree.command(name="clearuserlanguage", description="Admin: remove a member's translation language")
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
        f"🚫 {interaction.user.mention} cleared {user.mention}'s language"
    )


clearuserlanguage.error(_admin_command_error)


@tree.command(name="setrolelanguage", description="Admin: assign a translation language to a role")
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
            f"⚠️ {interaction.user.mention} tried `{code}` for {role.mention} (not supported)"
        )
        return
    storage.set_role_language(role.guild.id, role.id, code.lower())
    await interaction.response.send_message(
        f"Members with {role.mention} now default to `{code.lower()}` "
        "unless they set their own language.",
        ephemeral=True,
    )
    await _report_language_change(
        f"🌐 {interaction.user.mention} mapped {role.mention} to `{code.lower()}`"
    )


setrolelanguage.error(_admin_command_error)


@tree.command(name="clearrolelanguage", description="Admin: remove a role's translation language")
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
        f"🚫 {interaction.user.mention} cleared {role.mention}'s language"
    )


clearrolelanguage.error(_admin_command_error)


@tree.command(
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
            f"⚠️ {interaction.user.mention} tried `{code}` for the server language (not supported)"
        )
        return
    storage.set_server_language(interaction.guild_id, code.lower())
    await interaction.response.send_message(
        f"Server fallback language set to `{code.lower()}`.", ephemeral=True
    )
    await _report_language_change(
        f"🌐 {interaction.user.mention} set the server language to `{code.lower()}`"
    )


setserverlanguage.error(_admin_command_error)


@tree.command(
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
    await _report_language_change(f"🚫 {interaction.user.mention} cleared the server language")


clearserverlanguage.error(_admin_command_error)


@tree.command(
    name="setbehavior",
    description="Admin: choose how translations are delivered in this server",
)
@app_commands.describe(mode="Reply inline in the channel, or open a thread")
@app_commands.choices(
    mode=[
        app_commands.Choice(name="Reply in the channel (default)", value="reply"),
        app_commands.Choice(name="Open a thread", value="thread"),
    ]
)
@app_commands.default_permissions(manage_guild=True)
@app_commands.checks.has_permissions(manage_guild=True)
async def setbehavior(interaction: discord.Interaction, mode: app_commands.Choice[str]):
    """Let an admin pick reply-in-channel or thread delivery for this guild."""
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
        f"🌐 {interaction.user.mention} set translation delivery to `{mode.value}`"
    )


setbehavior.error(_admin_command_error)


@tree.command(
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
        f"🚫 {interaction.user.mention} cleared the translation delivery mode"
    )


clearbehavior.error(_admin_command_error)


@tree.command(name="languages", description="List the language codes this bot supports")
async def languages(interaction: discord.Interaction):
    """Show every ISO 639-1 code mapped in app/lang_codes.py, with its language name."""
    lines = [f"`{code}` — {ISO_TO_NAME.get(code, '?')}" for code in sorted(ISO_TO_FLORES)]
    await interaction.response.send_message(
        "**Supported languages:**\n" + "\n".join(lines), ephemeral=True
    )


@tree.command(name="help", description="List everything this bot can do")
async def help_command(interaction: discord.Interaction):
    """Summarize every command in one place instead of relying on Discord's picker."""
    lines = [
        "**For yourself**",
        "`/setlanguage <code>` — set your language for auto-translated replies",
        "`/clearlanguage` — remove your language",
        "`/languages` — list every supported language code",
        'Right-click a message → Apps → "Translate Message" — one-off translation, works for anyone',
        "",
        "**Admin (Manage Server permission)**",
        "`/setuserlanguage <member> <code>` — set someone else's language for them",
        "`/clearuserlanguage <member>` — remove another member's language",
        "`/setrolelanguage <role> <code>` — anyone with that role defaults to this language",
        "`/clearrolelanguage <role>` — remove a role's language mapping",
        "`/setserverlanguage <code>` — set this server's fallback translation language",
        "`/clearserverlanguage` — reset the server's fallback language to the default",
        "`/setbehavior <mode>` — choose reply-in-channel or thread delivery for this server",
        "`/clearbehavior` — reset translation delivery to the default (reply)",
    ]
    await interaction.response.send_message("\n".join(lines), ephemeral=True)


@tree.context_menu(name="Translate Message")
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


@client.event
async def on_ready():
    """Sync application commands with Discord once the client is logged in."""
    await tree.sync()
    if not _heartbeat.is_running():
        _heartbeat.start()
    logger.info("logged in as %s", client.user)


DISCORD_EMBEDS_PER_MESSAGE = 10
DISCORD_EMBED_TOTAL_CHAR_LIMIT = 5500  # conservative margin under Discord's 6000 cap


def _make_language_embed(target_lang: str, translated: str) -> discord.Embed:
    """One color-coded embed per language, so languages are distinguishable at a glance."""
    name = ISO_TO_NAME.get(target_lang, target_lang)
    return discord.Embed(
        title=f"{target_lang} — {name}",
        description=translated[:4096],
        color=color_for(target_lang),
    )


def _chunk_embeds(embeds: list[discord.Embed]) -> list[list[discord.Embed]]:
    """Group embeds into batches respecting Discord's per-message embed count/size limits."""
    chunks: list[list[discord.Embed]] = []
    current: list[discord.Embed] = []
    current_len = 0
    for embed in embeds:
        embed_len = len(embed.title or "") + len(embed.description or "")
        if current and (
            len(current) >= DISCORD_EMBEDS_PER_MESSAGE
            or current_len + embed_len > DISCORD_EMBED_TOTAL_CHAR_LIMIT
        ):
            chunks.append(current)
            current = []
            current_len = 0
        current.append(embed)
        current_len += embed_len
    if current:
        chunks.append(current)
    return chunks


async def _deliver_as_reply(message: discord.Message, embeds: list[discord.Embed]) -> str:
    """Post the translation as a native reply in the same channel."""
    try:
        for batch in _chunk_embeds(embeds):
            await message.reply(embeds=batch, mention_author=False)
    except discord.HTTPException:
        logger.exception("failed to send translation reply")
        return "Failed to send the translation (I may lack permission)."

    return "Translation sent."


async def _deliver_as_thread(message: discord.Message, embeds: list[discord.Embed]) -> str:
    """Post the translation in a thread opened on the original message."""
    try:
        thread = await message.create_thread(name="🌐 Translation", auto_archive_duration=1440)
        for batch in _chunk_embeds(embeds):
            await thread.send(embeds=batch)
    except discord.HTTPException:
        logger.exception("failed to create/post translation thread")
        return "Failed to create the thread (it may already have one, or I lack permission)."

    return "Thread created."


_DELIVERY_MODES = {"reply": _deliver_as_reply, "thread": _deliver_as_thread}


async def _translate_and_deliver(message: discord.Message) -> str:
    """Core auto-translate logic: shared by on_message and the admin retry command.

    Returns a short human-readable status, used by the retry command's response.
    """
    if not isinstance(message.channel, (discord.TextChannel, discord.Thread)):
        return "This only works in a text channel or thread."

    server_language = storage.get_server_language(message.guild.id) or DEFAULT_SERVER_LANGUAGE
    target_languages = _channel_active_languages(message.channel, message.author.id) | {
        server_language
    }
    logger.info(
        "guild %s: %d members cached, active languages in #%s: %s",
        message.guild.id,
        len(message.guild.members),
        message.channel.name,
        sorted(target_languages),
    )

    embeds = []
    for target_lang in sorted(target_languages):
        try:
            translated, detected = await translator.translate(message.content, target_lang)
        except Exception:
            logger.exception("channel translation failed for language %s", target_lang)
            continue

        if detected == target_lang:
            continue

        embeds.append(_make_language_embed(target_lang, translated))

    if not embeds:
        return "Nothing to translate (already matches every active language)."

    if isinstance(message.channel, discord.Thread):
        deliver = _deliver_as_reply  # Discord doesn't support nesting a thread in a thread
    else:
        mode = storage.get_delivery_mode(message.guild.id) or DEFAULT_DELIVERY_MODE
        deliver = _DELIVERY_MODES.get(mode, _deliver_as_reply)
    return await deliver(message, embeds)


@client.event
async def on_message(message: discord.Message):
    """Deliver the message translated into every language active here."""
    if message.author.bot or message.guild is None or not message.content:
        return
    await _translate_and_deliver(message)


@tree.context_menu(name="Retry Translation")
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


def main():
    """Entry point: run the Discord client."""
    client.run(DISCORD_BOT_TOKEN)


if __name__ == "__main__":
    main()
