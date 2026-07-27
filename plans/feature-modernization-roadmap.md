# Post-modernization Plan 2 — Feature modernization roadmap

**Scoped from the maintainer's brief (2026-07-25); several items need maintainer discussion before implementation — those are marked.** Written to be executed by a fresh session with no prior context, on any model. Driving convention: read top-to-bottom, first non-done item, pre-flight (full suite green in-image), one coherent change set at a time.

**Prerequisite:** Plan 1 Milestone 1 (bot live on Pi via image-based CD) — every change here rides the pipeline end-to-end: branch → PR → auto-review → merge on maintainer OK → publish → watcher redeploys. Method for each change: `/implement-dev-changes`. Invariants: 100% coverage on `GBotDiscord/src`, pip-audit 0, no regressions to the dual-command pattern or accepted trade-offs.

## Workstream A — Missed-bug sweep (do first; it seeds everything else)

Seed list (found during modernization, deferred here):

1. **String-typed property defaults** — `properties.py getEnvProperty` returns the raw string default when an env var is unset (defaults never pass through `determineValue`), so e.g. an omitted `STORMS_MIN_TIME_BETWEEN_SECONDS` yields `"3600"` (str) and `random.randint("3600", …)` would raise. Never fires today only because compose `env_file` supplies every key. Fix: route defaults through `determineValue` + tests.
2. **`setProperty` skips type coercion** — the runtime-mutation API path stores the raw JSON value (string or number) with no `determineValue`/validation, so a runtime-set int property can hold a string until restart. Verify, then fix with coercion + a failure response for unparseable values.
3. Sweep method: per-cog read-through with a bug ledger appended to this file; grep for bare `except:` blocks (several in `development_resource.py` swallow root causes), TODO/FIXME markers; catalog the ~8 deprecation warnings the suite emits on bare-runner CI (0 in-image) and fix any that are real nextcord 3.x deprecations.

## Workstream B — Multi-instance story & sharding (DISCUSS FIRST — maintainer asked)

Primer for the discussion:
- **Sharding** (the Discord term) = ONE bot application splitting its gateway socket into N shard connections; every guild maps to exactly one shard (`guild_id >> 22 % N`). Discord mandates it at 2,500 guilds. nextcord support: `AutoShardedBot`. It is **not** load-balancing across replicas — you cannot run two copies of the same token for redundancy/throughput; each event belongs to exactly one shard, and duplicate full instances would double-fire every storm/message handler.
- **What GBot already has**: `utils.filterGuildsForInstance` — multiple bot *applications* (different tokens) sharing one Firebase, partitioned by which guilds each instance is in. That's the real multi-instance mechanism today.
- **Realistic goals**: (1) a persistent **test/dev instance** — a second Discord application + token in a private test guild, run from the dev compose (dev machine or Pi), optionally against a separate Firebase project or a namespaced DB root, enabling live debugging with zero prod risk; (2) `AutoShardedBot` only if guild count ever approaches thousands (not now).
- **Decisions to record here after discussion**: create the second Discord app? DB isolation (shared DB + disjoint guilds via `filterGuildsForInstance`, vs separate Firebase project)? where the test instance runs; whether legacy dev-attach flow (debugpy compose) stays the local debug path.

## Workstream C — Music (YouTube) architecture revisit

