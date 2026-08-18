import json
from pathlib import Path

from app.config import DATA_DIR, ENABLED_MODULES_PATH, LAST_ANNOUNCED_SHA_PATH

# Modules a guild gets without ever running /polyglot-modules. New modules
# (e.g. events) start opted-out until an admin explicitly enables them --
# this keeps a fresh module rollout from silently changing behavior on
# servers that never asked for it.
DEFAULT_ENABLED_MODULES = {"translation"}


def make_key(guild_id: int, entity_id: int) -> str:
    """Build the guild-scoped storage key shared by every per-entity JSON store."""
    return f"{guild_id}:{entity_id}"


def read_json(path: Path) -> dict:
    """Load a JSON store, returning an empty dict if it hasn't been created yet."""
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: dict) -> None:
    """Persist a JSON store, creating the data directory if needed."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def clear_key(path: Path, key: str) -> None:
    """Remove one key from a JSON store, if present; a no-op otherwise."""
    data = read_json(path)
    if key in data:
        del data[key]
        write_json(path, data)


def guild_scoped_entries(path: Path, guild_id: int) -> dict[int, str]:
    """Return {entity_id: value} for every entry under this guild in a store."""
    prefix = f"{guild_id}:"
    return {
        int(key[len(prefix) :]): value
        for key, value in read_json(path).items()
        if key.startswith(prefix)
    }


def is_module_enabled(guild_id: int, module_name: str) -> bool:
    """Whether a module is active for this guild: explicit setting, else the built-in default."""
    key = f"{guild_id}:{module_name}"
    overrides = read_json(ENABLED_MODULES_PATH)
    if key in overrides:
        return overrides[key]
    return module_name in DEFAULT_ENABLED_MODULES


def set_module_enabled(guild_id: int, module_name: str, enabled: bool) -> None:
    """Persist an explicit enable/disable override for a module in this guild."""
    data = read_json(ENABLED_MODULES_PATH)
    data[f"{guild_id}:{module_name}"] = enabled
    write_json(ENABLED_MODULES_PATH, data)


def get_last_announced_sha() -> str | None:
    """Return the git SHA this bot last posted a deploy announcement for, if any."""
    return read_json(LAST_ANNOUNCED_SHA_PATH).get("sha")


def set_last_announced_sha(sha: str) -> None:
    """Persist the SHA just announced, so a plain restart doesn't re-post it."""
    write_json(LAST_ANNOUNCED_SHA_PATH, {"sha": sha})
