from app import storage
from app.config import (
    DELIVERY_MODE_PATH,
    EXCLUDED_CHANNELS_PATH,
    ROLE_LANGUAGES_PATH,
    SERVER_LANGUAGE_PATH,
    USER_LANGUAGES_PATH,
)


def get_user_language(guild_id: int, user_id: int) -> str | None:
    """Return the language code the user set for this guild, if any."""
    return storage.read_json(USER_LANGUAGES_PATH).get(storage.make_key(guild_id, user_id))


def set_user_language(guild_id: int, user_id: int, language_code: str) -> None:
    """Persist the user's preferred language for this guild."""
    data = storage.read_json(USER_LANGUAGES_PATH)
    data[storage.make_key(guild_id, user_id)] = language_code
    storage.write_json(USER_LANGUAGES_PATH, data)


def clear_user_language(guild_id: int, user_id: int) -> None:
    """Remove the user's language for this guild, if any was set."""
    storage.clear_key(USER_LANGUAGES_PATH, storage.make_key(guild_id, user_id))


def guild_user_languages(guild_id: int) -> dict[int, str]:
    """Return {user_id: language_code} for every user opted in on this guild."""
    return storage.guild_scoped_entries(USER_LANGUAGES_PATH, guild_id)


def get_role_language(guild_id: int, role_id: int) -> str | None:
    """Return the language code assigned to this role, if any."""
    return storage.read_json(ROLE_LANGUAGES_PATH).get(storage.make_key(guild_id, role_id))


def set_role_language(guild_id: int, role_id: int, language_code: str) -> None:
    """Persist the language assigned to a role for this guild."""
    data = storage.read_json(ROLE_LANGUAGES_PATH)
    data[storage.make_key(guild_id, role_id)] = language_code
    storage.write_json(ROLE_LANGUAGES_PATH, data)


def clear_role_language(guild_id: int, role_id: int) -> None:
    """Remove the role's language mapping for this guild, if any was set."""
    storage.clear_key(ROLE_LANGUAGES_PATH, storage.make_key(guild_id, role_id))


def guild_role_languages(guild_id: int) -> dict[int, str]:
    """Return {role_id: language_code} for every role mapped on this guild."""
    return storage.guild_scoped_entries(ROLE_LANGUAGES_PATH, guild_id)


def get_server_language(guild_id: int) -> str | None:
    """Return the guild's configured fallback language, if an admin set one."""
    return storage.read_json(SERVER_LANGUAGE_PATH).get(str(guild_id))


def set_server_language(guild_id: int, language_code: str) -> None:
    """Persist the guild's fallback language, overriding the built-in default."""
    data = storage.read_json(SERVER_LANGUAGE_PATH)
    data[str(guild_id)] = language_code
    storage.write_json(SERVER_LANGUAGE_PATH, data)


def clear_server_language(guild_id: int) -> None:
    """Remove the guild's fallback language override, if any was set."""
    storage.clear_key(SERVER_LANGUAGE_PATH, str(guild_id))


def get_delivery_mode(guild_id: int) -> str | None:
    """Return the guild's configured translation delivery mode, if an admin set one."""
    return storage.read_json(DELIVERY_MODE_PATH).get(str(guild_id))


def set_delivery_mode(guild_id: int, mode: str) -> None:
    """Persist the guild's translation delivery mode, overriding the built-in default."""
    data = storage.read_json(DELIVERY_MODE_PATH)
    data[str(guild_id)] = mode
    storage.write_json(DELIVERY_MODE_PATH, data)


def clear_delivery_mode(guild_id: int) -> None:
    """Remove the guild's delivery mode override, if any was set."""
    storage.clear_key(DELIVERY_MODE_PATH, str(guild_id))


def is_channel_excluded(guild_id: int, channel_id: int) -> bool:
    """Whether this channel is opted out of translation (e.g. a role-picker channel)."""
    return storage.read_json(EXCLUDED_CHANNELS_PATH).get(
        storage.make_key(guild_id, channel_id), False
    )


def set_channel_excluded(guild_id: int, channel_id: int, excluded: bool) -> None:
    """Persist whether this channel is opted out of translation; False clears the entry."""
    key = storage.make_key(guild_id, channel_id)
    if excluded:
        data = storage.read_json(EXCLUDED_CHANNELS_PATH)
        data[key] = True
        storage.write_json(EXCLUDED_CHANNELS_PATH, data)
    else:
        storage.clear_key(EXCLUDED_CHANNELS_PATH, key)
