#!/bin/sh
# Deterministic test wrapper (HalloweenEvent pattern): builds the test image and
# runs the suite in an ephemeral container with dev deps installed ad hoc.
# Engine-agnostic — uses `docker compose` when available, else `podman compose`.
# The gbot-test image is its own tag (never ghcr.io/cgoulart35/gbot:latest), so
# runs here are invisible to the Pi's deploy watcher and can't trigger a redeploy.
#
# Usage:
#   scripts/test.sh                                     run the full pytest suite
#   scripts/test.sh audit                               run pip-audit over requirements.txt
#   scripts/test.sh coverage                            run the suite under coverage + report (the 100% gate)
#   scripts/test.sh -k storm                            anything else passes through to pytest
#   scripts/test.sh GBotDiscord/test/gcoin/gcoin_test.py
set -e

cd "$(dirname "$0")/.."

if docker compose version >/dev/null 2>&1; then
    COMPOSE="docker compose"
else
    COMPOSE="podman compose"
fi

$COMPOSE -f docker-compose-test.yml build

if [ "$1" = "audit" ]; then
    $COMPOSE -f docker-compose-test.yml run --rm --entrypoint sh gbot-test -c \
        "pip install -r requirements-dev.txt -q && pip-audit -r requirements.txt"
elif [ "$1" = "coverage" ]; then
    $COMPOSE -f docker-compose-test.yml run --rm --entrypoint sh gbot-test -c \
        "pip install -r requirements-dev.txt -q && coverage run -m pytest -q && coverage report -m"
else
    $COMPOSE -f docker-compose-test.yml run --rm --entrypoint sh gbot-test -c \
        "pip install -r requirements-dev.txt -q && python -m pytest -q $*"
fi
