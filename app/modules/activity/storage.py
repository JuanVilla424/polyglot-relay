from app import storage
from app.config import ACTIVITY_DIGEST_PATH, ACTIVITY_PATH


def record_activity(guild_id: int, user_id: int, timestamp: int) -> None:
    """Create or overwrite this member's last-active timestamp in this guild."""
    data = storage.read_json(ACTIVITY_PATH)
    data[storage.make_key(guild_id, user_id)] = timestamp
    storage.write_json(ACTIVITY_PATH, data)


def get_last_active(guild_id: int) -> dict[int, int]:
    """Every {user_id: last_active_timestamp} tracked for this guild."""
    return storage.guild_scoped_entries(ACTIVITY_PATH, guild_id)


def get_last_digest_sent_at(guild_id: int) -> int | None:
    """When the weekly activity digest was last posted for this guild, if ever."""
    return storage.read_json(ACTIVITY_DIGEST_PATH).get(str(guild_id))


def set_last_digest_sent_at(guild_id: int, timestamp: int) -> None:
    """Record that the weekly digest was just (or is being seeded as) sent for this guild."""
    data = storage.read_json(ACTIVITY_DIGEST_PATH)
    data[str(guild_id)] = timestamp
    storage.write_json(ACTIVITY_DIGEST_PATH, data)
