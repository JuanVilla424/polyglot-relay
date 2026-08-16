import discord
from discord import app_commands

from app import storage, translator
from app.config import DISCORD_BOT_TOKEN
from app.lang_codes import to_flores
from app.logger import logger

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


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


def _resolve_guild_recipients(guild: discord.Guild) -> dict[int, str]:
    """Every member with an explicit or role-based language, keyed by user id."""
    recipients: dict[int, str] = {}
    role_languages = storage.guild_role_languages(guild.id)
    if role_languages:
        for member in guild.members:
            for role in member.roles:
                if role.id in role_languages:
                    recipients[member.id] = role_languages[role.id]
                    break
    recipients.update(storage.guild_user_languages(guild.id))
    return recipients


async def _admin_command_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
) -> None:
    """Shared error handler for admin-only commands: clean message, no unhandled traceback."""
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            "You need the Manage Server permission to use this.", ephemeral=True
        )
        return
    logger.exception("admin command failed", exc_info=error)
    await interaction.response.send_message("Something went wrong.", ephemeral=True)


@tree.command(name="setlanguage", description="Set your preferred language for auto-translated DMs")
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
        return
    storage.set_user_language(interaction.guild_id, interaction.user.id, code.lower())
    await interaction.response.send_message(
        f"Language set to `{code.lower()}`. You'll get DMs with translations from now on.",
        ephemeral=True,
    )


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
        return
    storage.set_user_language(user.guild.id, user.id, code.lower())
    await interaction.response.send_message(
        f"Language for {user.mention} set to `{code.lower()}`.", ephemeral=True
    )


setuserlanguage.error(_admin_command_error)


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
        return
    storage.set_role_language(role.guild.id, role.id, code.lower())
    await interaction.response.send_message(
        f"Members with {role.mention} now default to `{code.lower()}` "
        "unless they set their own language.",
        ephemeral=True,
    )


setrolelanguage.error(_admin_command_error)


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
    logger.info("logged in as %s", client.user)


@client.event
async def on_message(message: discord.Message):
    """DM each opted-in guild member (explicit or role-based) a translation, skipping the author."""
    if message.author.bot or message.guild is None or not message.content:
        return

    recipients = _resolve_guild_recipients(message.guild)
    recipients.pop(message.author.id, None)
    if not recipients:
        return

    for user_id, target_lang in recipients.items():
        try:
            translated, detected = await translator.translate(message.content, target_lang)
        except Exception:
            logger.exception("auto-translate failed for user %s", user_id)
            continue

        if detected == target_lang:
            continue

        try:
            user = client.get_user(user_id) or await client.fetch_user(user_id)
            await user.send(
                f"**#{message.channel.name}** · {message.author.display_name} "
                f"({detected} → {target_lang})\n{translated}"
            )
        except discord.Forbidden:
            logger.warning("cannot DM user %s (DMs closed or no shared server)", user_id)
        except discord.HTTPException:
            logger.exception("failed to DM user %s", user_id)


def main():
    """Entry point: run the Discord client."""
    client.run(DISCORD_BOT_TOKEN)


if __name__ == "__main__":
    main()
