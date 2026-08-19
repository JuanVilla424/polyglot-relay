from app import storage
from app.config import EVENTS_PATH, GAME_EVENT_ANNOUNCEMENTS_PATH


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
