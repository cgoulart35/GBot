# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Active effort (remove this section when `modernization-2026` merges)

`plans/modernization-2026-roadmap.md` is the master plan for the `modernization-2026` branch — six phases porting the HalloweenEvent 2026 playbook (Python 3.13, firebase-admin, CI/CD to a Raspberry Pi, Claude review + skills, hardening). Any request like "start/continue phase N" means: read that file, run its pre-flight, execute the first non-done phase only. The other files in `plans/` are complete or superseded — the roadmap says which. Local dev machine runs Podman: `podman machine start`, then `podman compose -f <file> ...` wherever docs say `docker-compose`.

## Project

GBot is a Dockerized Python Discord bot (built on `nextcord`, not discord.py) backed by Google Firebase Realtime Database. It also exposes an in-process Quart HTTPS API for management/automation. Features are grouped into cogs: Config, GCoin, GTrade, Hype, Music, Patreon, Presence, Storms, Who Dis. Halo features are deliberately discontinued but kept commented in-place (see "Halo" note below).

## Run / build

Bot only runs inside Docker. The Dockerfile generates self-signed TLS certs (`/GBot/server.{crt,key}`) at build time — the Quart API will not start without them, so you cannot meaningfully run `main.py` outside the container.

- Dev (waits for debugpy attach on host port 5677, API on 5003): `docker-compose -f docker-compose-dev.yml up -d --build`
- Prod (debugpy on 5678, API on 5004): `docker-compose -f docker-compose-prod.yml up -d --build`
- Both target stages share a `stage` base in `Dockerfile`; the only difference is whether the entrypoint waits for a debugger.

Before either works, populate `Shared/gbot.env` (Discord token, Firebase JSON, Patreon IDs, timeouts) and drop `Shared/serviceAccountKey.json` next to it. README §"Setup Guide" enumerates every env var.

## Tests

`unittest.TestCase` suites run by **pytest** (the standardized runner — it collects them natively; `pytest.ini` keeps the archived Halo suites ignored, mirroring `test.py`'s `# DISCONTINUED` imports). Tests live in `GBotDiscord/test/<cog>/<cog>_test.py` and heavily mock `GBotFirebaseService` static methods. **Always run from the repo root** so the `GBotDiscord.src...` / `GBotDiscord.test...` package imports resolve.

The canonical way to run tests is `scripts/test.sh` — it builds the test image via `docker-compose-test.yml` (`stage` target: runtime deps only, no entrypoint), mounts the repo at `/GBot`, installs `requirements-dev.txt` ad hoc (pytest/coverage/pip-audit are dev-only, never in the runtime image), and runs `python -m pytest -q`. `scripts/test.sh audit` runs pip-audit over `requirements.txt` instead. No `Shared/gbot.env` or `serviceAccountKey.json` required because tests mock Firebase and Discord.

- Manual image build: `docker-compose -f docker-compose-test.yml build` (re-run only when `requirements.txt` changes; the wrapper does this every run).
- Manual all-suites run: `docker-compose -f docker-compose-test.yml run --rm --entrypoint sh gbot-test -c "pip install -r requirements-dev.txt -q && python -m pytest -q"`
- Single cog: `docker-compose -f docker-compose-test.yml run --rm gbot-test -m unittest GBotDiscord/test/<cog>/<cog>_test.py`
- Legacy entry point: `docker-compose -f docker-compose-test.yml run --rm gbot-test GBotDiscord/test/test.py` — still supported as the local/VS Code path; `sys.exit(0 if result.wasSuccessful() else 1)` keeps its exit code CI-safe. New test modules must be wired into both pytest discovery (automatic via `<x>_test.py` naming) and `test.py`'s suite list.
- Volume mount means host edits are picked up without rebuild.
- Local alternative: the VS Code "Python: Current File" launch config still works — it sets `PYTHONPATH=${cwd}` which is required.
- CI: `.github/workflows/ci.yml` runs the same pytest suite plus `pip-audit -r requirements.txt` on every PR and every push to `develop` — Python 3.13 straight on the runner, no Docker, no system packages (tests mock Firebase/Discord). Dependabot is security-updates-only via repo settings; there is no version-update config.

## Architecture

### Composition
`GBotDiscord/src/main.py` is the entrypoint and does, in order: init logger → `GBotPropertiesManager.startPropertyManager()` → `GBotFirebaseService.startFirebaseScheduler()` → instantiate the `commands.Bot` → `load_extension('<cog>.<cog>_cog')` for each feature → register error/completion event handlers → `GBotAPIService.registerAPI(client)` → `discordClient.run(...)`. The Quart app is started as a task on the bot's asyncio loop (`gbotClient.loop.create_task(app.run_task(...))`), so the API shares the event loop with the Discord client.

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
`GBotPropertiesManager` (`properties.py`) is a class-level singleton holding env config. `startPropertyManager()` loads everything; `determineValue` coerces ints and splittable int lists. A subset is **mutable at runtime** via the `setProperty` API action — see the if/elif chain in `setProperty`. Properties not listed there (e.g., `DISCORD_TOKEN`, `API_PORT`) are intentionally immutable. When adding a property: declare class attribute → load in `startPropertyManager` → optionally add to `INT_PROPERTIES`/`SPLITTABLE_INT_PROPERTIES` → optionally add to `setProperty`.

### Quart API
Routes are declared in `quart_api/api.py` and forward to `*Resource` classes that own `doc()` (returns the schema) and `post()`. All `/GBot/private/*` routes use HTTP basic auth verified against Firebase Auth (`GBotFirebaseService.authenticate`). `/GBot/public/leaderboard/` is unauthenticated. Self-signed certs are baked into the image; `cors(app, allow_origin="*")` is intentional for the public leaderboard endpoint.

The `Development` resource is the operational lever for the deployed bot — `rebuildLatest` calls out to a separate `GIT_UPDATER_HOST` service (not in this repo) to redeploy from main; `setProperty` mutates `GBotPropertiesManager`; `syncSubscribers` triggers `Patreon.patreon_validation()` immediately instead of waiting for the 24h task.

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
