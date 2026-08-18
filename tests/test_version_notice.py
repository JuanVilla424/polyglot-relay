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


def test_get_deploy_sha_reads_the_generated_file(tmp_path, monkeypatch):
    """deploy.sh writes the full git SHA to deploy_sha.txt before the build."""
    sha_file = _write(tmp_path / "deploy_sha.txt", "abc123def456\n")
    monkeypatch.setattr(version_notice, "DEPLOY_SHA_PATH", sha_file)

    assert version_notice.get_deploy_sha() == "abc123def456"


def test_get_deploy_sha_missing_file_returns_none(tmp_path, monkeypatch):
    """A build done without deploy.sh (no deploy_sha.txt) -> None, not a crash."""
    monkeypatch.setattr(version_notice, "DEPLOY_SHA_PATH", tmp_path / "missing.txt")

    assert version_notice.get_deploy_sha() is None


def test_get_deploy_commit_log_reads_lines(tmp_path, monkeypatch):
    """Each line is '<sha> <subject>', newest first, exactly as deploy.sh writes it."""
    log_file = _write(tmp_path / "deploy_commit_log.txt", "sha2 second\nsha1 first\n")
    monkeypatch.setattr(version_notice, "DEPLOY_COMMIT_LOG_PATH", log_file)

    assert version_notice.get_deploy_commit_log() == ["sha2 second", "sha1 first"]


def test_get_deploy_commit_log_missing_file_returns_empty_list(tmp_path, monkeypatch):
    """A build done without deploy.sh (no deploy_commit_log.txt) -> [], not a crash."""
    monkeypatch.setattr(version_notice, "DEPLOY_COMMIT_LOG_PATH", tmp_path / "missing.txt")

    assert version_notice.get_deploy_commit_log() == []


def test_commits_since_returns_everything_above_the_last_announced_sha():
    """Only the commits newer than the last announced deploy are returned."""
    log = ["sha3 third", "sha2 second", "sha1 first"]

    assert version_notice.commits_since("sha2", log) == ["sha3 third"]


def test_commits_since_returns_the_whole_log_when_last_sha_is_none():
    """No prior deploy on record (first run) -> the whole available log."""
    log = ["sha2 second", "sha1 first"]

    assert version_notice.commits_since(None, log) == log


def test_commits_since_falls_back_to_the_whole_log_when_last_sha_is_too_old():
    """The last deploy's SHA fell outside the log's window -- best available approximation."""
    log = ["sha3 third", "sha2 second"]

    assert version_notice.commits_since("some-ancient-sha", log) == log


def test_build_deploy_announcement_fits_in_one_message_when_short():
    """A short commit list stays a single message."""
    messages = version_notice.build_deploy_announcement(
        "abc1234def", "1.0.5", ["abc1234def fix a bug"]
    )

    assert len(messages) == 1
    assert messages[0].startswith("🚀 Deployed `abc1234`")
    assert "v1.0.5" in messages[0]
    assert "fix a bug" in messages[0]


def test_build_deploy_announcement_without_pyproject_version_omits_it():
    """pyproject.toml unreadable -> the header still works, just without the (vX.Y.Z) part."""
    messages = version_notice.build_deploy_announcement("abc1234def", None, ["abc1234def fix"])

    assert "v" not in messages[0].split("\n")[0]


def test_build_deploy_announcement_uses_fallback_when_no_new_commits():
    """Same code deployed again (empty commit list) -> still announces, with a clear note."""
    messages = version_notice.build_deploy_announcement("abc1234def", "1.0.5", [])

    assert len(messages) == 1
    assert "no new commits" in messages[0]


def test_build_deploy_announcement_splits_long_commit_lists_without_losing_any_of_it():
    """A commit list over Discord's 2000-char message limit is chunked, not truncated."""
    commits = [f"sha{i} change number {i}" for i in range(300)]

    messages = version_notice.build_deploy_announcement("abc1234def", "1.0.5", commits)

    assert len(messages) > 1
    for message in messages:
        assert len(message) <= 2000
    all_text = "\n".join(messages)
    for commit in commits:
        assert commit in all_text
