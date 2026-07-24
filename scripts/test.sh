#!/bin/sh
# Deterministic test wrapper (HalloweenEvent pattern): builds the test image and
# runs the suite in an ephemeral container with dev deps installed ad hoc.
# Engine-agnostic — uses `docker compose` when available, else `podman compose`.
#
# Usage:
#   scripts/test.sh          run the full pytest suite
#   scripts/test.sh audit    run pip-audit over requirements.txt
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
else
    $COMPOSE -f docker-compose-test.yml run --rm --entrypoint sh gbot-test -c \
        "pip install -r requirements-dev.txt -q && python -m pytest -q"
fi
