import pytest

from slack_app import message_cache


@pytest.fixture(autouse=True)
def _fresh_cache():
    """The cache is module-level state; every test starts and ends empty."""
    message_cache.clear()
    yield
    message_cache.clear()


def test_remember_then_recall_returns_the_text():
    """A cached message comes back by (channel, ts)."""
    message_cache.remember("C1", "1.0", "hello")
    assert message_cache.recall("C1", "1.0") == "hello"


def test_recall_unknown_message_returns_none():
    """A miss is None -- the caller decides whether to fall back to the API."""
    assert message_cache.recall("C1", "404.0") is None


def test_eviction_drops_the_oldest_entry_past_the_cap(monkeypatch):
    """The cache stays bounded: inserting past the cap evicts the oldest."""
    monkeypatch.setattr(message_cache, "_MAX_MESSAGES", 2)
    message_cache.remember("C1", "1.0", "first")
    message_cache.remember("C1", "2.0", "second")
    message_cache.remember("C1", "3.0", "third")
    assert message_cache.recall("C1", "1.0") is None
    assert message_cache.recall("C1", "2.0") == "second"
    assert message_cache.recall("C1", "3.0") == "third"


def test_remember_same_key_updates_text_and_refreshes_recency(monkeypatch):
    """Re-remembering a message updates it and moves it to the fresh end."""
    monkeypatch.setattr(message_cache, "_MAX_MESSAGES", 2)
    message_cache.remember("C1", "1.0", "old")
    message_cache.remember("C1", "2.0", "second")
    message_cache.remember("C1", "1.0", "new")
    message_cache.remember("C1", "3.0", "third")
    assert message_cache.recall("C1", "1.0") == "new"
    assert message_cache.recall("C1", "2.0") is None
