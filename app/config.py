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

_announcements_channel_id = os.getenv("ANNOUNCEMENTS_CHANNEL_ID")
ANNOUNCEMENTS_CHANNEL_ID = int(_announcements_channel_id) if _announcements_channel_id else None

_verify_channel_id = os.getenv("VERIFY_CHANNEL_ID")
VERIFY_CHANNEL_ID = int(_verify_channel_id) if _verify_channel_id else None

_verified_role_id = os.getenv("VERIFIED_ROLE_ID")
VERIFIED_ROLE_ID = int(_verified_role_id) if _verified_role_id else None

_member_role_id = os.getenv("MEMBER_ROLE_ID")
MEMBER_ROLE_ID = int(_member_role_id) if _member_role_id else None

_guest_role_id = os.getenv("GUEST_ROLE_ID")
GUEST_ROLE_ID = int(_guest_role_id) if _guest_role_id else None

_verify_approver_role_ids = os.getenv("VERIFY_APPROVER_ROLE_IDS", "")
VERIFY_APPROVER_ROLE_IDS = [
    int(role_id.strip()) for role_id in _verify_approver_role_ids.split(",") if role_id.strip()
]

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
USER_LANGUAGES_PATH = DATA_DIR / "user_languages.json"
ROLE_LANGUAGES_PATH = DATA_DIR / "role_languages.json"
SERVER_LANGUAGE_PATH = DATA_DIR / "server_language.json"
DELIVERY_MODE_PATH = DATA_DIR / "delivery_mode.json"
EXCLUDED_CHANNELS_PATH = DATA_DIR / "excluded_channels.json"
DELIVERED_LANGUAGES_PATH = DATA_DIR / "delivered_languages.json"
ENABLED_MODULES_PATH = DATA_DIR / "enabled_modules.json"
LAST_ANNOUNCED_SHA_PATH = DATA_DIR / "last_announced_sha.json"
EVENTS_PATH = DATA_DIR / "events.json"
ACTIVITY_PATH = DATA_DIR / "activity.json"
ACTIVITY_DIGEST_PATH = DATA_DIR / "activity_digest.json"
