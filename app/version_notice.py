import tomllib
from pathlib import Path

DISCORD_MESSAGE_LIMIT = 2000

PYPROJECT_PATH = Path(__file__).resolve().parent.parent / "pyproject.toml"
CHANGELOG_PATH = Path(__file__).resolve().parent.parent / "CHANGELOG.md"


def get_current_version() -> str | None:
    """Return the version baked into this image's pyproject.toml, or None if unreadable."""
    if not PYPROJECT_PATH.exists():
        return None
    try:
        with open(PYPROJECT_PATH, "rb") as f:
            data = tomllib.load(f)
        return data["tool"]["poetry"]["version"]
    except (KeyError, tomllib.TOMLDecodeError):
        return None


def get_latest_changelog_entry() -> str | None:
    """Return the top '## [version] - date' block from CHANGELOG.md, or None if unavailable.

    generate_changelog (a git hook, not touched here) always writes newest-first,
    so the first '## [' header is the current release.
    """
    if not CHANGELOG_PATH.exists():
        return None
    lines = CHANGELOG_PATH.read_text(encoding="utf-8").splitlines()
    start = next((i for i, line in enumerate(lines) if line.startswith("## [")), None)
    if start is None:
        return None
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## [")), len(lines))
    return "\n".join(lines[start:end]).strip()


def _split_into_chunks(text: str, first_budget: int, budget: int) -> list[str]:
    """Split text into chunks at line boundaries, so a bullet is never cut mid-line.

    The first chunk gets a smaller budget since it shares a message with the header.
    """
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    limit = first_budget
    for line in text.splitlines():
        line_len = len(line) + 1  # + the newline that joins it to the next line
        if current and current_len + line_len > limit:
            chunks.append("\n".join(current))
            current = []
            current_len = 0
            limit = budget
        current.append(line)
        current_len += line_len
    if current:
        chunks.append("\n".join(current))
    return chunks


def build_deploy_announcement(version: str, changelog_entry: str | None) -> list[str]:
    """Format the deploy announcement as one or more Discord messages.

    A changelog entry is split across multiple messages at line boundaries instead
    of being truncated -- nothing about what changed is ever silently dropped just
    because it doesn't fit in one 2000-char Discord message.
    """
    header = f"🚀 Deployed **v{version}**"
    if not changelog_entry:
        return [f"{header}\n_(no changelog entry found for this version)_"]

    chunks = _split_into_chunks(
        changelog_entry,
        first_budget=DISCORD_MESSAGE_LIMIT - len(header) - 2,
        budget=DISCORD_MESSAGE_LIMIT,
    )
    return [f"{header}\n\n{chunks[0]}"] + chunks[1:]
