from app import storage


def _use_tmp_store(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    monkeypatch.setattr(storage, "USER_LANGUAGES_PATH", tmp_path / "user_languages.json")


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