Current design: yt-dlp based, per-guild queues/state, cache with `MUSIC_CACHE_DELETION_TIMEOUT_MINUTES`. Known pain: yt-dlp breakage cadence (the Pi's last pre-modernization commit was literally "Fixing music bot - upgrading yt-dlp"), download-then-play latency, disk usage on the Pi. Explore: streaming vs download, cache keying/eviction, voice-reconnect robustness, search/queue UX, cross-server reuse of cached tracks, CPU/thermals on the Pi during playback. Output: an architecture note in this file, then incremental PRs.

**Music bug ledger** — append findings here as they're observed in production; this workstream fixes them.

| # | Finding | Evidence | Severity |
|---|---|---|---|
| C-1 | **Voice-connect failure loop.** `nextcord.errors.ConnectionClosed: Shard ID None WebSocket closed with 4017` with `Failed to connect to voice... Retrying...`, repeating ~every 1–5s. Observed on the live Pi bot `2026-07-25 22:36` (outside Milestone 1's verification window, so *not* covered by that "0 tracebacks" record). Close code 4017 is an unknown/invalid opcode from the voice gateway — usually a nextcord-vs-voice-gateway version mismatch, not a network fault. Investigate whether the pinned nextcord version's voice implementation is current, and whether the retry loop is bounded (an unbounded loop burns CPU on the Pi and floods logs). | `docker logs GBot_7.0_prod` | correctness + Pi resource risk |

**How to check for recurrences on the Pi** (read-only; containers are maintainer-managed): scope errors to the current session rather than a time window, because the Pi's clock jumps at boot —
`docker logs GBot_7.0_prod 2>&1 | tac | awk '/GBot logged in as/{exit} {print}' | tac | grep -iE 'voice|4017|Traceback'`

## Workstream D — Spotify listening integration (new feature — define before building)

**⚠ Corrected 2026-07-26 — the presence-based tier ALREADY SHIPS.** This workstream was written as "new feature, define before building"; that premise was wrong. `music_cog.py` already has `/spotify <user>` (`strings.SPOTIFY_NAME`, cog line ~159), a `spotify_sync` `tasks.loop` (~line 116), per-guild `spotifySyncSessions` state, and `from nextcord import Spotify`. It reads a member's Discord Spotify activity and queues the matching track downloaded from YouTube, following the user as their activity changes. It is documented on the docs site (`docs/commands-music.md`). Found while auditing GBot-Docs for Plan 1 Milestone 2b.

So the real question is **not** "which tier to build first" but **"is the shipped presence-based feature good, and is the Web API tier worth adding?"** Re-scope as: (1) audit the existing `/spotify` implementation — sync-loop lifecycle across restarts, what happens when the followed user stops/switches, cleanup of `spotifySyncSessions` on `on_guild_remove`, and its share of the Workstream C yt-dlp/voice pain (see C-1); (2) only then evaluate **Spotify Web API** (per-user OAuth; playlists, top tracks, real "listen along") as a genuine tier-2 addition.

## Workstream E — Whole-bot design pass ("EVERYTHING")

Rolling per-area review, one area per change set: scheduled events (`tasks.loop` lifecycles, missed-run behavior across restarts), properties (typed/validated config; A-1/A-2 land here), logging (JSON formatter noise levels, per-cog verbosity), rules/config UX (`.toggle` discoverability), API resources parity with cog features, per-guild state lifecycle invariants (`on_ready`/`on_guild_join`/`on_guild_remove`), and writing down the implicit RTDB schema per queries file.

**Known gap for the "API resources parity" bullet — the docs site has a dead page.** `GBot-Docs/docs/activity.md` fetches `{{site.gbot_host}}/GBot/public/activity`, which returns **404**: GBot exposes exactly one public route, `/GBot/public/leaderboard/`, and `git log -S "public/activity" --all` shows the activity endpoint has **never existed in git history**. So that page shipped without its backend and has always been silently broken on the live site. Needs a decision: build a public activity endpoint, or delete the page from GBot-Docs. (The leaderboard pages are fine — they fetch without a trailing slash and get a 308 redirect, which `fetch` follows.) Found during the Plan 1 Milestone 2b docs audit, 2026-07-26.

**Moved out:** *message/embed consistency* and *user-facing error messages* were originally bullets here. The 2026-07-26 survey found 166 plain-text send sites across 8 live cogs — far too large for a rolling bullet — so they are now [presentation-and-ux-consistency.md](presentation-and-ux-consistency.md) (Plan 3), which also carries the ephemeral-reply and `defer()`-coverage defects it uncovered.

## Workstream F — Discord App Directory / marketability (north star, continuous)

Not a build-now item; acceptance criteria the other workstreams should not violate: bot verification readiness (required at scale), **slash-first UX** — the App Directory disfavors Message-Content-intent dependence, and legacy prefix commands depend on it (the dual-command pattern already gives full slash coverage; a future per-guild prefix retirement would revisit that accepted trade-off), privacy policy + terms of service documents, a support server, and eventually App Subscriptions/SKUs for monetization. Any new feature (C/D) ships slash-first.

## Suggested order & status

B discussion + A seeds → C (most user-visible pain) → D → E rolling → F as continuous criteria.

| Item | Status |
|---|---|
| A — bug sweep (seeds 1–2, then ledger) | pending |
| B — multi-instance/sharding decisions | **blocked on maintainer discussion** |
| C — music architecture note + PRs | pending |
| D — Spotify tier decision + presence-based v1 | pending |
| E — per-area passes | pending |
| F — directory-readiness criteria | continuous |
