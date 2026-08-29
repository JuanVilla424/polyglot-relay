import os

os.environ.setdefault("DISCORD_BOT_TOKEN", "test-token")
os.environ.setdefault("SLACK_BOT_TOKEN", "xoxb-test-token")
os.environ.setdefault("SLACK_APP_TOKEN", "xapp-test-token")
os.environ.setdefault("LIBRETRANSLATE_URL", "http://libretranslate:5000")
# Force-unset (not setdefault): a real .env with a live channel ID would
# otherwise make the log-channel reporting in either adapter attempt real
# API calls (Discord and Slack both read LOG_CHANNEL_ID).
os.environ["LOG_CHANNEL_ID"] = ""
