#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

if [ -n "$(git status --porcelain)" ]; then
    echo "ERROR: uncommitted changes present. Commit first -- otherwise the" >&2
    echo "deployed code won't match what's actually in git:" >&2
    git status --short >&2
    exit 1
fi

SERVICE="${1:-bot}"

docker compose build "$SERVICE"
docker compose up -d "$SERVICE"

# Every deploy announces to the log channel -- not just the bot's own (that
# used to be the only one that could, since it relied on the bot detecting
# its own restart; nllb/libretranslate never touched that code path at all).
SHA="$(git rev-parse --short HEAD)"
SUBJECT="$(git log -1 --format=%s)"
docker exec polyglot-relay-bot python -u -m app.announce_deploy "$SERVICE" "$SHA" "$SUBJECT" \
    || echo "WARNING: could not post the deploy announcement to Discord" >&2
