# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Active effort (remove this section when both post-modernization plans are done)

`plans/` is split by whether a plan still has work in it — **`plans/active/`** (unfinished) and **`plans/completed/`** (done or superseded, kept for their recon notes, decisions and recorded traps). [`plans/README.md`](plans/README.md) indexes both; keep it current when a plan changes state, and move the file rather than leaving a stale one behind.

`modernization-2026` is complete (all six phases of `plans/completed/modernization-2026-roadmap.md`; merged to `develop` 2026-07-25), as is Post-modernization Plan 1 (`plans/completed/pi-deployment-and-updater-retirement.md`, **2026-07-26** — bot live on the Pi via image-based CD, GitProjectUpdateHandler retired across all three repos). The active follow-on plans, in order:

1. `plans/active/feature-modernization-roadmap.md` — missed-bug sweep, multi-instance/sharding decision (maintainer discussion first), music + Spotify + whole-bot feature passes, App-Directory north star. **In progress** — Workstream C is up to C-PR5.
2. `plans/active/presentation-and-ux-consistency.md` — make everything the user sees consistent (166 plain-text send sites, no embeds, zero ephemeral replies). Phase 0 is a maintainer design gate.

**These plan files are in a public repo** — keep Pi/ops specifics at the level already there (paths and the SSH alias are fine); never record credential locations, host-access mechanics, or anything that would help someone reach the deployment. Report those to the maintainer in conversation instead.

Any request like "start/continue plan N" (or "the next plan") means: read that file, run its pre-flight, execute the first non-done milestone only. Local dev machine runs Podman: `podman machine start`, then `podman compose -f <file> ...` wherever docs say `docker-compose`.

## Project

GBot is a Dockerized Python Discord bot (built on `nextcord`, not discord.py) backed by Google Firebase Realtime Database. It also exposes an in-process Quart HTTPS API for management/automation. Features are grouped into cogs: Config, GCoin, GTrade, Hype, Music, Patreon, Presence, Storms, Who Dis. Halo features are deliberately discontinued but kept commented in-place (see "Halo" note below).

## Run / build

Bot only runs inside Docker. The Dockerfile generates self-signed TLS certs (`/GBot/server.{crt,key}`) at build time — the Quart API will not start without them, so you cannot meaningfully run `main.py` outside the container.

- Dev (waits for debugpy attach on host port 5677, API on 5003): `docker-compose -f docker-compose-dev.yml up -d --build`
- Prod (no debugger, API on 5004): `docker-compose -f docker-compose-prod.yml up -d --build`
- Both target stages share a `stage` base in `Dockerfile`; dev's entrypoint waits for a debugpy attach, prod runs `main.py` directly (no debugpy, no debug port — hardened in Phase 6).
- `docker-compose-prod.yml` names the published image (`ghcr.io/cgoulart35/gbot:${IMAGE_TAG:-latest}`): with `--build` it builds that tag locally, plain `up -d` pulls from GHCR. Production deployment is image-based CD — CI's `publish` job ships an arm64 image on every code push to `develop`, and `scripts/deploy-watcher.sh` on the Pi redeploys via `scripts/deploy.sh` (see README §Deployment).

Before either works, populate `Shared/gbot.env` (Discord token, Firebase JSON, Patreon IDs, timeouts) and drop `Shared/serviceAccountKey.json` next to it. README §"Setup Guide" enumerates every env var.

## Tests

