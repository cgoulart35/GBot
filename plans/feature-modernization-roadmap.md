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

## Workstream D — Spotify listening integration (new feature — define before building)

Two tiers to choose between: **presence-based** (Discord already exposes members' Spotify activity via `member.activities` — no Spotify API, no OAuth; enables now-playing surfacing, listening leaderboards, shared-listening prompts) vs **Spotify Web API** (per-user OAuth; playlists, top tracks, richer data, real "listen along"). Recommendation: ship presence-based first, evaluate the API tier after real usage.

## Workstream E — Whole-bot design pass ("EVERYTHING")

Rolling per-area review, one area per change set: scheduled events (`tasks.loop` lifecycles, missed-run behavior across restarts), properties (typed/validated config; A-1/A-2 land here), logging (JSON formatter noise levels, per-cog verbosity), message/embed consistency, rules/config UX (`.toggle` discoverability), user-facing error messages, API resources parity with cog features, per-guild state lifecycle invariants (`on_ready`/`on_guild_join`/`on_guild_remove`), and writing down the implicit RTDB schema per queries file.

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
