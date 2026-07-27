# Post-modernization Plan 2 — Feature modernization roadmap

**Scoped from the maintainer's brief (2026-07-25); several items need maintainer discussion before implementation — those are marked.** Written to be executed by a fresh session with no prior context, on any model. Driving convention: read top-to-bottom, first non-done item, pre-flight (full suite green in-image), one coherent change set at a time.

**Prerequisite:** Plan 1 Milestone 1 (bot live on Pi via image-based CD) — every change here rides the pipeline end-to-end: branch → PR → auto-review → merge on maintainer OK → publish → watcher redeploys. Method for each change: `/implement-dev-changes`. Invariants: 100% coverage on `GBotDiscord/src`, pip-audit 0, no regressions to the dual-command pattern or accepted trade-offs.

## Workstream A — Missed-bug sweep (do first; it seeds everything else)

**Seeds 1–3 are DONE (2026-07-26).** The read-through is complete and its output — the bug ledger below — is what seeds the remaining workstreams.

1. ~~**String-typed property defaults**~~ — **FIXED.** `getEnvProperty` now routes defaults through `determineValue`. Confirmed worse than recorded: an unset `PATREON_IGNORE_GUILDS` defaulted to `""` (str), and `utils.getGuildsForPatreonToIgnore()` does `patreonGuildId not in guildsToIgnore` with an int → `TypeError` on a path nearly every command touches. Only compose's `env_file` supplying every key kept it latent.
2. ~~**`setProperty` skips type coercion**~~ — **FIXED.** Verified: the API path stored the raw JSON value. Now coerced through `determineValue`, with `PropertyValueInvalid` → `{"status": "failure", "message": "Invalid value for property 'X'."}` instead of a silently wrong type. The if/elif chain became a `MUTABLE_PROPERTIES` allowlist + `setattr` (this removes the whole class of copy-paste clobber bug the `WHODIS_COOLDOWN_MINUTES` regression test guards), and the success message now echoes the **stored** value rather than the requested one. `determineValue` also accepts already-typed values (JSON list for splittables, resolved level for `LOG_LEVEL`) so API payloads and env strings share one coercion point.
3. ~~**Sweep method**~~ — **DONE.** TODO/FIXME markers: **none**. Bare `except:`: 14 live sites (2 more inside the commented-out Halo code), all cataloged as A-3 below. The "~8 deprecation warnings on bare-runner CI (0 in-image)" turned out to be **neither deprecations nor a real difference**: all 8 are `SyntaxWarning: invalid escape sequence '\s'` from one non-raw regex literal repeated 8× in `hype_test.py` (fixed with `r"..."`), and there are **zero nextcord 3.x deprecation warnings anywhere**. The in-image "0" was a **tooling blind spot**, not a cleaner environment: the repo bind-mount carries the host's `__pycache__`, and compile-time diagnostics never re-emit from cached bytecode. `docker-compose-test.yml` now sets `PYTHONPYCACHEPREFIX=/tmp/pycache` so in-image runs and CI agree.

### Bug ledger

From a full read-through of every live source file (Halo excluded). **Nothing below is fixed** — Workstream A produced the list; later change sets consume it. Ordered by severity within each group.

**Correctness — user-visible**

