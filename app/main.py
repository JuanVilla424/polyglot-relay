import discord
from discord import app_commands

from app import storage, translator
from app.config import DISCORD_BOT_TOKEN
from app.logger import logger

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


@tree.command(name="setlanguage", description="Set your preferred language for auto-translated DMs")
@app_commands.describe(code="Language code, e.g. es, en, fr")
async def setlanguage(interaction: discord.Interaction, code: str):
    """Store the invoking user's preferred language for this guild."""
    if interaction.guild_id is None:
        await interaction.response.send_message(
            "This command only works inside a server.", ephemeral=True
        )
        return
    storage.set_user_language(interaction.guild_id, interaction.user.id, code.lower())
    await interaction.response.send_message(
        f"Language set to `{code.lower()}`. You'll get DMs with translations from now on.",
        ephemeral=True,
    )


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
    if interaction.guild_id is not None:
        target = storage.get_user_language(interaction.guild_id, interaction.user.id)
    target = target or "en"

    try:
        translated, detected = await translator.translate(message.content, target)
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
    """DM each opted-in guild member a translation, skipping the author."""
    if message.author.bot or message.guild is None or not message.content:
        return

    recipients = storage.guild_user_languages(message.guild.id)
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
