import discord

from app.logger import logger
from app.modules.translation import storage, translator
from app.modules.translation.lang_codes import ISO_TO_FLAG, ISO_TO_NAME, color_for

# The server's own working language: always translated to, in addition to
# whatever individual members/roles have configured. An admin can override
# this per guild with /setserverlanguage; this is only the built-in fallback.
DEFAULT_SERVER_LANGUAGE = "en"

# How translations get posted: reply in-channel, thread, DM, or flag reactions
# (translate on demand). An admin can override this per guild with /setbehavior.
DEFAULT_DELIVERY_MODE = "reactions"

DISCORD_EMBEDS_PER_MESSAGE = 10
DISCORD_EMBED_TOTAL_CHAR_LIMIT = 5500  # conservative margin under Discord's 6000 cap
DISCORD_EMBED_DESCRIPTION_LIMIT = 4096


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


def _channel_member_languages(
    channel: discord.TextChannel | discord.Thread, exclude_user_id: int
) -> dict[discord.Member, str]:
    """Map each member who can see this channel to their configured language."""
    member_languages: dict[discord.Member, str] = {}
    for member in channel.guild.members:
        if member.id == exclude_user_id or member.bot:
            continue
        if not channel.permissions_for(member).view_channel:
            continue
        language = _resolve_member_language(member)
        if language:
            member_languages[member] = language
    return member_languages


def _channel_active_languages(
    channel: discord.TextChannel | discord.Thread, exclude_user_id: int
) -> set[str]:
    """Distinct languages (explicit or role-based) among members who can see this channel."""
    return set(_channel_member_languages(channel, exclude_user_id).values())


def _make_language_embed(
    target_lang: str, translated: str, part: tuple[int, int] | None = None
) -> discord.Embed:
    """One color-coded embed per language, so languages are distinguishable at a glance.

    `part` is (index, total) when a translation had to be split across multiple
    embeds because it exceeds Discord's per-embed description limit.
    """
    name = ISO_TO_NAME.get(target_lang, target_lang)
    title = f"{target_lang} — {name}"
    if part:
        title += f" ({part[0]}/{part[1]})"
    return discord.Embed(title=title, description=translated, color=color_for(target_lang))


def _make_language_embeds(target_lang: str, translated: str) -> list[discord.Embed]:
    """Split a translation across multiple embeds instead of silently truncating it
    at Discord's 4096-char embed description limit.
    """
    chunks = [
        translated[i : i + DISCORD_EMBED_DESCRIPTION_LIMIT]
        for i in range(0, len(translated), DISCORD_EMBED_DESCRIPTION_LIMIT)
    ] or [""]
    total = len(chunks)
    return [
        _make_language_embed(target_lang, chunk, part=(index + 1, total) if total > 1 else None)
        for index, chunk in enumerate(chunks)
    ]


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


async def _deliver_as_dm(
    member_languages: dict[discord.Member, str], embeds_by_lang: dict[str, list[discord.Embed]]
) -> str:
    """DM each member their translation privately, in their own configured language."""
    sent = 0
    failed = 0
    for member, language in member_languages.items():
        embeds = embeds_by_lang.get(language)
        if not embeds:
            continue
        try:
            for batch in _chunk_embeds(embeds):
                await member.send(embeds=batch)
            sent += 1
        except discord.HTTPException:
            logger.warning("could not DM %s (id=%s), likely has DMs closed", member, member.id)
            failed += 1

    if not failed:
        return f"Sent {sent} DM(s)."
    return f"Sent {sent} DM(s), {failed} failed (DMs closed)."


