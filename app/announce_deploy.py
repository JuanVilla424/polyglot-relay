"""Stand-alone: connect just long enough to post one deploy announcement to
the log channel, then disconnect.

Invoked directly by deploy.sh after every successful deploy, for every
service -- not tied to the bot's own on_ready cycle, which only fires when
the bot container itself restarts and so could never announce an
nllb/libretranslate-only deploy.

Usage: python -m app.announce_deploy <service> <sha> <subject>
"""

import asyncio
import sys

import discord

from app.config import DISCORD_BOT_TOKEN
from app.discord_utils import report_to_log_channel


def build_message(service: str, sha: str, subject: str) -> str:
    """Format the deploy announcement posted to the log channel."""
    return f"🚀 Deployed `{service}` — `{sha}` {subject}"


async def _post_and_disconnect(message: str) -> None:
    client = discord.Client(intents=discord.Intents.default())

    @client.event
    async def on_ready():
        try:
            await report_to_log_channel(client, message)
        finally:
            await client.close()

    await client.start(DISCORD_BOT_TOKEN)


def main() -> None:
    """Parse argv and post the deploy announcement."""
    if len(sys.argv) != 4:
        print("Usage: python -m app.announce_deploy <service> <sha> <subject>", file=sys.stderr)
        sys.exit(1)
    service, sha, subject = sys.argv[1:4]
    asyncio.run(_post_and_disconnect(build_message(service, sha, subject)))


if __name__ == "__main__":
    main()