| # | Finding | Location |
|---|---|---|
| A-1 | **DM commands from subscribers are always rejected.** `isGuildOrUserSubscribed` checks `serverId in mutualGuilds`, comparing an `int` against a list of `nextcord.Guild` objects — always `False`. So the entire "command made in a private message by someone in a subscribed guild" path is dead, and DM users get "you do not have access to GBot" unless they share an *ignored* guild. The ignore-list branch 12 lines above does it correctly (`for mutualGuild in mutualGuilds: if mutualGuild.id in ...`). | `predicates.py:125` |
| A-2 | **Patron validation stops at the first ignored server.** The loop over `allPatronMembers` uses `break` where it means `continue`, so once any patron entry maps to an ignored server, every remaining patron is skipped — stale entries are never reaped. | `patreon_cog.py:44` |
| A-3 | **Disabling Music by slash command doesn't disconnect the voice client.** Every other branch of `commonToggle` accepts both the legacy word and the emoji choice; the teardown check is `if feature_type == 'music'` only, and the slash choice value is `'🎵 Music'`. So `/toggle` leaves the bot sitting in voice with a live queue. | `config_cog.py:339` |
| A-4 | **Non-blocking locks whose return value is discarded.** `lock.acquire(blocking = False)` is called and ignored in `commonUmbrella`/`commonGuess`/`commonBet` and both Who Dis locks, then released in `finally`. When contended, the second caller proceeds *without* the lock and its `finally` releases the first caller's lock — so the stated invariants ("first to umbrella", "only one Who Dis at a time … ensures user pairings are unique") are not enforced, and `RuntimeError: release unlocked lock` can escape. These are `threading.Lock`s guarding `await`-containing critical sections on a single event loop. | `storms_cog.py:140,229,286`; `whodis_cog.py:135,283` |
| A-5 | **`/market` breaks permanently when a seller leaves.** `context.guild.get_member(...)` returns `None` for a departed/uncached member, and the next line reads `.name` → the whole command fails for everyone in that guild until the listing expires. | `gtrade_cog.py:448,452,456,460,464` |
| A-6 | **`/skip` reports the wrong error.** With nothing playing it replies "there is currently no Spotify activity to sync with" instead of "there is currently nothing playing." | `music_cog.py:387` |
| A-7 | **Who Dis pairings are matched by substring.** `getWhoDisGameKey` tests `str(userId) in gameKey` against `"<id>:<id>"`, and `guessWhoDis` validates the guess the same way — a shorter (older) Discord ID contained in a longer one collides. | `whodis_cog.py:439,502` |
| A-8 | **Crafting an item crashes on a content-less message.** `elif attachments != None` is true for the empty list, so `attachments[0]` raises `IndexError` on a sticker-only or embed-only reply. Should be `elif attachments:`. | `gtrade_cog.py:156` |
| A-9 | **Who Dis stays enabled when GCoin is disabled.** `toggle_who_dis` declares `toggle_gcoin` as a dependency, but GCoin's dependents list is `['toggle_gtrade', 'toggle_storms']` — Who Dis is missing, so disabling GCoin leaves it running without its dependency. | `config_cog.py:290` |
| A-10 | **Leaderboard rewards are credited off counterparty *names*.** `processTransactionForLeaderboardRewards` does `if "Storms" in other` / `if "Who Dis" in other`, where `other` is the other party's Discord username — a user named "Storms" credits storm rewards to whoever they transact with. (CLAUDE.md already flags this function as the one fragile memo-reading site.) | `leaderboards_queries.py:50-53` |

**Robustness / lifecycle**

