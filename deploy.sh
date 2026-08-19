#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

if [ -n "$(git status --porcelain)" ]; then
    echo "ERROR: uncommitted changes present. Commit first -- otherwise the" >&2
    echo "deploy SHA baked into the image won't match what's actually running:" >&2
    git status --short >&2
    exit 1
fi

SERVICE="${1:-bot}"

# Only "bot" reads deploy_commit_log.txt/deploy_sha.txt (the deploy-announcement
# feature) -- libretranslate/nllb don't need them, so skip generating them there.
if [ "$SERVICE" = "bot" ]; then
    git log --format="%H %s" -50 > deploy_commit_log.txt
    git rev-parse HEAD > deploy_sha.txt
fi

docker compose build "$SERVICE"
docker compose up -d "$SERVICE"
