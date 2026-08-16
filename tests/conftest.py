import os

os.environ.setdefault("DISCORD_BOT_TOKEN", "test-token")
os.environ.setdefault("LIBRETRANSLATE_URL", "http://libretranslate:5000")
# Force-unset (not setdefault): a real .env with a live channel ID would
# otherwise make _report_language_change attempt real Discord API calls.
os.environ["LOG_CHANNEL_ID"] = ""
