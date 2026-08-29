from slack_app import config, storage


def _isolate(monkeypatch, tmp_path):
    """Point the store at a throwaway directory so tests never touch data/."""
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "USER_LANGUAGES_PATH", tmp_path / "user_languages.json")


def test_set_then_get_user_language_round_trips(monkeypatch, tmp_path):
    """A stored preference comes back exactly as saved."""
    _isolate(monkeypatch, tmp_path)
    storage.set_user_language("T1", "U1", "es")
    assert storage.get_user_language("T1", "U1") == "es"


def test_get_user_language_returns_none_when_unset(monkeypatch, tmp_path):
    """No preference on record means None, not an error or a default."""
    _isolate(monkeypatch, tmp_path)
    assert storage.get_user_language("T1", "U404") is None


def test_clear_user_language_removes_only_that_user(monkeypatch, tmp_path):
    """Clearing one user leaves everyone else's preference intact."""
    _isolate(monkeypatch, tmp_path)
    storage.set_user_language("T1", "U1", "es")
    storage.set_user_language("T1", "U2", "fr")
    storage.clear_user_language("T1", "U1")
    assert storage.get_user_language("T1", "U1") is None
    assert storage.get_user_language("T1", "U2") == "fr"


def test_clear_user_language_is_a_noop_when_unset(monkeypatch, tmp_path):
    """Clearing a preference that was never set neither fails nor creates the store."""
    _isolate(monkeypatch, tmp_path)
    storage.clear_user_language("T1", "U1")
    assert storage.get_user_language("T1", "U1") is None


def test_keys_are_scoped_per_workspace(monkeypatch, tmp_path):
    """The same Slack user ID in two workspaces keeps two separate preferences."""
    _isolate(monkeypatch, tmp_path)
    storage.set_user_language("T1", "U1", "es")
    storage.set_user_language("T2", "U1", "de")
    assert storage.get_user_language("T1", "U1") == "es"
    assert storage.get_user_language("T2", "U1") == "de"
