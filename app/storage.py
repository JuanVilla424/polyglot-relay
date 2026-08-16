import json

from app.config import DATA_DIR, USER_LANGUAGES_PATH


def _key(guild_id: int, user_id: int) -> str:
    return f"{guild_id}:{user_id}"


def get_user_language(guild_id: int, user_id: int) -> str | None:
    """Return the language code the user set for this guild, if any."""
    return _read().get(_key(guild_id, user_id))


def set_user_language(guild_id: int, user_id: int, language_code: str) -> None:
    """Persist the user's preferred language for this guild."""
    data = _read()
    data[_key(guild_id, user_id)] = language_code
    _write(data)


def guild_user_languages(guild_id: int) -> dict[int, str]:
    """Return {user_id: language_code} for every user opted in on this guild."""
    prefix = f"{guild_id}:"
    return {
        int(key[len(prefix) :]): lang for key, lang in _read().items() if key.startswith(prefix)
    }


def _read() -> dict[str, str]:
    if not USER_LANGUAGES_PATH.exists():
        return {}
    with open(USER_LANGUAGES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _write(data: dict[str, str]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(USER_LANGUAGES_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