| # | Finding | Location |
|---|---|---|
| A-11 | **Spotify sync sessions are never torn down.** `on_guild_remove` clears `musicStates` but not `spotifySyncSessions`; `spotify_sync` then calls `guild.get_member(userId)` → `None` → `AttributeError` **every second, forever**, logging on each tick. Same failure when the followed user simply leaves. This is the concrete form of the Workstream D "sync-loop lifecycle" question. | `music_cog.py:67,125` |
| A-12 | **Presence activity list grows on every reconnect.** `Presence.on_ready` appends 3 activities each time it fires, and `on_ready` re-fires on every gateway RESUME/READY — unbounded growth plus duplicate cycling on a long-running Pi process. Every other cog guards re-entry (`try: task.start() except RuntimeError`); this list does not. | `presence_cog.py:22-24` |
| A-13 | **Task loops mutate the dicts they iterate.** `storm_invoker`, `music_timeout` and `spotify_sync` iterate `self.<state>.items()` with `await`s inside, while `on_guild_remove`/`disconnectAndClearQueue` pop from those same dicts → `RuntimeError: dictionary changed size during iteration`, swallowed by the loops' broad `except Exception` (so a tick is silently lost). `who_dis_timeout` already does this correctly — it collects keys first, with a comment saying why. | `storms_cog.py:66`; `music_cog.py:100,118` |
| A-14 | **`on_guild_remove` pops without a default** in Storms and Music, raising `KeyError` for a guild that was never initialized (e.g. filtered out by `filterGuildsForInstance`). | `storms_cog.py:45-46`; `music_cog.py:67` |
| A-15 | **`finally` blocks reference possibly-unbound locals.** In `commonUmbrella`/`commonGuess`/`commonBet` a `KeyError` from `self.stormLocks[serverId]` leaves `lock`, `inConfiguredChannel` and `isConfigured` unbound, so the real failure is masked by `UnboundLocalError`. Same shape in `commonWhoDis` for `isPrivateMessage`/`deleteMsgs`. | `storms_cog.py:197-202`; `whodis_cog.py:206-212` |
| A-16 | **Two runtime-mutable properties are captured once and never re-read.** `Patreon.__init__` snapshots `utils.getGuildsForPatreonToIgnore()`, and `CustomButtonMenuPages.__init__` takes `USER_RESPONSE_TIMEOUT_SECONDS` as a **default argument** (bound at import). `setProperty` on either has no effect until restart, while the predicates read the same value live — so the cog and the predicates can disagree. Note `getGuildsForPatreonToIgnore()` also mutates the property list in place. | `patreon_cog.py:20`; `pagination.py:47`; `utils.py:127` |
| A-17 | **Hype match regexes are stored unvalidated.** `createMatch` never compiles the pattern, so an admin can save an invalid regex that then raises `re.error` on **every message** in that guild; `random.choice(responses)` is also evaluated before the match test and raises on an empty response list. User-supplied patterns are additionally a ReDoS/event-loop-stall vector. | `hype_cog.py:44-46`; `hype_queries.py:13` |
| A-18 | **`channelSync` indexes an empty queue.** Both branches fall through to `queue[0][1]` when elevator mode is on with an empty queue — reachable after a voice drop leaves `voiceClient` non-`None` but disconnected, which is exactly the state C-1 produces. | `music_cog.py:481,483` |
| A-19 | **Download thread outlives its `YoutubeDL`.** `Thread(target = ydl.download, ...)` is started inside `with YoutubeDL(...)`, so the context manager closes the instance while the thread is still using it. Fire-and-forget: no join, no error path. | `music_cog.py:468` |
| A-20 | **`after=` playback callback runs on the audio thread.** `playMusic` is re-entered from `voiceClient.play(..., after=lambda e: self.playMusic(serverId))`, mutating `musicStates` off the event loop, and the callback's error argument `e` is discarded — an ffmpeg failure silently advances the queue. | `music_cog.py:513,516` |
| A-21 | **Image content-type check rejects valid images.** `response.headers['content-type'] not in image_formats` fails on any header carrying parameters (`image/png; charset=utf-8`), and a missing header raises into the bare `except` → `False`. | `utils.py:90` |

**Systemic (architectural — feed Workstream E, and C for the music-specific ones)**

| # | Finding | Location |
|---|---|---|
| A-22 | **All Firebase I/O is synchronous and runs on the bot's event loop.** `firebase.py`'s five primitives block; `storm_invoker` alone can issue two RTDB round-trips per guild per second. The Quart API shares that loop, and `GBotFirebaseService.authenticate` blocks it further with a **synchronous** `httpx.post` to Google on every authenticated request. On the Pi this directly competes with the gateway heartbeat. | `firebase.py:32,37-55`; `api.py:37,49` |
| A-23 | **yt-dlp search runs on the event loop.** `searchYouTubeAndCacheDownload` is a blocking network+parse call awaited by nobody — the whole bot (gateway + API) stalls for the duration of every `/play`. The download is threaded; the *search* is not. | `music_cog.py:240,458` |
| A-24 | **Multi-step writes are not atomic.** `performTransaction` debits then credits as separate writes, and `completeTradeTransaction` chains money → pending-removal → item-create → item-delete. A failure mid-sequence loses or duplicates GCoin/items. Single-instance the sync I/O makes each call effectively uninterruptible, but `filterGuildsForInstance` means multiple instances can share one Firebase project — the read-modify-write race is real there. Ties into Workstream B. | `gcoin_queries.py:30-40`; `gtrade_cog.py:668` |
| A-25 | **14 live bare `except:` blocks swallow root causes**, several turning genuine failures into misleading user text or a blanket 400: `gcoin_cog.py:72` answers "please enter a valid amount" for *any* exception (including Firebase being down), and all five API resources abort 400 on internal errors that are really 500s. | `utils.py:29,94,183`; `firebase.py:34`; `gcoin_cog.py:72`; `storms_cog.py:486`; `patreon_cog.py:63`; `development_resource.py`, `discord_resource.py`, `storms_resource.py`, `leaderboards_resource.py` |
| A-26 | **Dead/misleading code.** `predicates.py:68` has a vestigial `if True:` wrapper (the branch it guards *is* meaningful — `LegacyPrefixCommandsNotEnabledForGuild` is deliberately unhandled in `main.py` so disabled-prefix guilds get silence — but the wrapper is not); `utils.sendMessageToAdmins` null-checks `channelId`/`channel` *after* already dereferencing them; `discord_resource.py:89` rebinds `value` from the parsed body to a field of itself; `main.py:104` logs "excuted". | see cells |

