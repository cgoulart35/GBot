#!/bin/sh
# Deterministic wrapper for the /qa skill — runs GBot from the CURRENT WORKING TREE, for manual
# QA of surfaces the test suite can't cover.
#
# One compose file per instance, each naming its own env file: docker-compose-dev.yml is
# gbot.dev01 (GBot#9690), docker-compose-prod.yml is gbot.prod01 (GBot#6890). This script just
# picks which one to bring up; it does not override anything inside them.
#
# Identity: QA runs as gbot.dev01 BY DEFAULT. The rule QA rests on is "one Discord token runs in
# exactly one place at a time" — NOT "production must be down". Both identities live on the Pi, so
# a QA run BORROWS one: stop that instance there, run it here, put it back when you're done. The
# other keeps serving throughout, which is why dev is the default — borrowing it never interrupts
# real users. Reach for `prod` only when the change genuinely needs the production identity.
#
# Note the caveat that outlives the identity split: both share ONE Firebase project. Per-guild
# data (servers/<id>: config, toggles, hype) is partitioned, so QA in a dev guild is isolated. But
# gcoin/<userId>, leaderboards and patreon_members are GLOBAL roots — a storm win or a trade in
# the test guild credits a real balance. Music is the easy case: it writes nothing to Firebase.
#
# Safety rails baked in:
#   - IMAGE_TAG=qa: `up prod` builds ghcr.io/cgoulart35/gbot:qa rather than clobbering the locally
#     pulled :latest, and the Pi's deploy watcher only ever compares :latest, so it cannot see a
#     QA build. (The dev compose names no image at all, so its build is already invisible.)
#   - Single-instance gate on `up`: the container logs into Discord with a REAL token and
#     reads/writes the REAL Firebase RTDB, so `up` refuses to start unless QA_CONFIRM=yes
#     acknowledges that the chosen identity is not already running somewhere.
# Engine-agnostic — uses `docker compose` when available, else `podman compose`.
#
# Usage:
#   QA_CONFIRM=yes scripts/qa.sh up [dev|prod]   build from the working tree + start (detached)
#   scripts/qa.sh logs [N]                       tail the last N (default 50) log lines
#   scripts/qa.sh ps                             show container status
#   scripts/qa.sh down                           stop and remove the QA container
#
# logs/ps/down deliberately take no identity and cover BOTH files: only one QA container is ever
# up, so there is nothing ambiguous to report — and `down` can never leave one running because
# you named the wrong side.
set -e

cd "$(dirname "$0")/.."

if docker compose version >/dev/null 2>&1; then
    COMPOSE="docker compose"
else
    COMPOSE="podman compose"
fi
export IMAGE_TAG=qa

DEV_FILE=docker-compose-dev.yml
PROD_FILE=docker-compose-prod.yml

case "${1:-}" in
    up)
        case "${2:-dev}" in
            dev)  IDENTITY=gbot.dev01;  FILE=$DEV_FILE;  ENV_FILE=gbot.env.dev ;;
            prod) IDENTITY=gbot.prod01; FILE=$PROD_FILE; ENV_FILE=gbot.env ;;
            *)    echo "qa.sh: unknown identity '$2' — expected 'dev' or 'prod'." >&2; exit 2 ;;
        esac
        if [ ! -f "Shared/$ENV_FILE" ]; then
            echo "qa.sh: Shared/$ENV_FILE is missing — copy it from the Pi's Shared/ directory." >&2
            exit 1
        fi
        ls Shared/serviceAccountKey.json >/dev/null    # fail loudly if the DB credential is missing
        if [ "${QA_CONFIRM:-}" != "yes" ]; then
            echo "qa.sh: refusing to start — this runs a REAL bot (real Discord token + real Firebase)." >&2
            echo "qa.sh: confirm $IDENTITY is stopped on the Pi, then re-run as:" >&2
            echo "qa.sh:   QA_CONFIRM=yes scripts/qa.sh up ${2:-dev}" >&2
            exit 1
        fi
        echo "qa.sh: starting QA as $IDENTITY ($FILE, Shared/$ENV_FILE)"
        $COMPOSE -f "$FILE" up -d --build
        ;;
    # `|| true` on each: whichever identity is NOT up is a no-op here, and under `set -e` a
    # non-zero from that no-op would abort before the one that matters ran — for `down` that
    # would leave a real, token-holding container running, the exact opposite of the guarantee
    # above. Today's engines return 0 for it, but the guarantee must not depend on that.
    logs)
        $COMPOSE -f "$DEV_FILE" logs --tail "${2:-50}" || true
        $COMPOSE -f "$PROD_FILE" logs --tail "${2:-50}" || true
        ;;
    ps)
        $COMPOSE -f "$DEV_FILE" ps || true
        $COMPOSE -f "$PROD_FILE" ps || true
        ;;
    down)
        $COMPOSE -f "$DEV_FILE" down || true
        $COMPOSE -f "$PROD_FILE" down || true
        ;;
    *)
        echo "usage: [QA_CONFIRM=yes] scripts/qa.sh up [dev|prod] | logs [N] | ps | down" >&2
        exit 2
        ;;
esac
