#!/bin/sh
# Deterministic wrapper for the /qa skill — runs a prod-shaped GBot container built
# from the CURRENT WORKING TREE, for manual QA of surfaces the test suite can't cover.
# Safety rails baked in:
#   - IMAGE_TAG=qa: the build is tagged ghcr.io/cgoulart35/gbot:qa — invisible to the
#     Pi's deploy watcher (which only compares :latest image IDs) and never clobbers
#     the locally pulled :latest image.
#   - Single-instance gate on `up`: the container logs into Discord with the REAL token
#     and reads/writes the REAL Firebase RTDB. The live Pi instance must be stopped
#     first (maintainer-run) — two bots must never share one identity/state — so `up`
#     refuses to start unless QA_CONFIRM=yes acknowledges that.
# Engine-agnostic — uses `docker compose` when available, else `podman compose`.
#
# Usage:
#   QA_CONFIRM=yes scripts/qa.sh up    build from the working tree + start (detached)
#   scripts/qa.sh logs [N]             tail the last N (default 50) log lines
#   scripts/qa.sh ps                   show container status
#   scripts/qa.sh down                 stop and remove the QA container
set -e

cd "$(dirname "$0")/.."

if docker compose version >/dev/null 2>&1; then
    COMPOSE="docker compose"
else
    COMPOSE="podman compose"
fi
export IMAGE_TAG=qa

case "${1:-}" in
    up)
        ls Shared/gbot.env Shared/serviceAccountKey.json >/dev/null    # fail loudly if secrets are missing
        if [ "${QA_CONFIRM:-}" != "yes" ]; then
            echo "qa.sh: refusing to start — this runs the REAL bot (real Discord token + real Firebase)." >&2
            echo "qa.sh: confirm the live Pi instance is STOPPED, then re-run as: QA_CONFIRM=yes scripts/qa.sh up" >&2
            exit 1
        fi
        $COMPOSE -f docker-compose-prod.yml up -d --build
        ;;
    logs)
        $COMPOSE -f docker-compose-prod.yml logs --tail "${2:-50}"
        ;;
    ps)
        $COMPOSE -f docker-compose-prod.yml ps
        ;;
    down)
        $COMPOSE -f docker-compose-prod.yml down
        ;;
    *)
        echo "usage: [QA_CONFIRM=yes] scripts/qa.sh up | logs [N] | ps | down" >&2
        exit 2
        ;;
esac