## Workstream B — Multi-instance story & sharding (DISCUSS FIRST — maintainer asked)

Primer for the discussion:
- **Sharding** (the Discord term) = ONE bot application splitting its gateway socket into N shard connections; every guild maps to exactly one shard (`guild_id >> 22 % N`). Discord mandates it at 2,500 guilds. nextcord support: `AutoShardedBot`. It is **not** load-balancing across replicas — you cannot run two copies of the same token for redundancy/throughput; each event belongs to exactly one shard, and duplicate full instances would double-fire every storm/message handler.
- **What GBot already has**: `utils.filterGuildsForInstance` — multiple bot *applications* (different tokens) sharing one Firebase, partitioned by which guilds each instance is in. That's the real multi-instance mechanism today.
- **Realistic goals**: (1) a persistent **test/dev instance** — a second Discord application + token in a private test guild, run from the dev compose (dev machine or Pi), optionally against a separate Firebase project or a namespaced DB root, enabling live debugging with zero prod risk; (2) `AutoShardedBot` only if guild count ever approaches thousands (not now).
- **Decisions to record here after discussion**: create the second Discord app? DB isolation (shared DB + disjoint guilds via `filterGuildsForInstance`, vs separate Firebase project)? where the test instance runs; whether legacy dev-attach flow (debugpy compose) stays the local debug path.

## Workstream C — Music (YouTube) architecture revisit

