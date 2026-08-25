"""Entry point for the Slack adapter: Bolt over Socket Mode.

Socket Mode keeps everything outbound (a websocket to Slack over 443), so the
container needs no public endpoint and no inbound ports -- the same posture as
the Discord gateway connection.
"""

import asyncio
from pathlib import Path

from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from slack_bolt.async_app import AsyncApp

from slack_app import handlers
from slack_app.config import SLACK_APP_TOKEN, SLACK_BOT_TOKEN
from slack_app.logger import logger

HEARTBEAT_PATH = Path("/tmp/healthy")
_HEARTBEAT_SECONDS = 30

app = AsyncApp(token=SLACK_BOT_TOKEN)
handlers.register(app)


async def _heartbeat() -> None:
    """Touch a file the Docker healthcheck watches, proving the loop is alive."""
    while True:
        HEARTBEAT_PATH.touch()
        await asyncio.sleep(_HEARTBEAT_SECONDS)


async def _run() -> None:
    """Start the heartbeat and hand the loop to the socket-mode handler."""
    heartbeat_task = asyncio.create_task(_heartbeat())
    handler = AsyncSocketModeHandler(app, SLACK_APP_TOKEN)
    logger.info("starting Slack socket-mode handler")
    try:
        await handler.start_async()
    finally:
        heartbeat_task.cancel()


def main() -> None:
    """Run the Slack client until the process is stopped."""
    asyncio.run(_run())


if __name__ == "__main__":
    main()
