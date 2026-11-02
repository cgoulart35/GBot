#!/bin/sh
# Builds or previews the website in a throwaway Ruby container, so the host needs no Ruby.
# Gems are cached in a named volume. Nothing here touches the bot or its images.
#
# Usage:
#   scripts/site.sh            serve a preview on http://localhost:4000/GBot/
#   scripts/site.sh build      build into site/_site
#   scripts/site.sh check      build a separate copy, so a running preview is left alone, and check every link and image
set -e

cd "$(dirname "$0")/.."

if docker version >/dev/null 2>&1; then
    ENGINE=docker
else
    ENGINE=podman
fi

run() {
    $ENGINE run --rm "$@"
}

SETUP="apt-get -qq update >/dev/null && apt-get -qq install -y build-essential libcurl4 >/dev/null && bundle install --quiet"
MOUNTS="-v $PWD/site:/site -v gbot-site-gems:/usr/local/bundle -w /site"

case "$1" in
    "")
        run -it -p 4000:4000 $MOUNTS docker.io/library/ruby:3.3-slim sh -c \
            "$SETUP && bundle exec jekyll serve --host 0.0.0.0 --port 4000"
        ;;
    build)
        run $MOUNTS docker.io/library/ruby:3.3-slim sh -c "$SETUP && bundle exec jekyll build"
        ;;
    check)
        run $MOUNTS docker.io/library/ruby:3.3-slim sh -c \
            "$SETUP && bundle exec jekyll build --baseurl '' --destination /tmp/site-check && bundle exec htmlproofer /tmp/site-check --disable-external"
        ;;
    *)
        echo "Usage: scripts/site.sh [build|check]" >&2
        exit 2
        ;;
esac
