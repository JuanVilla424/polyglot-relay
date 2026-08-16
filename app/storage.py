import json
from pathlib import Path

from app.config import (
    DATA_DIR,
    DELIVERY_MODE_PATH,
    ROLE_LANGUAGES_PATH,
    SERVER_LANGUAGE_PATH,
    USER_LANGUAGES_PATH,
)


def _key(guild_id: int, entity_id: int) -> str:
    return f"{guild_id}:{entity_id}"


def get_user_language(guild_id: int, user_id: int) -> str | None:
    """Return the language code the user set for this guild, if any."""
    return _read(USER_LANGUAGES_PATH).get(_key(guild_id, user_id))


def set_user_language(guild_id: int, user_id: int, language_code: str) -> None:
    """Persist the user's preferred language for this guild."""
    data = _read(USER_LANGUAGES_PATH)
    data[_key(guild_id, user_id)] = language_code
    _write(USER_LANGUAGES_PATH, data)


def clear_user_language(guild_id: int, user_id: int) -> None:
    """Remove the user's language for this guild, if any was set."""
    _clear(USER_LANGUAGES_PATH, _key(guild_id, user_id))


def guild_user_languages(guild_id: int) -> dict[int, str]:
    """Return {user_id: language_code} for every user opted in on this guild."""
    return _guild_entries(USER_LANGUAGES_PATH, guild_id)


def get_role_language(guild_id: int, role_id: int) -> str | None:
    """Return the language code assigned to this role, if any."""
    return _read(ROLE_LANGUAGES_PATH).get(_key(guild_id, role_id))


def set_role_language(guild_id: int, role_id: int, language_code: str) -> None:
    """Persist the language assigned to a role for this guild."""
    data = _read(ROLE_LANGUAGES_PATH)
    data[_key(guild_id, role_id)] = language_code
    _write(ROLE_LANGUAGES_PATH, data)


def clear_role_language(guild_id: int, role_id: int) -> None:
    """Remove the role's language mapping for this guild, if any was set."""
    _clear(ROLE_LANGUAGES_PATH, _key(guild_id, role_id))


def guild_role_languages(guild_id: int) -> dict[int, str]:
    """Return {role_id: language_code} for every role mapped on this guild."""
    return _guild_entries(ROLE_LANGUAGES_PATH, guild_id)


def get_server_language(guild_id: int) -> str | None:
    """Return the guild's configured fallback language, if an admin set one."""
    return _read(SERVER_LANGUAGE_PATH).get(str(guild_id))


def set_server_language(guild_id: int, language_code: str) -> None:
    """Persist the guild's fallback language, overriding the built-in default."""
    data = _read(SERVER_LANGUAGE_PATH)
    data[str(guild_id)] = language_code
    _write(SERVER_LANGUAGE_PATH, data)


def clear_server_language(guild_id: int) -> None:
    """Remove the guild's fallback language override, if any was set."""
    _clear(SERVER_LANGUAGE_PATH, str(guild_id))


def get_delivery_mode(guild_id: int) -> str | None:
    """Return the guild's configured translation delivery mode, if an admin set one."""
    return _read(DELIVERY_MODE_PATH).get(str(guild_id))


def set_delivery_mode(guild_id: int, mode: str) -> None:
    """Persist the guild's translation delivery mode, overriding the built-in default."""
    data = _read(DELIVERY_MODE_PATH)
    data[str(guild_id)] = mode
    _write(DELIVERY_MODE_PATH, data)


def clear_delivery_mode(guild_id: int) -> None:
    """Remove the guild's delivery mode override, if any was set."""
    _clear(DELIVERY_MODE_PATH, str(guild_id))


def _clear(path: Path, key: str) -> None:
    data = _read(path)
    if key in data:
        del data[key]
        _write(path, data)


def _guild_entries(path: Path, guild_id: int) -> dict[int, str]:
    prefix = f"{guild_id}:"
    return {
        int(key[len(prefix) :]): lang for key, lang in _read(path).items() if key.startswith(prefix)
    }


def _read(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write(path: Path, data: dict[str, str]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
