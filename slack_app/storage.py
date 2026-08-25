import json
from pathlib import Path

from slack_app import config


def make_key(team_id: str, user_id: str) -> str:
    """Build the workspace-scoped storage key ("T123...:U456...")."""
    return f"{team_id}:{user_id}"


def read_json(path: Path) -> dict:
    """Load a JSON store, returning an empty dict if it hasn't been created yet."""
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: dict) -> None:
    """Persist a JSON store, creating the data directory if needed."""
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_user_language(team_id: str, user_id: str) -> str | None:
    """Return the language code this user set in this workspace, if any."""
    return read_json(config.USER_LANGUAGES_PATH).get(make_key(team_id, user_id))


def set_user_language(team_id: str, user_id: str, language_code: str) -> None:
    """Persist the user's preferred language for this workspace."""
    data = read_json(config.USER_LANGUAGES_PATH)
    data[make_key(team_id, user_id)] = language_code
    write_json(config.USER_LANGUAGES_PATH, data)


def clear_user_language(team_id: str, user_id: str) -> None:
    """Remove the user's language for this workspace, if any was set."""
    data = read_json(config.USER_LANGUAGES_PATH)
    key = make_key(team_id, user_id)
    if key in data:
        del data[key]
        write_json(config.USER_LANGUAGES_PATH, data)
