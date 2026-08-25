"""Slack event listeners: message caching, flag reactions, the Translate
shortcut, and the /polyglot-lang slash command."""

from slack_sdk.errors import SlackApiError

from core import translator
from core.lang_codes import (
    FLAG_TO_ISO,
    ISO_TO_FLORES,
    ISO_TO_NAME,
    slack_emoji_to_flag,
    to_flores,
)
from slack_app import config, logic, message_cache, storage
from slack_app.logger import logger


async def _post_ephemeral(client, channel_id: str, user_id: str, text: str, blocks=None) -> None:
    """Send an only-you-can-see-this message, swallowing delivery failures
    (e.g. the bot was never invited to a private channel) into the log."""
    try:
        await client.chat_postEphemeral(channel=channel_id, user=user_id, text=text, blocks=blocks)
    except SlackApiError:
        logger.exception("could not post ephemeral message in channel %s", channel_id)


async def _report_activity(client, text: str) -> None:
    """Mirror of the Discord adapter's log-channel reporting, into a Slack channel."""
    if not config.LOG_CHANNEL_ID:
        return
    try:
        await client.chat_postMessage(channel=config.LOG_CHANNEL_ID, text=text)
    except SlackApiError:
        logger.exception("could not report activity to the log channel")


async def _fetch_message_text(client, channel_id: str, ts: str) -> str | None:
    """Last-resort single-message fetch for a cache miss.

    conversations.history is heavily rate-limited for new non-Marketplace
    apps (~1 request/minute since May 2025), so this only ever runs when the
    cache doesn't have the message -- and failure just means "too old".
    """
    try:
        response = await client.conversations_history(
            channel=channel_id, latest=ts, inclusive=True, limit=1
        )
    except SlackApiError:
        logger.warning("conversations.history fallback failed for %s@%s", channel_id, ts)
        return None
    messages = response.get("messages") or []
    if not messages or messages[0].get("ts") != ts:
        return None
    return messages[0].get("text") or None


async def _translate_and_post(client, channel_id: str, user_id: str, text: str, target: str):
    """Translate text and deliver it ephemerally to the requester."""
    try:
        translated, detected = await translator.translate(text, target)
    except translator.UnsupportedLanguageError:
        await _post_ephemeral(
            client, channel_id, user_id, "That message's language isn't supported for translation."
        )
        return
    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception("on-demand translation failed")
        await _post_ephemeral(client, channel_id, user_id, "Translation failed, try again later.")
        return

    if detected == target:
        await _post_ephemeral(
            client, channel_id, user_id, f"That message is already in `{target}`."
        )
        return

    await _post_ephemeral(
        client,
        channel_id,
        user_id,
        translated,
        blocks=logic.translation_blocks(detected, target, text, translated),
    )


async def handle_message_event(event: dict) -> None:
    """Cache plain user messages so flag reactions can find their text later.

    Subtyped events (bot_message, message_changed, channel_join, ...) and
    anything with a bot_id are skipped -- same bot-loop guard as the Discord
    adapter's author.bot check.
    """
    if event.get("subtype") or event.get("bot_id"):
        return
    text = event.get("text")
    channel_id = event.get("channel")
    ts = event.get("ts")
    if text and channel_id and ts:
        message_cache.remember(channel_id, ts, text)


async def handle_reaction_added(event: dict, client) -> None:
    """A flag-emoji reaction translates that message for the reactor, privately."""
    flag = slack_emoji_to_flag(event.get("reaction", ""))
    target = FLAG_TO_ISO.get(flag) if flag else None
    if target is None:
        return

    item = event.get("item") or {}
    channel_id = item.get("channel")
    ts = item.get("ts")
    user_id = event.get("user")
    if item.get("type") != "message" or not channel_id or not ts or not user_id:
        return

    text = message_cache.recall(channel_id, ts)
    if text is None:
        text = await _fetch_message_text(client, channel_id, ts)
    if text is None:
        await _post_ephemeral(
            client,
            channel_id,
            user_id,
            "That message is too old to translate on demand -- it's no longer "
            "in my recent-message cache.",
        )
        return

    logger.info(
        "flag reaction %s from %s on %s@%s -> translating to %s",
        event.get("reaction"),
        user_id,
        channel_id,
        ts,
        target,
    )
    await _translate_and_post(client, channel_id, user_id, text, target)


async def handle_translate_shortcut(ack, body: dict, client) -> None:
    """Message shortcut: translate to the requester's language, visible only
    to them. The shortcut payload carries the message text itself, so this
    path never touches the rate-limited history API."""
    await ack()

    message = body.get("message") or {}
    text = message.get("text") or ""
    channel_id = (body.get("channel") or {}).get("id")
    user_id = (body.get("user") or {}).get("id")
    team_id = (body.get("team") or {}).get("id") or ""
    if not channel_id or not user_id:
        return
    if not text:
        await _post_ephemeral(client, channel_id, user_id, "Nothing to translate in that message.")
        return

    target = storage.get_user_language(team_id, user_id) or config.DEFAULT_TARGET_LANGUAGE
    await _translate_and_post(client, channel_id, user_id, text, target)


async def handle_polyglot_lang(ack, command: dict, client) -> None:
    """/polyglot-lang <code>|clear|list -- self-service language preference."""
    text = (command.get("text") or "").strip().lower()
    team_id = command.get("team_id") or ""
    user_id = command.get("user_id") or ""

    if not text or text == "help":
        await ack(
            "Usage: `/polyglot-lang <code>` to set your language (e.g. `es`), "
            "`/polyglot-lang clear` to remove it, `/polyglot-lang list` to see "
            "every supported code."
        )
        return

    if text == "list":
        lines = [f"`{code}` — {ISO_TO_NAME.get(code, '?')}" for code in sorted(ISO_TO_FLORES)]
        await ack("*Supported languages:*\n" + "\n".join(lines))
        return

    if text == "clear":
        storage.clear_user_language(team_id, user_id)
        await ack("Your language preference was removed.")
        await _report_activity(client, f"🚫 <@{user_id}> cleared their language")
        return

    if to_flores(text) is None:
        await ack(f"`{text}` isn't a supported language code. Try `/polyglot-lang list`.")
        await _report_activity(client, f"⚠️ <@{user_id}> tried `{text}` (not supported)")
        return

    storage.set_user_language(team_id, user_id, text)
    await ack(f"Language set to `{text}`. Flag reactions and the Translate shortcut will use it.")
    await _report_activity(client, f"🌐 <@{user_id}> set their language to `{text}`")


def register(app) -> None:
    """Wire every listener onto the Bolt app."""
    app.event("message")(handle_message_event)
    app.event("reaction_added")(handle_reaction_added)
    app.shortcut("translate_message")(handle_translate_shortcut)
    app.command("/polyglot-lang")(handle_polyglot_lang)