async def _deliver_as_reactions(message: discord.Message, target_languages: set[str]) -> str:
    """Add one flag reaction per active language; translation happens on demand.

    No translation happens here — but the message's own language is still
    detected (a cheap LibreTranslate-only call, not a full NLLB translation)
    so its flag is skipped: offering to "translate" a message into the
    language it's already written in is just noise. Languages without a known
    flag (e.g. Catalan) are skipped too, rather than failing the whole batch.
    """
    try:
        detected = await translator.detect_language(message.content)
    except Exception:
        logger.exception("language detection failed before adding reactions")
        detected = None

    added = 0
    for target_lang in sorted(target_languages):
        if target_lang == detected:
            continue
        flag = ISO_TO_FLAG.get(target_lang)
        if not flag:
            continue
        try:
            await message.add_reaction(flag)
            added += 1
        except discord.HTTPException:
            logger.warning("could not add reaction %s to message %s", flag, message.id)

    if not added:
        return "No flags to add (message already matches every active language, or no known flag)."
    return f"Added {added} flag reaction(s)."


async def _translate_single_language(message: discord.Message, target_lang: str) -> None:
    """Translate one message into one language and reply with it publicly.

    Used by the reactions delivery mode: called on demand when someone reacts
    with a flag, instead of translating every active language upfront.
    """
    try:
        translated, detected = await translator.translate(message.content, target_lang)
    except Exception:
        logger.exception("on-demand reaction translation failed for language %s", target_lang)
        return

    if detected == target_lang:
        return

    embeds = _make_language_embeds(target_lang, translated)
    try:
        for batch in _chunk_embeds(embeds):
            await message.reply(embeds=batch, mention_author=False)
    except discord.HTTPException:
        logger.exception("failed to send reaction-triggered translation reply")


_DELIVERY_MODES = {"reply": _deliver_as_reply, "thread": _deliver_as_thread}


def _author_language_for_reactions(message: discord.Message, mode: str) -> str | None:
    """In reactions mode, the author's own configured language is offered too.

    Unlike reply/thread (which would auto-translate at the author, unprompted
    noise), a flag is just an option to click -- so it's worth offering for
    when the author writes in a different language than the one they set for
    themselves.
    """
    if mode != "reactions":
        return None
    return _resolve_member_language(message.author)


async def _translate_and_deliver(message: discord.Message) -> str:
    """Core auto-translate logic: shared by the message handler and the admin retry command.

    Returns a short human-readable status, used by the retry command's response.
    """
    if not isinstance(message.channel, (discord.TextChannel, discord.Thread)):
        return "This only works in a text channel or thread."

    if isinstance(message.channel, discord.Thread):
        mode = "reply"  # Discord doesn't support nesting a thread in a thread
    else:
        mode = storage.get_delivery_mode(message.guild.id) or DEFAULT_DELIVERY_MODE

    member_languages: dict[discord.Member, str] = {}
    if mode == "dm":
        # No server-language fallback here: DM only goes to people who actually
        # configured a language, never as an unsolicited private message.
        member_languages = _channel_member_languages(message.channel, message.author.id)
        target_languages = set(member_languages.values())
    else:
        server_language = storage.get_server_language(message.guild.id) or DEFAULT_SERVER_LANGUAGE
        target_languages = _channel_active_languages(message.channel, message.author.id) | {
            server_language
        }
        author_language = _author_language_for_reactions(message, mode)
        if author_language:
            target_languages.add(author_language)
    logger.info(
        "guild %s: %d members cached, active languages in #%s: %s",
        message.guild.id,
        len(message.guild.members),
        message.channel.name,
        sorted(target_languages),
    )

    if mode == "reactions":
        return await _deliver_as_reactions(message, target_languages)

    embeds_by_lang: dict[str, list[discord.Embed]] = {}
    for target_lang in sorted(target_languages):
        try:
            translated, detected = await translator.translate(message.content, target_lang)
        except Exception:
            logger.exception("channel translation failed for language %s", target_lang)
            continue

        if detected == target_lang:
            continue

        embeds_by_lang[target_lang] = _make_language_embeds(target_lang, translated)

    if not embeds_by_lang:
        return "Nothing to translate (already matches every active language)."

    if mode == "dm":
        return await _deliver_as_dm(member_languages, embeds_by_lang)

    embeds = [embed for lang_embeds in embeds_by_lang.values() for embed in lang_embeds]
    deliver = _DELIVERY_MODES.get(mode, _deliver_as_reply)
    return await deliver(message, embeds)
