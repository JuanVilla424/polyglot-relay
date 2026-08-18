from pathlib import Path

from app import version_notice


def _write(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def test_get_current_version_reads_pyproject_toml(tmp_path, monkeypatch):
    """The version comes straight from [tool.poetry].version."""
    pyproject = _write(
        tmp_path / "pyproject.toml", '[tool.poetry]\nname = "x"\nversion = "1.2.3"\n'
    )
    monkeypatch.setattr(version_notice, "PYPROJECT_PATH", pyproject)

    assert version_notice.get_current_version() == "1.2.3"


def test_get_current_version_missing_file_returns_none(tmp_path, monkeypatch):
    """No pyproject.toml at the expected path -> None, not a crash."""
    monkeypatch.setattr(version_notice, "PYPROJECT_PATH", tmp_path / "missing.toml")

    assert version_notice.get_current_version() is None


def test_get_current_version_malformed_file_returns_none(tmp_path, monkeypatch):
    """A pyproject.toml that fails to parse, or is missing the expected keys, doesn't raise."""
    pyproject = _write(tmp_path / "pyproject.toml", "not valid toml [[[\n")
    monkeypatch.setattr(version_notice, "PYPROJECT_PATH", pyproject)

    assert version_notice.get_current_version() is None


def test_get_latest_changelog_entry_returns_only_the_top_block(tmp_path, monkeypatch):
    """Only the newest version's block is returned, not the whole file."""
    changelog = _write(
        tmp_path / "CHANGELOG.md",
        "## [1.0.5] - 2026-08-16\n\n### Bug Fixes\n\n- fix a\n\n"
        "## [1.0.4] - 2026-08-15\n\n### Features\n\n- feat b\n",
    )
    monkeypatch.setattr(version_notice, "CHANGELOG_PATH", changelog)

    entry = version_notice.get_latest_changelog_entry()

    assert entry.startswith("## [1.0.5]")
    assert "fix a" in entry
    assert "1.0.4" not in entry


def test_get_latest_changelog_entry_missing_file_returns_none(tmp_path, monkeypatch):
    """No CHANGELOG.md at the expected path -> None, not a crash."""
    monkeypatch.setattr(version_notice, "CHANGELOG_PATH", tmp_path / "missing.md")

    assert version_notice.get_latest_changelog_entry() is None


def test_get_latest_changelog_entry_no_header_returns_none(tmp_path, monkeypatch):
    """A file with no '## [' header at all -> None."""
    changelog = _write(tmp_path / "CHANGELOG.md", "just some text\n")
    monkeypatch.setattr(version_notice, "CHANGELOG_PATH", changelog)

    assert version_notice.get_latest_changelog_entry() is None


def test_build_deploy_announcement_fits_in_one_message_when_short():
    """A short changelog entry stays a single message."""
    messages = version_notice.build_deploy_announcement("1.0.5", "### Bug Fixes\n\n- fix a")

    assert len(messages) == 1
    assert messages[0].startswith("🚀 Deployed **v1.0.5**")
    assert "fix a" in messages[0]


def test_build_deploy_announcement_without_changelog_entry_uses_fallback():
    """No changelog entry found -> still announces the version, with a fallback note."""
    messages = version_notice.build_deploy_announcement("1.0.5", None)

    assert len(messages) == 1
    assert "1.0.5" in messages[0]


def test_build_deploy_announcement_splits_long_changelog_without_losing_any_of_it():
    """A changelog entry over Discord's 2000-char message limit is chunked, not truncated."""
    lines = [f"- change number {i}" for i in range(300)]
    long_entry = "\n".join(lines)

    messages = version_notice.build_deploy_announcement("1.0.5", long_entry)

    assert len(messages) > 1
    for message in messages:
        assert len(message) <= 2000
    all_text = "\n".join(messages)
    for line in lines:
        assert line in all_text
