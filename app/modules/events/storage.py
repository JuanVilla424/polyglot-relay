from app import storage
from app.config import CANCELLED_EVENTS_PATH, EVENTS_PATH, GAME_EVENT_ANNOUNCEMENTS_PATH


def get_event(message_id: int) -> dict | None:
    """Return the stored event for this message, if any."""
    return storage.read_json(EVENTS_PATH).get(str(message_id))


def save_event(message_id: int, event: dict) -> None:
    """Create or overwrite the event tracked under this message."""
    data = storage.read_json(EVENTS_PATH)
    data[str(message_id)] = event
    storage.write_json(EVENTS_PATH, data)


def delete_event(message_id: int) -> None:
    """Remove the event tracked under this message, if any."""
    storage.clear_key(EVENTS_PATH, str(message_id))


def all_events() -> dict[str, dict]:
    """Every tracked event across every guild, keyed by message id (as a string)."""
    return storage.read_json(EVENTS_PATH)


def get_announcement(message_id: int) -> dict | None:
    """Return the stored game-event announcement for this message, if any."""
    return storage.read_json(GAME_EVENT_ANNOUNCEMENTS_PATH).get(str(message_id))


def save_announcement(message_id: int, announcement: dict) -> None:
    """Create or overwrite the announcement tracked under this message."""
    data = storage.read_json(GAME_EVENT_ANNOUNCEMENTS_PATH)
    data[str(message_id)] = announcement
    storage.write_json(GAME_EVENT_ANNOUNCEMENTS_PATH, data)


def all_announcements() -> dict[str, dict]:
    """Every tracked game-event announcement across every guild, keyed by message id."""
    return storage.read_json(GAME_EVENT_ANNOUNCEMENTS_PATH)


def record_cancellation(guild_id: int, title: str, cancelled_at: int, max_age_seconds: int) -> None:
    """Remember a cancelled event's title so a prompt re-creation announces as a
    reschedule instead of a brand-new event. Records older than max_age_seconds
    are pruned on every write so the store never accumulates stale titles."""
    data = storage.read_json(CANCELLED_EVENTS_PATH)
    data.setdefault(str(guild_id), {})[title.strip().casefold()] = cancelled_at
    for guild_key in list(data):
        data[guild_key] = {
            record_title: recorded_at
            for record_title, recorded_at in data[guild_key].items()
            if cancelled_at - recorded_at <= max_age_seconds
        }
        if not data[guild_key]:
            del data[guild_key]
    storage.write_json(CANCELLED_EVENTS_PATH, data)


def pop_recent_cancellation(guild_id: int, title: str, now: int, max_age_seconds: int) -> bool:
    """True if this guild cancelled an event with this title (case/whitespace
    insensitive) within the window. The record is consumed on match, so only the
    FIRST re-creation of the title announces as rescheduled."""
    data = storage.read_json(CANCELLED_EVENTS_PATH)
    normalized = title.strip().casefold()
    recorded_at = data.get(str(guild_id), {}).get(normalized)
    if recorded_at is None or now - recorded_at > max_age_seconds:
        return False
    del data[str(guild_id)][normalized]
    if not data[str(guild_id)]:
        del data[str(guild_id)]
    storage.write_json(CANCELLED_EVENTS_PATH, data)
    return True
