#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

git log --format="%H %s" -50 > deploy_commit_log.txt
git rev-parse HEAD > deploy_sha.txt

docker compose build bot
docker compose up -d bot
