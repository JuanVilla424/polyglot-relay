import os
import sys
from pathlib import Path

from dotenv import load_dotenv

env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(env_path)

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not DISCORD_BOT_TOKEN:
    print("ERROR: DISCORD_BOT_TOKEN not set (define it in .env or the environment)")
    sys.exit(1)

LIBRETRANSLATE_URL = os.getenv("LIBRETRANSLATE_URL", "http://libretranslate:5000")
NLLB_URL = os.getenv("NLLB_URL", "http://nllb:8000")

_log_channel_id = os.getenv("LOG_CHANNEL_ID")
LOG_CHANNEL_ID = int(_log_channel_id) if _log_channel_id else None

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
USER_LANGUAGES_PATH = DATA_DIR / "user_languages.json"
ROLE_LANGUAGES_PATH = DATA_DIR / "role_languages.json"
