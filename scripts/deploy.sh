#!/bin/sh
# Deploy the current prod image from GHCR. Matches origin/develop; gitignored secrets are untouched.
# Run on-demand (dev/QA redeploy) or by scripts/deploy-watcher.sh when a new image is published.
set -u
cd "$(dirname "$0")/.." || exit 1
COMPOSE="docker compose -f docker-compose-prod.yml"

git fetch origin develop --quiet
git checkout -f develop --quiet            # switch to develop even if a dev left us on another branch (-f discards tracked dev edits)
git reset --hard origin/develop --quiet    # match remote exactly; gitignored secrets (Shared/gbot.env, Shared/serviceAccountKey.json) untouched

$COMPOSE pull
$COMPOSE up -d                             # recreates only the containers whose image changed
docker image prune -f
