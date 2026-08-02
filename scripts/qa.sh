#!/bin/sh
# Deterministic wrapper for the /qa skill — runs a prod-shaped GBot container built
# from the CURRENT WORKING TREE, for manual QA of surfaces the test suite can't cover.
#
# Identity: QA runs as gbot.dev01 BY DEFAULT (Shared/gbot.env.dev). The rule QA rests on is
# "one Discord token runs in exactly one place at a time" — NOT "production must be down".
# gbot.dev01 runs nowhere else, so a dev QA window leaves the Pi's gbot.prod01 serving real
# users untouched. Pass `prod` only when the change genuinely needs the production identity
# (a real guild's data, or a Patreon-gated path in a really-subscribed server) — that one
# DOES require stopping the Pi container first.
#
# Note the caveat that outlives the identity split: both identities share ONE Firebase project.
# Per-guild data (servers/<id>: config, toggles, hype) is partitioned, so a dev-guild QA is
# isolated. But gcoin/<userId>, leaderboards and patreon_members are GLOBAL roots — a storm win
# or a trade in the test guild credits real balances. Music is the easy case: it writes nothing
# to Firebase at all.
#
# Safety rails baked in:
#   - IMAGE_TAG=qa: the build is tagged ghcr.io/cgoulart35/gbot:qa — invisible to the
#     Pi's deploy watcher (which only compares :latest image IDs) and never clobbers
#     the locally pulled :latest image.
#   - Single-instance gate on `up`: the container logs into Discord with a REAL token and
#     reads/writes the REAL Firebase RTDB, so `up` refuses to start unless QA_CONFIRM=yes
#     acknowledges that the chosen identity is not already running somewhere.
# Reuses docker-compose-prod.yml on purpose, so QA exercises the real production compose
# rather than a lookalike that could drift from it.
# Engine-agnostic — uses `docker compose` when available, else `podman compose`.
#
# Usage:
#   QA_CONFIRM=yes scripts/qa.sh up [dev|prod]   build from the working tree + start (detached)
#   scripts/qa.sh logs [N]                       tail the last N (default 50) log lines
#   scripts/qa.sh ps                             show container status
#   scripts/qa.sh down                           stop and remove the QA container
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
        case "${2:-dev}" in
            dev)  IDENTITY=gbot.dev01;  export GBOT_ENV_FILE=gbot.env.dev ;;
            prod) IDENTITY=gbot.prod01; export GBOT_ENV_FILE=gbot.env ;;
            *)    echo "qa.sh: unknown identity '$2' — expected 'dev' or 'prod'." >&2; exit 2 ;;
        esac
        if [ ! -f "Shared/$GBOT_ENV_FILE" ]; then
            echo "qa.sh: Shared/$GBOT_ENV_FILE is missing — copy it from the Pi's Shared/ directory." >&2
            exit 1
        fi
        ls Shared/serviceAccountKey.json >/dev/null    # fail loudly if the DB credential is missing
        if [ "${QA_CONFIRM:-}" != "yes" ]; then
            echo "qa.sh: refusing to start — this runs a REAL bot (real Discord token + real Firebase)." >&2
            echo "qa.sh: confirm $IDENTITY is not running anywhere else (the Pi included), then re-run as:" >&2
            echo "qa.sh:   QA_CONFIRM=yes scripts/qa.sh up ${2:-dev}" >&2
            exit 1
        fi
        echo "qa.sh: starting QA as $IDENTITY (Shared/$GBOT_ENV_FILE)"
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
        echo "usage: [QA_CONFIRM=yes] scripts/qa.sh up [dev|prod] | logs [N] | ps | down" >&2
        exit 2
        ;;
esac
