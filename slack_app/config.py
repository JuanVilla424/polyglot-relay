import os
import sys
from pathlib import Path

from dotenv import load_dotenv

env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(env_path)

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
if not SLACK_BOT_TOKEN:
    print("ERROR: SLACK_BOT_TOKEN not set (define it in .env or the environment)")
    sys.exit(1)

SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")
if not SLACK_APP_TOKEN:
    print("ERROR: SLACK_APP_TOKEN not set (define it in .env or the environment)")
    sys.exit(1)

# Optional: Slack channel ID where language-command activity gets reported.
# Slack channel IDs are strings ("C0123..."), unlike Discord's numeric IDs.
LOG_CHANNEL_ID = os.getenv("LOG_CHANNEL_ID") or None

# Fallback target language for on-demand translation when the requester never
# set their own with /polyglot-lang.
DEFAULT_TARGET_LANGUAGE = (os.getenv("DEFAULT_TARGET_LANGUAGE") or "en").lower()

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
USER_LANGUAGES_PATH = DATA_DIR / "user_languages.json"
