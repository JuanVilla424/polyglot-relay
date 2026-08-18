from app import storage


def _use_tmp_store(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    monkeypatch.setattr(storage, "ENABLED_MODULES_PATH", tmp_path / "enabled_modules.json")
    monkeypatch.setattr(
        storage, "LAST_ANNOUNCED_VERSION_PATH", tmp_path / "last_announced_version.json"
    )


def test_read_json_missing_file_returns_empty_dict(tmp_path):
    """No store file on disk yet -> reads return {} instead of raising."""
    assert storage.read_json(tmp_path / "missing.json") == {}


def test_write_json_then_read_json_round_trips(tmp_path):
    """A written store reads back exactly what was written."""
    path = tmp_path / "store.json"

    storage.write_json(path, {"a": 1, "b": "two"})

    assert storage.read_json(path) == {"a": 1, "b": "two"}


def test_clear_key_removes_only_that_key(tmp_path):
    """Clearing one key leaves the rest of the store untouched."""
    path = tmp_path / "store.json"
    storage.write_json(path, {"keep": 1, "drop": 2})

    storage.clear_key(path, "drop")

    assert storage.read_json(path) == {"keep": 1}


def test_clear_key_is_a_noop_when_absent(tmp_path):
    """Clearing a key that was never set doesn't raise."""
    path = tmp_path / "store.json"

    storage.clear_key(path, "missing")  # must not raise

    assert storage.read_json(path) == {}


def test_guild_scoped_entries_isolates_by_guild(tmp_path):
    """Only entries whose key is prefixed with this guild's id are returned."""
    path = tmp_path / "store.json"
    storage.write_json(
        path,
        {
            storage.make_key(1, 100): "es",
            storage.make_key(1, 200): "en",
            storage.make_key(2, 300): "fr",
        },
    )

    assert storage.guild_scoped_entries(path, 1) == {100: "es", 200: "en"}
    assert storage.guild_scoped_entries(path, 2) == {300: "fr"}


def test_is_module_enabled_defaults_translation_on_and_others_off(tmp_path, monkeypatch):
    """No explicit config anywhere -> translation is on, everything else is off."""
    _use_tmp_store(tmp_path, monkeypatch)

    assert storage.is_module_enabled(1, "translation") is True
    assert storage.is_module_enabled(1, "events") is False


def test_set_module_enabled_overrides_the_default(tmp_path, monkeypatch):
    """An explicit override wins over the built-in default, in both directions."""
    _use_tmp_store(tmp_path, monkeypatch)

    storage.set_module_enabled(1, "events", True)
    storage.set_module_enabled(1, "translation", False)

    assert storage.is_module_enabled(1, "events") is True
    assert storage.is_module_enabled(1, "translation") is False


def test_module_enabled_state_isolates_by_guild(tmp_path, monkeypatch):
    """Enabling a module in one guild doesn't affect another guild's default."""
    _use_tmp_store(tmp_path, monkeypatch)

    storage.set_module_enabled(1, "events", True)

    assert storage.is_module_enabled(1, "events") is True
    assert storage.is_module_enabled(2, "events") is False


def test_get_last_announced_version_missing_returns_none(tmp_path, monkeypatch):
    """No version ever announced yet -> None, not a crash."""
    _use_tmp_store(tmp_path, monkeypatch)

    assert storage.get_last_announced_version() is None


def test_set_and_get_last_announced_version_round_trips(tmp_path, monkeypatch):
    """A stored version persists and reads back exactly."""
    _use_tmp_store(tmp_path, monkeypatch)

    storage.set_last_announced_version("1.0.5")

    assert storage.get_last_announced_version() == "1.0.5"


def test_set_last_announced_version_overwrites_the_previous_value(tmp_path, monkeypatch):
    """A new version bump replaces the old baseline, not appends to it."""
    _use_tmp_store(tmp_path, monkeypatch)
    storage.set_last_announced_version("1.0.4")

    storage.set_last_announced_version("1.0.5")

    assert storage.get_last_announced_version() == "1.0.5"