Current design: yt-dlp based, per-guild queues/state, cache with `MUSIC_CACHE_DELETION_TIMEOUT_MINUTES`. Known pain: yt-dlp breakage cadence (the Pi's last pre-modernization commit was literally "Fixing music bot - upgrading yt-dlp"), download-then-play latency, disk usage on the Pi. Explore: streaming vs download, cache keying/eviction, voice-reconnect robustness, search/queue UX, cross-server reuse of cached tracks, CPU/thermals on the Pi during playback. Output: an architecture note in this file, then incremental PRs.

**Also owned by this workstream, from the Workstream A read-through:** A-23 (yt-dlp search blocks the event loop — likely the single biggest playback-latency and Pi-stall cause), A-19 (download thread outlives its `YoutubeDL`), A-20 (`after=` callback mutates state off the event loop and discards the ffmpeg error), A-18 (`channelSync` indexes an empty queue in exactly the post-voice-drop state C-1 creates), A-6 (`/skip` wrong error text).

**Music bug ledger** — append findings here as they're observed in production; this workstream fixes them.

| # | Finding | Evidence | Severity |
|---|---|---|---|
| C-1 | **Voice-connect failure loop.** `nextcord.errors.ConnectionClosed: Shard ID None WebSocket closed with 4017` with `Failed to connect to voice... Retrying...`, repeating ~every 1–5s. Observed on the live Pi bot `2026-07-25 22:36` (outside Milestone 1's verification window, so *not* covered by that "0 tracebacks" record). Close code 4017 is an unknown/invalid opcode from the voice gateway — usually a nextcord-vs-voice-gateway version mismatch, not a network fault. Investigate whether the pinned nextcord version's voice implementation is current, and whether the retry loop is bounded (an unbounded loop burns CPU on the Pi and floods logs). | `docker logs GBot_7.0_prod` | correctness + Pi resource risk |

**How to check for recurrences on the Pi** (read-only; containers are maintainer-managed): scope errors to the current session rather than a time window, because the Pi's clock jumps at boot —
`docker logs GBot_7.0_prod 2>&1 | tac | awk '/GBot logged in as/{exit} {print}' | tac | grep -iE 'voice|4017|Traceback'`

## Workstream D — Spotify listening integration (new feature — define before building)

**⚠ Corrected 2026-07-26 — the presence-based tier ALREADY SHIPS.** This workstream was written as "new feature, define before building"; that premise was wrong. `music_cog.py` already has `/spotify <user>` (`strings.SPOTIFY_NAME`, cog line ~159), a `spotify_sync` `tasks.loop` (~line 116), per-guild `spotifySyncSessions` state, and `from nextcord import Spotify`. It reads a member's Discord Spotify activity and queues the matching track downloaded from YouTube, following the user as their activity changes. It is documented on the docs site (`docs/commands-music.md`). Found while auditing GBot-Docs for Plan 1 Milestone 2b.

So the real question is **not** "which tier to build first" but **"is the shipped presence-based feature good, and is the Web API tier worth adding?"** Re-scope as: (1) audit the existing `/spotify` implementation — sync-loop lifecycle across restarts, what happens when the followed user stops/switches, cleanup of `spotifySyncSessions` on `on_guild_remove`, and its share of the Workstream C yt-dlp/voice pain (see C-1); (2) only then evaluate **Spotify Web API** (per-user OAuth; playlists, top tracks, real "listen along") as a genuine tier-2 addition.

**Part of (1) is already answered.** The Workstream A read-through confirmed the lifecycle defect concretely: **A-11** — `on_guild_remove` clears `musicStates` but never `spotifySyncSessions`, so `spotify_sync` calls `guild.get_member(userId)` on a departed guild/user, gets `None`, and raises `AttributeError` **every second indefinitely**, logging each tick. Also relevant: **A-13** (the sync loop mutates the dict it iterates, silently losing ticks).

## Workstream E — Whole-bot design pass ("EVERYTHING")

Rolling per-area review, one area per change set: scheduled events (`tasks.loop` lifecycles, missed-run behavior across restarts), properties (typed/validated config; A-1/A-2 land here), logging (JSON formatter noise levels, per-cog verbosity), rules/config UX (`.toggle` discoverability), API resources parity with cog features, per-guild state lifecycle invariants (`on_ready`/`on_guild_join`/`on_guild_remove`), and writing down the implicit RTDB schema per queries file.

**Known gap for the "API resources parity" bullet — the docs site has a dead page.** `GBot-Docs/docs/activity.md` fetches `{{site.gbot_host}}/GBot/public/activity`, which returns **404**: GBot exposes exactly one public route, `/GBot/public/leaderboard/`, and `git log -S "public/activity" --all` shows the activity endpoint has **never existed in git history**. So that page shipped without its backend and has always been silently broken on the live site. Needs a decision: build a public activity endpoint, or delete the page from GBot-Docs. (The leaderboard pages are fine — they fetch without a trailing slash and get a 308 redirect, which `fetch` follows.) Found during the Plan 1 Milestone 2b docs audit, 2026-07-26.

**Moved out:** *message/embed consistency* and *user-facing error messages* were originally bullets here. The 2026-07-26 survey found 166 plain-text send sites across 8 live cogs — far too large for a rolling bullet — so they are now [presentation-and-ux-consistency.md](presentation-and-ux-consistency.md) (Plan 3), which also carries the ephemeral-reply and `defer()`-coverage defects it uncovered.

## Workstream F — Discord App Directory / marketability (north star, continuous)

Not a build-now item; acceptance criteria the other workstreams should not violate: bot verification readiness (required at scale), **slash-first UX** — the App Directory disfavors Message-Content-intent dependence, and legacy prefix commands depend on it (the dual-command pattern already gives full slash coverage; a future per-guild prefix retirement would revisit that accepted trade-off), privacy policy + terms of service documents, a support server, and eventually App Subscriptions/SKUs for monetization. Any new feature (C/D) ships slash-first.

## Suggested order & status

Original order: B discussion + A seeds → C (most user-visible pain) → D → E rolling → F as continuous criteria.

**Revised after the A sweep (2026-07-26):** the ledger's *correctness — user-visible* group (A-1…A-10) should land as its own change set **before** C. A-1 alone means every DM command from a paying subscriber is refused, and A-2/A-3/A-5 are each small, independent, and testable. C then absorbs A-18…A-20 and A-23 as part of the architecture note rather than as separate fixes. B is still the only maintainer-blocked item, and A-24 gives that discussion a concrete stake (cross-instance read-modify-write on shared Firebase).

| Item | Status |
|---|---|
| A — bug sweep (seeds 1–3, then ledger) | **done 2026-07-26** — seeds fixed; 26-entry ledger above is the output |
| B — multi-instance/sharding decisions | **blocked on maintainer discussion** |
| C — music architecture note + PRs | pending |
| D — Spotify tier decision + presence-based v1 | pending |
| E — per-area passes | pending |
| F — directory-readiness criteria | continuous |
