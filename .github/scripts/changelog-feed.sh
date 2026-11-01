#!/usr/bin/env bash
# Turns one push to develop into short changelog lines and posts them to Discord: one line per
# merged PR or directly pushed commit. Lives under .github/ so that changing it publishes no image.
#
# Env: GH_REPO, GH_TOKEN, HEAD_SHA, BEFORE_SHA, DRY_RUN ("true" prints instead of posting), and
# DISCORD_WEBHOOK when posting. Commit text only ever reaches jq as an argument, never the shell.
# MESSAGE, from a manual run only, posts that exact text instead of describing any commits.
set -euo pipefail

MAX_MESSAGE_LENGTH=1900
MAX_COMMITS=50
DISCORD_MESSAGE_LIMIT=2000
repoUrl="https://github.com/$GH_REPO"
# separates an entry's title row from its description row, so the cap below counts whole entries
ROW_BREAK=$'\x1f'

post() {
  if [ "${DRY_RUN:-false}" = "true" ]; then
    printf '%s\n' "$1"
    return 0
  fi
  # flags 4 is SUPPRESS_EMBEDS, so links add no preview cards; empty parse means nobody gets pinged
  jq -n --arg content "$1" '{content: $content, flags: 4, allowed_mentions: {parse: []}}' |
    curl --fail-with-body --silent --show-error -H 'Content-Type: application/json' -d @- "$DISCORD_WEBHOOK"
}

if [ -n "${MESSAGE:-}" ]; then
  if [ "${#MESSAGE}" -gt "$DISCORD_MESSAGE_LIMIT" ]; then
    echo "::error::message is ${#MESSAGE} characters; Discord allows $DISCORD_MESSAGE_LIMIT"
    exit 1
  fi
  post "$MESSAGE"
  exit 0
fi

# "feat(music): add x" -> "feat<TAB>add x". Prints nothing for a type this feed hides.
classify() {
  local subject="$1" type rest
  if [[ "$subject" =~ ^([a-zA-Z]+)(\(([^\)]*)\))?\!?:[[:space:]]*(.*)$ ]]; then
    type="$(printf '%s' "${BASH_REMATCH[1]}" | tr '[:upper:]' '[:lower:]')"
    rest="${BASH_REMATCH[4]}"
    case "$type" in docs|ci|test) return 0 ;; esac
    if [ "${BASH_REMATCH[3]}" = "deps" ]; then type="deps"; fi
    printf '%s\t%s' "$type" "$rest"
  else
    # most PR titles here have a prefix, but not all (#26), and those still count as news
    printf 'change\t%s' "$subject"
  fi
}

# The friendlier word a channel reader sees for a type.
labelFor() {
  case "$1" in
    feat) echo "New" ;;
    fix) echo "Fixed" ;;
    deps) echo "Updated" ;;
    *) echo "Changed" ;;
  esac
}

# The first "Changelog: ..." line of a PR description or commit message, or nothing. Optional, and
# deliberately explicit: PR descriptions open with whatever suits a reviewer, which is often
# planning references or a bot's release notes, so they cannot be posted as they are.
changelogLine() {
  jq -Rrs 'split("\n") | map(sub("\r$"; "")) | map(select(test("^changelog:[[:space:]]*[^[:space:]]"; "i")))[0] // "" | sub("^changelog:[[:space:]]*"; ""; "i") | sub("[[:space:]]+$"; "")'
}

# Prints one entry for one commit on develop's first-parent history, or nothing if it is hidden.
describeCommit() {
  local commit="$1" sha parentCount subject label title classified number pull description type
  sha="$(jq -r '.sha' <<< "$commit")"
  parentCount="$(jq '.parents | length' <<< "$commit")"
  subject="$(jq -r '.commit.message | split("\n")[0]' <<< "$commit")"
  label="[\`${sha:0:7}\`](<$repoUrl/commit/$sha>)"
  if [ "$parentCount" -gt 1 ]; then
    # a merge's subject is only "Merge pull request #N from...", so the title comes from the PR
    number="$(gh api "repos/$GH_REPO/commits/$sha/pulls" --jq '.[0].number // empty')"
    if [ -z "$number" ]; then
      return 0 # merging develop into a branch and back, say: no PR to describe, nothing new to say
    fi
    pull="$(gh api "repos/$GH_REPO/pulls/$number")"
    title="$(jq -r '.title' <<< "$pull")"
    description="$(jq -r '.body // ""' <<< "$pull" | changelogLine)"
    label="[#$number](<$repoUrl/pull/$number>)"
  else
    title="$subject"
    description="$(jq -r '.commit.message' <<< "$commit" | changelogLine)"
  fi
  classified="$(classify "$title")"
  if [ -n "$classified" ]; then
    type="${classified%%$'\t'*}"
    printf '**%s** %s (%s)' "$(labelFor "$type")" "${classified#*$'\t'}" "$label"
    # -# is Discord's small subtext, so the description sits quietly under its title
    if [ -n "$description" ]; then
      printf '%s-# %s' "$ROW_BREAK" "$description"
    fi
    printf '\n'
  fi
}

# Walk first parents only, so a merged branch's own commits never post. Newest first; reversed below.
lines=""
sha="$HEAD_SHA"
count=0
while [ "$count" -lt "$MAX_COMMITS" ]; do
  commit="$(gh api "repos/$GH_REPO/commits/$sha")"
  line="$(describeCommit "$commit")"
  if [ -n "$line" ]; then
    lines="$line"$'\n'"$lines"
  fi
  count=$((count + 1))
  parent="$(jq -r '.parents[0].sha // empty' <<< "$commit")"
  # a brand-new branch reports an all-zero BEFORE_SHA that is never reached, so stop after one.
  # A prefix match, because a manual run may pass a short hash where a push always sends a full one.
  if [ -z "$parent" ] || [[ "$parent" == "$BEFORE_SHA"* ]] || [[ "$BEFORE_SHA" =~ ^0+$ ]]; then
    break
  fi
  sha="$parent"
done

message=""
total=0
kept=0
while IFS= read -r line; do
  [ -n "$line" ] || continue
  total=$((total + 1))
  if [ $(( ${#message} + ${#line} + 1 )) -le "$MAX_MESSAGE_LENGTH" ]; then
    message+="${line//$ROW_BREAK/$'\n'}"$'\n'
    kept=$((kept + 1))
  fi
done <<< "$lines"

if [ -z "$message" ]; then
  echo "Nothing to post for this push."
  exit 0
fi
if [ "$kept" -lt "$total" ]; then
  message+="...and $((total - kept)) more"
fi

post "$message"