`unittest.TestCase` suites run by **pytest** (the standardized runner — it collects them natively; `pytest.ini` keeps the archived Halo suites ignored, mirroring `test.py`'s `# DISCONTINUED` imports). Tests live in `GBotDiscord/test/<cog>/<cog>_test.py` and heavily mock `GBotFirebaseService` static methods. **Always run from the repo root** so the `GBotDiscord.src...` / `GBotDiscord.test...` package imports resolve.

The canonical way to run tests is `scripts/test.sh` — it builds the test image via `docker-compose-test.yml` (`stage` target: runtime deps only, no entrypoint), mounts the repo at `/GBot`, installs `requirements-dev.txt` ad hoc (pytest/coverage/pip-audit are dev-only, never in the runtime image), and runs `python -m pytest -q`; extra args pass through to pytest (`scripts/test.sh -k storm`, or a test path for one cog's suite). `scripts/test.sh audit` runs pip-audit over `requirements.txt` instead; `scripts/test.sh coverage` runs the suite under coverage and prints the 100%-gate report. No `Shared/gbot.env` or `serviceAccountKey.json` required because tests mock Firebase and Discord.

- Manual image build: `docker-compose -f docker-compose-test.yml build` (re-run only when `requirements.txt` changes; the wrapper does this every run).
- Manual all-suites run: `docker-compose -f docker-compose-test.yml run --rm --entrypoint sh gbot-test -c "pip install -r requirements-dev.txt -q && python -m pytest -q"`
- Single cog: `docker-compose -f docker-compose-test.yml run --rm gbot-test -m unittest GBotDiscord/test/<cog>/<cog>_test.py`
- Legacy entry point: `docker-compose -f docker-compose-test.yml run --rm gbot-test GBotDiscord/test/test.py` — still supported as the local/VS Code path; `sys.exit(0 if result.wasSuccessful() else 1)` keeps its exit code CI-safe. New test modules must be wired into both pytest discovery (automatic via `<x>_test.py` naming) and `test.py`'s suite list.
- Volume mount means host edits are picked up without rebuild. It also carries the host's `__pycache__`, which would let cached bytecode suppress compile-time diagnostics (`SyntaxWarning` etc.) that a fresh CI checkout still reports — `docker-compose-test.yml` sets `PYTHONPYCACHEPREFIX=/tmp/pycache` so in-image runs and CI report identically. Don't remove it.
- Local alternative: the VS Code "Python: Current File" launch config still works — it sets `PYTHONPATH=${cwd}` which is required.
- CI: `.github/workflows/ci.yml` runs the same pytest suite plus `pip-audit -r requirements.txt` on every PR and every push to `develop` — Python 3.13 straight on the runner, no Docker, no system packages (tests mock Firebase/Discord). Code pushes to `develop` additionally run the `publish` job (native-arm64 runner) that pushes `ghcr.io/cgoulart35/gbot:latest` + `:<short-sha>`; doc/CI-only pushes are skipped via the `changes` job. Dependabot is security-updates-only via repo settings; there is no version-update config.
- **yt-dlp bumps:** `.github/workflows/yt-dlp-bump.yml` runs monthly (plus `workflow_dispatch` — fire it the moment music breaks), resolves the latest **stable** from PyPI (`.info.version`, which excludes the near-daily `.dev0` nightlies), rewrites the pin, verifies it by running the suite + `pip-audit` against it, and opens a PR carrying that verdict. Monthly rather than weekly because bumps are one-line and accrue no refactor debt — `2025.2.19` → `2026.7.4` skipped ~30 releases and touched no Python. Dependabot can't cover this: `allow: [dependency-name: yt-dlp]` would scope **security** updates to yt-dlp too, and omitting `allow` floods every pip pin.

## Architecture

### Composition
`GBotDiscord/src/main.py` is the entrypoint and does, in order: init logger → `GBotPropertiesManager.startPropertyManager()` → `GBotFirebaseService.startFirebaseScheduler()` → `applyDavePrepareEpochPatch()` → instantiate the `commands.Bot` → `load_extension('<cog>.<cog>_cog')` for each feature → register error/completion event handlers → `GBotAPIService.registerAPI(client)` → `discordClient.run(...)`. The Quart app is started as a task on the bot's asyncio loop (`gbotClient.loop.create_task(app.run_task(...))`), so the API shares the event loop with the Discord client.

`dave_patch.py` is the one place GBot patches a third-party library: nextcord never dispatches voice opcode 24 (`DAVE_PREPARE_EPOCH`), so the bot never rejoins the MLS group when a voice channel goes solo → group and its audio becomes undecryptable (ledger C-13). It has a defined removal condition — `dave_patch_test.py`'s canary test fails the day nextcord dispatches the opcode itself, and the module goes with it. Don't add unrelated library patches here; this one exists because the alternative was a dead feature.

### Per-feature layout
Each feature has its own package `GBotDiscord/src/<feature>/` containing:
- `<feature>_cog.py` — the `commands.Cog` subclass (commands, listeners, `tasks.loop` background loops, in-memory per-guild state).
- `<feature>_queries.py` — thin functions wrapping `GBotFirebaseService` calls; the schema is documented as a comment block at the top of each queries file (e.g., `gcoin_queries.py` describes `gcoin/<userId>/{balance,history,username}`).

Cross-feature talk happens via `client.get_cog('<Name>')` (e.g., `discord_resource.py` reaches into `Patreon` and `Presence`); the storm/whodis resources do the same with `Storms`.

### Dual-mode commands (slash + legacy prefix)
Every user-facing command exists twice: a `@nextcord.slash_command(...)` method and a `@commands.command(...)` method. Both delegate to a shared `commonX(self, context, ...)` coroutine that accepts either `nextcord.Interaction` or `Context`. When adding new commands, follow this exact pattern — it's load-bearing for the `.toggle legacy_prefix_commands` feature.

Decorator order matters and is mirrored from `predicates.py`. Predicates take a positional `isSlashCommand` boolean; pass `True` on the slash variant so the predicate uses `application_checks.check` instead of `commands.check`. Slash variants also pass `guild_ids = GBotPropertiesManager.SLASH_COMMAND_TEST_GUILDS` so the env var can scope registration during development (empty list = global).

Typical predicate stack (order matters because errors surface the *first* failing check):
- Slash: `isGuildOrUserSubscribed(True)` → `isMessageSentInGuild(True)` → feature-specific checks.
- Prefix: feature-specific checks → `isFeatureEnabledForServer('toggle_legacy_prefix_commands', False)` → `isMessageSentInGuild()` → `isGuildOrUserSubscribed()`.

### Persistence (Firebase RTDB)
All DB I/O goes through `GBotFirebaseService` (`firebase.py`) — never call `firebase_admin` directly. The five primitives are `get/set/push/update/remove`, each taking a list of child keys (`["servers", serverId, "prefix"]`); `get` returns a small adapter object exposing `.val()` (pyrebase's old contract, kept so query call sites never changed). The service account key (`Shared/serviceAccountKey.json`) is the database credential; `authenticate` verifies API basic-auth logins against the Identity Toolkit REST API using the `apiKey` from `FIREBASE_CONFIG_JSON`. Tests mock these as `MagicMock`/`AsyncMock` on the class.

Schema is implicit — there's no migration framework. Two patterns are used:
1. **Lazy upgrade per server**: `config_queries.upgradeServerValues` runs on `on_ready` for every server and back-fills new top-level fields with defaults. When you add a server-config flag, add a check here.
2. **One-shot patch via API**: heavier schema changes live in `quart_api/development_queries.py` and are triggered manually by POSTing `{"action":{"name":"runDatabasePatch","patch":"<id>"}}` to `/GBot/private/development/`. Wire the patch name into the `if patch == ...` chain in `development_resource.py`.

`leaderboards` is a denormalized aggregate table. It's updated from two places: balance changes via `gcoin_queries.setUserBalance` and event counters via cogs calling `leaderboards_queries.incrementUserNumValue`. Keep these decoupled from the GCoin transaction primitives — `processTransactionForLeaderboardRewards` is the only call site that reads transaction memo strings ("Storms", "Who Dis", "x10", etc.) to credit aggregate stats.

### Configuration & runtime mutation
`GBotPropertiesManager` (`properties.py`) is a class-level singleton holding env config. `startPropertyManager()` loads everything; `determineValue` is the **single coercion point** — it handles ints, splittable int lists and `LOG_LEVEL`, and both env strings *and* already-typed API payloads pass through it. Defaults are coerced too (an omitted int property must not land as its string default). A subset is **mutable at runtime** via the `setProperty` API action — see the `MUTABLE_PROPERTIES` allowlist; anything not on it (e.g., `DISCORD_TOKEN`, `API_PORT`) is intentionally immutable and `setProperty` returns `False`. A mutable property given an uncoercible value raises `PropertyValueInvalid`, which `development_resource` turns into a failure response. When adding a property: declare class attribute → load in `startPropertyManager` → optionally add to `INT_PROPERTIES`/`SPLITTABLE_INT_PROPERTIES` → optionally add to `MUTABLE_PROPERTIES`.

### Quart API
Routes are declared in `quart_api/api.py` and forward to `*Resource` classes that own `doc()` (returns the schema) and `post()`. All `/GBot/private/*` routes use HTTP basic auth verified against Firebase Auth (`GBotFirebaseService.authenticate`). `/GBot/public/leaderboard/` is unauthenticated. Self-signed certs are baked into the image; `cors(app, allow_origin="*")` is intentional for the public leaderboard endpoint.

The `Development` resource is the operational lever for the deployed bot — `runDatabasePatch` applies a one-shot schema patch; `setProperty` mutates `GBotPropertiesManager`; `syncSubscribers` triggers `Patreon.patreon_validation()` immediately instead of waiting for the 24h task. Redeploys are **not** an API concern: they go through image-based CD (see README §Deployment).

### Patreon subscription gating
`isGuildOrUserSubscribed` is applied to nearly every user-facing command. It checks the `patreon_members` Firebase table (populated by the `/patreon` slash command from inside the configured Patreon Discord server) and lets the command through if the calling guild is subscribed *or* the user shares a subscribed guild (for private-message commands).

`PATREON_IGNORE_GUILDS` bypasses the check — `utils.getGuildsForPatreonToIgnore()` always appends `PATREON_GUILD_ID` to that list, so the Patreon coordination server itself is implicitly ignored. The `Patreon.patreon_validation` task (24h loop) also force-leaves any guild that isn't subscribed and isn't in the ignore list.

### Per-guild in-memory state
`Storms`, `Music`, `WhoDis` keep state in instance dicts keyed by `str(guildId)`. The lifecycle is: `on_ready` initializes state for every guild returned by `utils.filterGuildsForInstance` (which intersects DB-tracked guilds with `client.guilds` — important if you ever run multiple bot instances against the same Firebase project); `on_guild_join` initializes for new joins; `on_guild_remove` tears down. When adding new per-guild stateful behavior, wire all three listeners.

### Logging
`CustomFormatter` in `main.py` emits JSON-formatted lines and escapes backslashes/quotes before `super().format()`. Don't `print()` — use `self.logger` / `logging.getLogger()` so the output stays parseable. Logs go to both `Logs/GBotDiscord.log` and stdout.

## Conventions worth knowing

- Imports always use the full package path: `from GBotDiscord.src.<feature> import <queries>`. Relative imports break the test harness.
- Files use `#region IMPORTS` / `#endregion` banners; keep them when editing.
- Halo features (Halo Infinite API integration, two API resources, an entire cog) are kept in-tree but commented out with `# DISCONTINUED` markers throughout `main.py`, `api.py`, `test.py`, several cogs, and `config_queries.py`. Leave them alone — they're not dead code to clean up, they're an archived feature.
- Money values are `Decimal`, always rounded with `utils.roundDecimalPlaces(value, places)` (uses `ROUND_HALF_UP`) before display or persistence as a string.
- GCoin transactions go through `gcoin_queries.performTransaction` — it enforces the invariants in `exceptions.py` (`EnforceRealUsersError`, `EnforceSenderFundsError`, etc.). Don't bypass it by calling `setUserBalance` directly for transfers.

## Upstream issues we carry patches for

Third-party defects GBot works around in-tree. Each entry must name the upstream report, the workaround, and **how we find out it's fixed** — the point of this register is that the patch gets *deleted*, not inherited forever. **Append a row whenever a new workaround lands, and delete the row when the workaround goes.** Don't add a patch here without a removal condition.

| Upstream | Defect | Our workaround | Removal condition |
|---|---|---|---|
| nextcord [#1294](https://github.com/nextcord/nextcord/issues/1294) (reported 2026-08-01, affects 3.2.0 and `master`) | Voice opcode 24 `DAVE_PREPARE_EPOCH` is declared and its handler implemented, but never dispatched — so the bot never rejoins the MLS group when a voice channel goes solo → group, and its audio is undecryptable for the rest of the session while it reports "playing" (ledger C-13). | `GBotDiscord/src/dave_patch.py` wraps `DiscordVoiceWebSocket.received_message` at startup and dispatches the opcode into nextcord's own handler. Applied from `main.py`. | `dave_patch_test.py::test_nextcord_still_does_not_dispatch_prepare_epoch` asserts the *unpatched* library still ignores opcode 24, so it **fails the moment a nextcord bump includes the fix** — which is exactly when it matters, since `requirements.txt` pins the version. Its failure message names everything to delete: the module, its `main.py` call, that suite, and this row. |

## Skills (`/commands`)

Repo skills live in `.claude/skills/<name>/SKILL.md` (tracked in git) and are invokable as `/<name>`; all are also auto-invokable (Claude loads one when a request matches its `description`). They wrap the deterministic `scripts/` wrappers or the documented compose commands with the right flags, safety rails, and verification — prefer them over hand-deriving commands; **`/implement-dev-changes`** composes them into a full dev-change flow:

- **`/test [pytest-args | coverage | audit]`** — run the suite / the 100%-coverage gate / pip-audit the ephemeral-container way (wraps `scripts/test.sh`; the `gbot-test` image never touches `:latest`, so runs are invisible to the Pi's deploy watcher).
- **`/qa [up|logs|ps|down]`** — manual QA by **live-instance swap** (wraps `scripts/qa.sh`): builds the working tree as `:qa` (watcher-invisible) and runs the REAL bot — real Discord token, real Firebase — so the maintainer must stop the Pi instance first (never two instances at once). Human-gated via `QA_CONFIRM=yes`.
- **`/prod-up`** / **`/prod-down`** / **`/prod-logs [N]`** — start / stop / inspect the prod container (`GBot_7.0_prod`) from the published GHCR image. `/prod-logs` is read-only; on the Pi, container start/stop is maintainer-run.
- **`/implement-dev-changes`** — the end-to-end dev-flow **orchestrator**: explore → plan → branch → implement (+tests) → `/test` (+ `coverage` when `GBotDiscord/src` changed) → optional `/qa` → commit → push → PR → review loop → pre-deploy checks → **merge (only on explicit OK)** → verify publish + Pi deploy. Pauses at every human gate; never merges/pushes/deploys unprompted.

## PR auto-review & accepted trade-offs

- **PR review (CI):** `.github/workflows/claude-review.yml` runs Claude (`anthropics/claude-code-action@v1`) on every non-draft PR (drafts get reviewed once marked ready), posting inline findings and a short summary comment; authed by the `CLAUDE_CODE_OAUTH_TOKEN` repo secret (a Claude subscription token, not API billing). Comments only — never approves or blocks. The action's **backend** validates the workflow against the **default branch** (`develop`): on any PR whose `claude-review.yml` differs from — or doesn't yet exist on — `develop`, the review job **skips gracefully** (green check + a "Skipping action due to workflow validation" warning; not a GitHub-side rule, and older action versions hard-failed with `401 Workflow validation failed` instead). So merge workflow changes on their own first — reviews only run once the file is on `develop`.
- **Review scope — accepted trade-offs (the auto-reviewer must NOT re-flag these):** Halo features commented in place with `# DISCONTINUED` markers (archived, not dead code); self-signed TLS certs baked into the image for the Quart API; `cors(app, allow_origin="*")` on the public leaderboard; the dual slash/prefix command duplication (load-bearing for `.toggle legacy_prefix_commands`); the implicit RTDB schema (lazy `upgradeServerValues` + one-shot API patches, no migration framework); camelCase Python names; mutable GitHub Action version tags (`@vN` rather than SHA-pinned — so upstream fixes are picked up automatically); the review job skipping itself on workflow-editing PRs (the workflow-validation guard — see above); and the yt-dlp bump PRs carrying **no CI checks and no Claude review** — they are opened by `GITHUB_TOKEN`, for which GitHub raises no workflow events, so `yt-dlp-bump.yml` self-verifies in-job instead (and "Allow GitHub Actions to create and approve pull requests" is deliberately enabled to permit it). These are settled; a review that raises them is noise, not a finding. **Append a line here whenever a future review flags something we decide to accept** — this list is how the reviewer "learns" what to ignore (the prompt in `claude-review.yml` points at it).
