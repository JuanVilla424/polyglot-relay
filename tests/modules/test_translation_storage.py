from app import storage as core_storage
from app.modules.translation import storage


def _use_tmp_store(tmp_path, monkeypatch):
    monkeypatch.setattr(core_storage, "DATA_DIR", tmp_path)
    monkeypatch.setattr(storage, "USER_LANGUAGES_PATH", tmp_path / "user_languages.json")
    monkeypatch.setattr(storage, "ROLE_LANGUAGES_PATH", tmp_path / "role_languages.json")
    monkeypatch.setattr(storage, "SERVER_LANGUAGE_PATH", tmp_path / "server_language.json")
    monkeypatch.setattr(storage, "DELIVERY_MODE_PATH", tmp_path / "delivery_mode.json")


def test_get_user_language_missing_file_returns_none(tmp_path, monkeypatch):
    """No store file on disk yet -> lookups return None instead of raising."""
    _use_tmp_store(tmp_path, monkeypatch)

    assert storage.get_user_language(1, 1) is None


def test_set_and_get_user_language(tmp_path, monkeypatch):
    """A stored preference round-trips and stays scoped to its guild/user."""
    _use_tmp_store(tmp_path, monkeypatch)

    storage.set_user_language(1, 100, "es")

    assert storage.get_user_language(1, 100) == "es"
    assert storage.get_user_language(1, 999) is None
    assert storage.get_user_language(2, 100) is None


def test_guild_user_languages_isolates_by_guild(tmp_path, monkeypatch):
    """Two guilds sharing the same store never see each other's users."""
    _use_tmp_store(tmp_path, monkeypatch)

    storage.set_user_language(1, 100, "es")
    storage.set_user_language(1, 200, "en")
    storage.set_user_language(2, 300, "fr")

    assert storage.guild_user_languages(1) == {100: "es", 200: "en"}
    assert storage.guild_user_languages(2) == {300: "fr"}


def test_role_languages_round_trip_and_isolate_by_guild(tmp_path, monkeypatch):
    """Role mappings persist independently of user mappings and stay per-guild."""
    _use_tmp_store(tmp_path, monkeypatch)

    storage.set_role_language(1, 10, "es")
    storage.set_role_language(1, 20, "en")
    storage.set_role_language(2, 30, "fr")

    assert storage.get_role_language(1, 10) == "es"
    assert storage.get_role_language(1, 999) is None
    assert storage.guild_role_languages(1) == {10: "es", 20: "en"}
    assert storage.guild_role_languages(2) == {30: "fr"}
    # User and role stores don't collide even with overlapping guild/id numbers.
    assert storage.guild_user_languages(1) == {}


def test_clear_user_language_removes_only_that_entry(tmp_path, monkeypatch):
    """Clearing one user's language leaves everyone else untouched."""
    _use_tmp_store(tmp_path, monkeypatch)
    storage.set_user_language(1, 100, "es")
    storage.set_user_language(1, 200, "en")

    storage.clear_user_language(1, 100)

    assert storage.get_user_language(1, 100) is None
    assert storage.get_user_language(1, 200) == "en"


def test_clear_user_language_is_a_noop_when_unset(tmp_path, monkeypatch):
    """Clearing a language that was never set doesn't raise."""
    _use_tmp_store(tmp_path, monkeypatch)

    storage.clear_user_language(1, 100)  # must not raise

    assert storage.get_user_language(1, 100) is None


def test_clear_role_language_removes_only_that_entry(tmp_path, monkeypatch):
    """Clearing one role's language leaves other roles untouched."""
    _use_tmp_store(tmp_path, monkeypatch)
    storage.set_role_language(1, 10, "es")
    storage.set_role_language(1, 20, "en")

    storage.clear_role_language(1, 10)

    assert storage.get_role_language(1, 10) is None
    assert storage.get_role_language(1, 20) == "en"


def test_get_server_language_missing_returns_none(tmp_path, monkeypatch):
    """No override stored yet -> lookup returns None instead of raising."""
    _use_tmp_store(tmp_path, monkeypatch)

    assert storage.get_server_language(1) is None


def test_server_language_round_trip_and_isolates_by_guild(tmp_path, monkeypatch):
    """A stored server-language override persists and stays scoped to its guild."""
    _use_tmp_store(tmp_path, monkeypatch)

    storage.set_server_language(1, "es")
    storage.set_server_language(2, "fr")

    assert storage.get_server_language(1) == "es"
    assert storage.get_server_language(2) == "fr"


def test_clear_server_language_removes_only_that_guild(tmp_path, monkeypatch):
    """Clearing one guild's override leaves other guilds untouched."""
    _use_tmp_store(tmp_path, monkeypatch)
    storage.set_server_language(1, "es")
    storage.set_server_language(2, "fr")

    storage.clear_server_language(1)

    assert storage.get_server_language(1) is None
    assert storage.get_server_language(2) == "fr"


def test_clear_server_language_is_a_noop_when_unset(tmp_path, monkeypatch):
    """Clearing a server language that was never set doesn't raise."""
    _use_tmp_store(tmp_path, monkeypatch)

    storage.clear_server_language(1)  # must not raise

    assert storage.get_server_language(1) is None


def test_get_delivery_mode_missing_returns_none(tmp_path, monkeypatch):
    """No override stored yet -> lookup returns None instead of raising."""
    _use_tmp_store(tmp_path, monkeypatch)

    assert storage.get_delivery_mode(1) is None


def test_delivery_mode_round_trip_and_isolates_by_guild(tmp_path, monkeypatch):
    """A stored delivery-mode override persists and stays scoped to its guild."""
    _use_tmp_store(tmp_path, monkeypatch)

    storage.set_delivery_mode(1, "thread")
    storage.set_delivery_mode(2, "reply")

    assert storage.get_delivery_mode(1) == "thread"
    assert storage.get_delivery_mode(2) == "reply"


def test_clear_delivery_mode_removes_only_that_guild(tmp_path, monkeypatch):
    """Clearing one guild's override leaves other guilds untouched."""
    _use_tmp_store(tmp_path, monkeypatch)
    storage.set_delivery_mode(1, "thread")
    storage.set_delivery_mode(2, "reply")

    storage.clear_delivery_mode(1)

    assert storage.get_delivery_mode(1) is None
    assert storage.get_delivery_mode(2) == "reply"


def test_clear_delivery_mode_is_a_noop_when_unset(tmp_path, monkeypatch):
    """Clearing a delivery mode that was never set doesn't raise."""
    _use_tmp_store(tmp_path, monkeypatch)

    storage.clear_delivery_mode(1)  # must not raise

    assert storage.get_delivery_mode(1) is None
