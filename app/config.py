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

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
USER_LANGUAGES_PATH = DATA_DIR / "user_languages.json"
