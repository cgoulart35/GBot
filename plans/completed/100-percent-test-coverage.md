# GBot — 100% Test Coverage Plan

This document drives a series of `/plan` sessions whose collective goal is to drive `GBotDiscord/src/**` to 100% line + branch coverage under `coverage.py`. Work through the **Sessions** list top-to-bottom — each session is sized to fit one `/plan` + implement cycle.

The repo's testing conventions are non-obvious; **every session must adhere to the [Ground rules](#ground-rules)** to avoid rediscovering them.

---

## How to use this plan across multiple `/clear`-d sessions

This file is the **single source of truth** for which sessions are done and what coverage % we're at. After `/clear`, a fresh Claude has no memory of prior progress — it picks up by reading this file.

**Each new `/plan` session does the following:**

1. Read this file top-to-bottom. Find the first unchecked box in [Progress tracker](#progress-tracker) below — that is the session to work on.
2. Read the matching `## Session N — ...` section for the goal, files, and cases.
3. Re-read the [Ground rules](#ground-rules) section. The repo conventions (Docker-only tests, query-module reassignment mocking, slash + prefix duality, the pagination try/except pattern) are not obvious from the code and trip up every fresh session.
4. Plan + implement that session's work only. **Do not stack multiple sessions into one plan** — they were sized intentionally.
5. Before declaring done: run `docker-compose -f docker-compose-test.yml run --rm gbot-test -m coverage run GBotDiscord/test/test.py && docker-compose -f docker-compose-test.yml run --rm gbot-test -m coverage report` and record the new total coverage %.
6. **Update this file in the same commit**: tick the session's checkbox in [Progress tracker](#progress-tracker) and fill in the **New coverage** column.
7. Commit message format: `Test coverage Session N: <one-line summary> (coverage: XX% → YY%)`.

If a session uncovers work that doesn't fit (e.g., a needed refactor, a bug, a new TODO surfaced), **append a follow-up bullet under the session heading** rather than expanding scope mid-flight. Future sessions can pick those up.

---

## Progress tracker

Tick boxes left-to-right as sessions complete. The "New coverage" column is the post-session `coverage report` total — fill it in from the run in step 5 above. "Baseline" goes in Session 0's row once measured.

| Done | Session | New coverage |
|:---:|---|:---:|
| [x] | 0 — Coverage tooling & baseline | _baseline:_ 72% |
| [x] | 1 — `utils.py` | 76% |
| [x] | 2 — `properties.py` | 79% |
| [x] | 3 — `firebase.py` + `leaderboards_queries.py` | 80% |
| [x] | 4 — `pagination.py` | 81% |
| [x] | 5 — `predicates.py` | 83% |
| [x] | 6 — `presence/presence_cog.py` | 84% |
| [x] | 7 — Quart resource stubs (`development`, `discord`, `storms`, `leaderboard`) | 90% |
| [x] | 8 — `quart_api/api.py` | 92% |
| [x] | 9 — `quart_api/development_queries.py` | 93% |
| [x] | 10 — `patreon/patreon_cog.py` gap-fill + `patreon_queries.py` | 94% |
| [x] | 11 — `hype/hype_cog.py` `unmatch`/`unmatchSlash` pagination tests | 95% |
| [x] | 12 — `gtrade/gtrade_queries.py` + `gtrade_cog.py` gap-fill | 98% |
| [x] | 13 — `gcoin/gcoin_queries.py` | 98% |
| [ ] | 14 — `main.py` error & completion handlers (optional) | _skipped_ |
| [x] | 15 — Gap-fill remaining cogs (`music`, `whodis`, `storms`, `config`, `gcoin`) | **100%** |

---

## Coverage target & exclusions

"100% coverage" means **100% of `GBotDiscord/src/**` excluding the lines and files listed below.** These exclusions are intentional and should be encoded in `.coveragerc`:

| Excluded | Reason |
|---|---|
| `GBotDiscord/src/main.py` | Module-level boot script (logging setup, `discordClient.run(...)`, extension loading). Side-effecting on import — covering it means executing the bot. The error/completion handlers defined here are testable, so factor them out (see [Session 14](#session-14--maingitpy-error--completion-handlers)) if 100% is required. |
| `GBotDiscord/src/halo/**` and `GBotDiscord/src/quart_api/halo_resource.py` | Discontinued feature — kept in-tree as archived code per CLAUDE.md. Do NOT write tests for these; do exclude them from coverage. |
| `GBotDiscord/src/**/__init__.py` (all empty) | No executable code. |
| `GBotDiscord/src/strings.py` | Module-level string constants only; no behavior. |
| `GBotDiscord/src/exceptions.py` | All classes are `pass` bodies that inherit from `Exception` / `commands.CheckFailure` / `commands.CommandError`. Only `CustomCommandOnCooldown.__init__` has logic — that single class can be covered by a 3-line test, or excluded with a `# pragma: no cover` if not worth it. |

Anything else under `GBotDiscord/src/**` is in scope.

`# pragma: no cover` is acceptable for genuinely unreachable branches (e.g., the `except` block around `await app.run_task(...)` if it ever appears), but every use must be justified in the PR.

---

## Ground rules

Encode these in the prompt to every `/plan` session — they are repo conventions not derivable from a quick read.

1. **Always run tests in Docker via `docker-compose-test.yml`.** Tests resolve imports as `GBotDiscord.src.<feature>...` and the compose file sets `PYTHONPATH=/GBot`. Running outside Docker requires `PYTHONPATH=${cwd}`; the VS Code "Python: Current File" config sets that, nothing else.
   - All suites: `docker-compose -f docker-compose-test.yml run --rm gbot-test GBotDiscord/test/test.py`
   - One file: `docker-compose -f docker-compose-test.yml run --rm gbot-test -m unittest GBotDiscord/test/<cog>/<cog>_test.py`
2. **Tests mock Firebase, not real DB.** Stub the five `GBotFirebaseService` primitives (`get/set/push/update/remove`) as `MagicMock`s in each test. The `get` primitive returns a value with a `.val()` method — use `result = Mock(); result.val.return_value = ...` when needed. Never set up real Firebase credentials for tests.
3. **Cogs are constructed with a real `commands.Bot()` client.** Do not mock `nextcord.Client` at the cog level — `Bot()` instantiates cleanly without a token. See `gcoin_test.setUp` for the canonical pattern.
4. **Mock `*_queries` module functions by reassignment, not by `patch`.** The codebase relies on Python's lookup of module-level names; tests do e.g. `gcoin_queries.getUserBalance = MagicMock(return_value=...)`. This persists across tests in the same suite — re-stub in each `setUp`/test as needed.
5. **Slash + prefix duality must both be tested.** Every user-facing command has a slash variant and a legacy prefix variant; they delegate to a shared `commonX(...)` helper. Cover the common helper plus at least one happy-path call from each variant (the variants differ in how they pass `interaction.user` vs `ctx.author`, and slash variants may call `interaction.response.defer()`).
6. **`pagination.FieldPageSource.__init__` is mocked with `return_value=None` and wrapped in a `try/except`** in tests that exercise the pagination path — see `gcoin_test.test_wallets_with_balances`. The cog code calls `pages.start(context)` which raises because `__init__` was short-circuited; the `except` block then asserts on the constructor args. This is intentional and load-bearing — there's a TODO in `hype_test.py` to find a cleaner approach, but until that's solved, follow the same pattern.
7. **Use `GBotDiscord/test/utils.py` helpers.** `AsyncIter` wraps a list for `async for` (e.g., `guild.fetch_members().return_value = AsyncIter([user1, user2])`). `SideEffectBuilder` maps an arg-index to a return-value dict for `side_effect`. Don't reimplement these.
8. **Decimal precision matters.** GCoin/leaderboard values are `Decimal`, rounded via `utils.roundDecimalPlaces(value, places)` (`ROUND_HALF_UP`). When asserting on stored values, the expectation is the rounded string (e.g., `"21.00"`, not `"21.0"` or `Decimal("21")`).
9. **Register every new `Test<Cog>` class in `GBotDiscord/test/test.py`.** Both an import line and an `unittest.TestLoader().loadTestsFromTestCase(...)` line, and add it to the `allTestsSuite` list. The all-tests run is the CI signal.
10. **Don't uncomment Halo code.** `# DISCONTINUED` markers are intentional — leave them, don't try to "clean up."

---

## Tooling setup (do this first, in Session 0)

The repo currently has no coverage tooling. Add it minimally:

1. Append `coverage==7.6.1` (or latest 7.x) to `requirements.txt`. Rebuild the test image: `docker-compose -f docker-compose-test.yml build`.
2. Create `.coveragerc` at the repo root:
   ```ini
   [run]
   branch = True
   source = GBotDiscord/src
   omit =
       GBotDiscord/src/main.py
       GBotDiscord/src/halo/*
       GBotDiscord/src/quart_api/halo_resource.py
       GBotDiscord/src/**/__init__.py
       GBotDiscord/src/strings.py

   [report]
   exclude_lines =
       pragma: no cover
       raise NotImplementedError
       if __name__ == .__main__.:
   show_missing = True
   skip_covered = False
   fail_under = 100
   ```
3. Add a Make-style helper command to the README under a new "Coverage" section. Recommended invocation:
   ```
   docker-compose -f docker-compose-test.yml run --rm gbot-test \
     -m coverage run GBotDiscord/test/test.py && \
   docker-compose -f docker-compose-test.yml run --rm gbot-test \
     -m coverage report -m
   ```
4. Capture the baseline coverage percentage in the Session 0 commit message — it's the starting point every subsequent session improves on.

---

## Inventory: where we stand today

Counts from `grep -E "^\s*(async def|def)\s+test_"` on existing test files vs. function counts in src:

| Module | Src lines | Src defs | Test fns | Status |
|---|---:|---:|---:|---|
| `config/config_cog.py` | 343 | 20 | 25 | **Likely high** — review |
| `config/config_queries.py` | 66 | 7 | (covered via cog tests) | Likely covered indirectly |
| `gcoin/gcoin_cog.py` | 241 | 14 | 35 | **Likely high** — review |
| `gcoin/gcoin_queries.py` | 70 | 8 | (none direct) | Needs direct tests for `performTransaction` invariants |
| `gtrade/gtrade_cog.py` | 733 | 33 | 73 | Likely high but biggest cog — gap-fill |
| `gtrade/gtrade_queries.py` | 145 | 16 | (none direct) | Needs direct tests |
| `hype/hype_cog.py` | 207 | 12 | 17 (6 are TODO stubs) | **`unmatch` pagination tests are stubbed out** |
| `hype/hype_queries.py` | 25 | 3 | (covered indirectly) | OK |
| `leaderboards/leaderboards_queries.py` | 71 | 8 | 0 | **No tests at all** |
| `music/music_cog.py` | 557 | 41 | 82 | **Likely high** — review |
| `patreon/patreon_cog.py` | 95 | 8 | 5 | **Partial** — see `Patreon.patreon_validation` branches |
| `patreon/patreon_queries.py` | 21 | 4 | 0 | No direct tests |
| `presence/presence_cog.py` | 51 | 5 | 0 (stub class only) | **No tests** |
| `predicates.py` | 135 | 24 | 0 (stub class only) | **No tests** |
| `quart_api/api.py` | 166 | 14 | 0 | **No tests** — Quart endpoints unwired in tests |
| `quart_api/development_queries.py` | 73 | 2 | 0 | **No tests** |
| `quart_api/development_resource.py` | 104 | 3 | 0 (stub class only) | **No tests** |
| `quart_api/discord_resource.py` | 111 | 2 | 0 (stub class only) | **No tests** |
| `quart_api/leaderboards_resource.py` | 14 | 1 | 0 (stub class only) | **No tests** |
| `quart_api/storms_resource.py` | 83 | 4 | 0 (stub class only) | **No tests** |
| `storms/storms_cog.py` | 490 | 26 | 63 | Likely high — gap-fill |
| `whodis/whodis_cog.py` | 545 | 26 | 73 | Likely high — gap-fill |
| `utils.py` | 269 | 27 | 0 | **No tests** (used everywhere) |
| `properties.py` | 190 | 5 | 0 | **No tests** |
| `firebase.py` | 50 | 8 | 0 (mocked everywhere) | Trivial — see [Session 3](#session-3--firebasepy--leaderboards_queriespy) |
| `pagination.py` | 62 | 6 | 0 | **No tests** |
| `main.py` | 151 | 9 | 0 | Excluded from coverage; handlers may be testable if refactored |

---

## Sessions

Each session is one `/plan` cycle. Order matters: earlier sessions cover modules that later test code will mock or import.

### Session 0 — Coverage tooling & baseline
**Goal:** Add `coverage.py`, wire `.coveragerc`, document the run command, and capture the starting coverage %.
**Files touched:** `requirements.txt`, `.coveragerc` (new), `README.md` (Coverage section), commit message records baseline %.
**Acceptance:** `docker-compose -f docker-compose-test.yml run --rm gbot-test -m coverage run GBotDiscord/test/test.py` runs to green and `coverage report -m` produces a per-file table.

### Session 1 — `utils.py`
**Goal:** Cover every helper in `GBotDiscord/src/utils.py`. This is the highest-leverage module — many later tests can stop ad-hoc mocking once these are covered.
**New file:** `GBotDiscord/test/utils_test.py` (NB: must NOT shadow `GBotDiscord/test/utils.py` — pick a distinct class name like `TestUtils` and register in `test.py`).
**Cases to cover:**
- `idToUserStr`, `idToRoleStr`, `idToChannelStr` — string formatting (1 assertion each).
- `idStrArgToInt` — success path + `ArgumentParsingError` raised on non-numeric.
- `strParamToArgs` — single quoted segment, multiple, empty `""` collapsed, no quotes.
- `emojisParamToArgs` — unicode emoji, custom `<:name:id>`, mixed, whitespace skipped, empty raises `ArgumentParsingError`.
- `isUserAdminOrOwner` — owner short-circuit; admin role match; no match → `False`. Mock `config_queries.getServerValue`.
- `isUserAssignedRole` — `roleId` None → `False`; roleId in user roles → `True`; not in → `False`.
- `isUserInThisGuildAndNotABot` — found+human / found+bot / not-found. Use `AsyncIter`.
- `isUrlImageContentTypeAndStatus200` — patch `httpx.AsyncClient` to return 200+png, 200+wrong content-type, 500, and raise. (Use `unittest.mock.patch` on `httpx.AsyncClient`.)
- `calculateTimeLeftStr` — `0s`, `< 1 min`, `> 1h`. Pure math.
- `roundDecimalPlaces` — 2 places, 0 places, half-up rounding boundary.
- `copyDictWithoutKeys` — excluded keys omitted; original dict unchanged.
- `filterGuildsForInstance` — guilds in client kept; absent ones removed.
- `getServerPrefixOrDefault` — DM message returns `.`; guild message returns DB value.
- `getGuildsForPatreonToIgnore` — `PATREON_GUILD_ID` always appended if absent.
- `getOnlineAndIdleUsers` — online included, idle included, offline/bot excluded.
- `getUserIdFromName` — case-insensitive match, no match returns `None`.
- `askUserQuestion` — sends question, awaits `client.wait_for` with check that matches author/channel.
- `sendDiscordEmbed` — branches: description/None, file/fileURL/both/neither, thumbnailUrl present, `deleteAfter` set.
- `sendMessageToAdmins` — channel configured + send success; channel not configured returns `False`; exception fetching channel returns `False` and logs.
- `purgePreviousMessages` — `PartialInteractionMessage` and wrong-channel messages deleted individually; <100 batch-deleted; >100 batched into 100-message chunks.
- `removeRoleFromAllUsers` — happy path; exception → `False`.
- `addRoleToUser` — happy path; exception → `False`.
- `createTempTableImage` / `deleteTempTableImage` — patch `df2img.plot_dataframe`/`df2img.save_dataframe`, assert called with the constructed `DataFrame`; `deleteTempTableImage` returns `True` when file exists (patch `os.path.exists` + `os.remove`), `False` when missing.

### Session 2 — `properties.py`
**Goal:** Cover `GBotPropertiesManager`. Pure-Python class with env coercion + `setProperty` dispatch.
**New file:** `GBotDiscord/test/properties_test.py`.
**Cases:**
- `getEnvProperty` — value present → coerced through `determineValue`; missing + default → default; missing + no default → `PropertyNotSpecified` raised and logged. Use `unittest.mock.patch.dict(os.environ, ...)`.
- `determineValue` — every `INT_PROPERTIES` member coerced to int; `SPLITTABLE_INT_PROPERTIES` empty string → `[]`, comma-separated → list of ints; `LOG_LEVEL` routed through `getLogLevel`; default branch returns raw value.
- `getLogLevel` — every named level (`CRITICAL`, `FATAL`, `ERROR`, `WARNING`, `WARN`, `INFO`, `DEBUG`) returns matching `logging.*`; unknown → `logging.NOTSET`.
- `setProperty` — every mutable property mutates the class attribute and returns `True`; `LOG_LEVEL` additionally calls `logger.setLevel`; unknown property returns `False`. **Bug note:** `WHODIS_COOLDOWN_MINUTES` is mis-set to `WHODIS_TIMEOUT_MINUTES` in `setProperty` (line 168). Write a test that documents the bug (XFAIL or comment), or fix and write a test asserting it's correct — decide with the user before changing behavior.
- `startPropertyManager` — patch the env, call it, assert every class attribute is populated with the expected coerced value.

### Session 3 — `firebase.py` + `leaderboards_queries.py`
**Goal:** Cover the DB primitives wrapper and the leaderboards query module.
**New files:** `GBotDiscord/test/firebase_test.py`, `GBotDiscord/test/leaderboards/leaderboards_queries_test.py`.
**`firebase.py` cases:**
- `loopChildren` — calls `.child()` once per element in order; returns the final ref. Stub `GBotFirebaseService.db` with a `Mock` whose `.child(...)` returns another mock chainable.
- `get/set/push/update/remove` — each calls `loopChildren` with the args and forwards to the right method on the returned object.
- `authenticate` — `sign_in_with_email_and_password` success → `True`; exception → `False`. Stub `GBotFirebaseService.auth`.
- `startFirebaseScheduler` — patch `pyrebase.initialize_app`, assert `db` and `auth` are set from its return value.

**`leaderboards_queries.py` cases:**
- `getLeaderboard` — returns `.val()` of `["leaderboards"]`.
- `setUserName` — calls `set(['leaderboards', userId, 'username'], userName)`.
- `setUserBalance` — sets balance string, then calls `setUserName` (verify by spying on `GBotFirebaseService.set` call sequence).
- `incrementUserNumValue` — increments existing int value; missing key starts at `0+1=1`.
- `getUserLeaderboardIntValue` — present → `int(val)`; absent → `0`.
- `getUserLeaderboardDecimalValue` — present → `Decimal(val)`; absent → `Decimal('0.00')`.
- `addToUserNumRewardsValue` — adds amount, rounds to 2 places via `utils.roundDecimalPlaces`.
- `processTransactionForLeaderboardRewards` — `"Storms"` in other → `addToUserNumRewardsValue` for `numNetStormRewards`; `"Who Dis"` in other → `numWhoDisRewards`. Negative `-X.XX` gcoin string handled (sign flip).

### Session 4 — `pagination.py`
**Goal:** Cover `FieldPageSource`, `DescriptionPageSource`, `CustomButtonMenuPages`, and `startPages`.
**New file:** `GBotDiscord/test/pagination_test.py`.
**Cases:**
- `FieldPageSource.format_page` — embed gets every entry as a field; `thumbnailUrl=None` does not call `set_thumbnail`; footer text reflects `menu.current_page + 1` and `get_max_pages()`. Provide a small fake `menu` with the right attributes.
- `DescriptionPageSource.format_page` — description is `\n`-joined entries; optional `fields` are added; thumbnail omitted when None.
- `CustomButtonMenuPages.__init__` — `delete_message_after` is `True`; five `MenuPaginationButton`s added with the right emojis.
- `startPages` — `nextcord.Interaction` branch calls `pages.start(interaction=context)`; non-interaction calls `pages.start(context)`.

### Session 5 — `predicates.py`
**Goal:** Replace the stub `TestPredicates` class with real tests for every predicate factory. Each factory has slash + prefix branches.
**File to edit:** `GBotDiscord/test/predicates_test.py` (already imported in `test.py`).
**Cases (per factory, slash + prefix where applicable):**
- `isMessageAuthorAdmin` — admin → pass; non-admin → raises `MessageAuthorNotAdmin`. Stub `utils.isUserAdminOrOwner`.
- `isMessageSentInGuild` — guild set → pass; `None` → raises `MessageNotSentFromGuild`.
- `isMessageSentInPrivateMessage` — guild `None` → pass; guild set → raises `MessageNotSentFromPrivateMessage`.
- `isFeatureEnabledForServer` — `privateMessagesAllowed=True` + DM → pass without DB check; feature on → pass; feature off → `FeatureNotEnabledForGuild`; feature off + name is `toggle_legacy_prefix_commands` → `LegacyPrefixCommandsNotEnabledForGuild`.
- `isAuthorAPatronInGBotPatreonServer` — wrong guild → `NotSentFromPatreonGuild`; right guild + no role → `NotAPatron`; right guild + role → pass.
- `isGuildOrUserSubscribed` — guild in `PATREON_IGNORE_GUILDS` → pass; mutual guild in ignore list (DM context) → pass; subscribed guild via patron table → pass; subscribed via mutual (DM) → pass; nothing matches → `NotSubscribed`.

The trick: each factory returns either `application_checks.check(predicate)` or `commands.check(predicate)` — both decorators wrap an async predicate. To invoke the inner predicate directly, you can call `factory(...).__wrapped__` (for `commands.check`) or you can extract the predicate by introspecting the decorator's closure. The cleaner alternative is to refactor each `commonPredicate` into a module-level async function and test that — propose this refactor in the `/plan` session.

### Session 6 — `presence/presence_cog.py`
**Goal:** Replace the stub `TestPresence` with real tests.
**File to edit:** `GBotDiscord/test/presence/presence_test.py`.
**Cases:**
- `on_ready` — populates `default_presence_activities` with three entries; starts `loop_presence`. `RuntimeError` from `.start()` is logged, not raised.
- `loop_presence` — when `currentTime >= custom_presence_expire_time`, calls `client.change_presence` with the indexed activity, increments `presence_index`, wraps to 0 after last. When `currentTime < custom_presence_expire_time`, does nothing. Exception path logs error.
- `changePresence` — happy path sets `custom_presence_expire_time` and calls `change_presence`, returns `True`. Exception path returns `False` and logs.

### Session 7 — Quart resource stubs (`development`, `discord`, `storms`, `leaderboard`)
**Goal:** Replace the four stub resource test files with real tests. Each resource has a sync `doc()` returning a dict and an async `post()` (the leaderboard resource has only `get()`).
**Files to edit:** `GBotDiscord/test/quart_api/{development,discord,storms,leaderboards}_resource_test.py`.

`development_resource_test.py` cases:
- `doc()` — returns the documented options/postBodyTemplate dict.
- `post()` — for each action name (`rebuildLatest`, `runDatabasePatch`, `setProperty`, `syncSubscribers`), cover the happy path and each failure branch (missing keys, bad patch name, unknown property, git updater unreachable, `patreon_validation` raising). Mock `Development.sendRequestToGitUpdaterHost`, `development_queries.create_leaderboard_table_7_0_0`, `GBotPropertiesManager.setProperty`, and `client.get_cog('Patreon')`.
- `sendRequestToGitUpdaterHost` — patch `httpx.AsyncClient`, cover 200 + JSON, non-200, exception, `None` response.

`discord_resource_test.py` cases:
- `doc()` — returns the documented dict.
- `post()` — `leaveGuild` happy path + missing serverId + serverId not in DB. `sendMessage` with and without `optionalMessageIdForReply`. `changePresence` for each `type` (`playing`/`listening`/`watching`), invalid type, invalid expire format, `Presence.changePresence` returning False. Invalid request → error dict. JSON parse error → `abort(400)`.

`storms_resource_test.py` cases (covers both `StormsStart` and `StormsState`):
- `doc()` — both classes return the documented dict.
- `StormsStart.post()` — `serverId="all"` calls `generateNewStorm` for each entry in `stormStates` and returns each state with `deleteMessages` stripped; specific serverId calls once; invalid serverId returns error dict.
- `StormsState.post()` — same shape but does NOT call `generateNewStorm`.

`leaderboards_resource_test.py` cases:
- `Leaderboard.get()` — happy path returns `leaderboards_queries.getLeaderboard()` result; exception → `abort(400)`.

For each, register `Test<X>Resource` in `test.py` (already imported but assertions are no-ops; replace the test bodies).

### Session 8 — `quart_api/api.py`
**Goal:** Cover `GBotAPIService.registerAPI` route wiring + the `authorize` decorator + `logPayloadAndResponse`.
**New file:** `GBotDiscord/test/quart_api/api_test.py`.
**Approach:** Use Quart's test client. The route handlers delegate to the resource classes — mock those at the module level. Authorization is `HTTP Basic` against `GBotFirebaseService.authenticate` — stub that.
**Cases:**
- `authorize` — sync function: missing auth → 401; non-basic → 401; basic but `authenticate` returns `False` → 401; auth ok → forwarded. Async function: same set of cases.
- `logPayloadAndResponse` — with `data` includes `requestPayload`; without omits it.
- Each registered route hits its resource. Smoke-test one GET and one POST per resource group; you do not need to re-test every action body here (Session 7 covered those).
- Ensure `cors(app, allow_origin="*")` is intact for the public leaderboard endpoint.

The `gbotClient.loop.create_task(app.run_task(...))` line is fire-and-forget on the bot's event loop — patch `app.run_task` so it doesn't actually bind. Don't try to assert that it ran.

### Session 9 — `quart_api/development_queries.py`
**Goal:** Cover `create_leaderboard_table_7_0_0` and `getAllUserGCoin`.
**New file:** `GBotDiscord/test/quart_api/development_queries_test.py`.
**Cases:**
- `getAllUserGCoin` — wraps `GBotFirebaseService.get(["gcoin"]).val()`.
- `create_leaderboard_table_7_0_0` — provide a fake `client.fetch_user` that returns a user with `.name`, and a fake `getAllUserGCoin` payload with transactions covering every memo branch: `"Won Guess"`, `"Won Bet"`, `"Started Storm"`, `"x10"`, `"x5"`, `"x2.5"`, `"x1.25"`, `"Storms"` in other, `"Who Dis"` in other, negative gcoin string (sign flip). Assert `GBotFirebaseService.set(['gcoin', userId, 'username'], name)` and `set(['leaderboards', userId], expectedDict)` are called with the right counts.

### Session 10 — `patreon/patreon_cog.py` gap-fill + `patreon_queries.py`
**Goal:** The existing 5 tests cover `patreon_validation`'s three main branches and the two `patreon`/`patreonSlash` commands. Verify branch coverage of `patreon_validation` (the inner loops over `getAllGuilds()` and `getAllPatrons().values()` likely have uncovered combinations: member-not-fetched, no patron role, etc.). Also add direct tests for `patreon_queries`.
**Files to edit/create:** `GBotDiscord/test/patreon/patreon_test.py`, new `GBotDiscord/test/patreon/patreon_queries_test.py`.
**Cases to add to cog test:**
- `getAllGuilds` returns empty → no-op.
- `fetch_member` raises (member left) → handled.
- Author has no patron role → entry removed.
- Patron table entry references guild bot is not in.
**Queries cases:** trivial — one assertion per function (the four functions just wrap Firebase calls).

### Session 11 — `hype/hype_cog.py` `unmatch`/`unmatchSlash` pagination tests
**Goal:** Fill the six `unmatch_*` TODO stubs in `hype_test.py`. These hinge on mocking `pagination.CustomButtonMenuPages.__init__` + `pagination.FieldPageSource.__init__` so the cog code can call them without rendering a real menu, then asserting on the question + outcome paths (cancel / timeout / match-deleted).
**File to edit:** `GBotDiscord/test/hype/hype_test.py`.
**Cases (each in slash + prefix variant):**
- `unmatch_cancel` — list shown, user picks cancel button → cancellation message.
- `unmatch_timeout` — list shown, no input → timeout message.
- `unmatch_match_deleted` — list shown, user picks a match → `hype_queries.removeMatch` called with the right ids and confirmation message sent.

The note in the existing TODO says "once figured out here, update `gcoin_test` & `config_test` to behave the same way (remove try/catch blocks)" — defer that cleanup unless it falls out naturally; otherwise file a follow-up session for it.

### Session 12 — `gtrade/gtrade_queries.py` + `gtrade/gtrade_cog.py` gap-fill
**Goal:** Direct tests for every function in `gtrade_queries.py` (16 functions, mostly thin Firebase wrappers but a few have logic: `getUserItem`, `renameItemRelatedPendingTradeTransactions`, `removePendingTradeTransactionAndOthersAffected`, `getPendingTradeTransaction`). Then run `coverage report -m` against `gtrade_cog.py` to identify uncovered lines and fill them.
**Files:** new `GBotDiscord/test/gtrade/gtrade_queries_test.py`; edit `GBotDiscord/test/gtrade/gtrade_test.py` to plug gaps surfaced by the coverage report.

### Session 13 — `gcoin/gcoin_queries.py`
**Goal:** Direct tests for `performTransaction` invariants — `EnforceRealUsersError`, `EnforceSenderReceiverNotEqual`, `EnforcePositiveTransactions`, `EnforceSenderFundsError`, and the four valid-transaction permutations (real-to-real, real-to-virtual, virtual-to-real, virtual-to-virtual).
**New file:** `GBotDiscord/test/gcoin/gcoin_queries_test.py`.
**Also cover:** `validateFunds`, `getAllUserBalances`, `getUserBalance` (present + absent), `setUserBalance` (calls `setUserName` + `leaderboards_queries.setUserBalance`), `setUserName`, `addUserTrxHistory` (calls `leaderboards_queries.processTransactionForLeaderboardRewards`), `getUserTransactionHistory`.

### Session 14 — `main.py` error & completion handlers (optional)
**Goal:** Only attempt if the user wants `main.py` in the coverage target. Currently it's excluded because it's mostly module-level boot.
**Approach:** Factor the bot-level event handlers (`on_ready`, `on_application_command_completion`, `on_command_completion`, `on_completion`, `on_application_command_error`, `on_command_error`, `on_error`, `getCommandPrefix`, `CustomFormatter`) out of `main.py` into a new module like `GBotDiscord/src/bot_handlers.py`, then test:
- `CustomFormatter.format` — `record.args == ()` short-circuit; `AccessLogAtoms` short-circuit; `None` in args replaced with `''`; `\` and `"` escaped.
- `getCommandPrefix` — DM → `.`; guild → DB-fetched prefix.
- `on_error` — every `isinstance` branch sends the matching message; `ApplicationInvokeError` unwraps to `error.original`.
- `on_completion` — formats log line with/without guild.

If the user prefers, leave `main.py` excluded permanently and skip this session.

### Session 15 — Gap-fill remaining cogs (`music`, `whodis`, `storms`, `config`, `gcoin`)
**Goal:** Run `coverage report -m` after all earlier sessions and gap-fill the remaining uncovered lines, one cog per micro-session if needed. These cogs already have substantial coverage (35–82 tests each), so this is targeted rather than top-down.
**Approach for each:** read the `coverage report -m` output for the cog, identify the missed line ranges, write the minimum test cases that hit them. Likely targets:
- `music_cog.py`: error paths in `play`/`spotify` (yt-dlp failures, disconnected voice, queue overflow). Cache-deletion task edge cases.
- `whodis_cog.py`: cooldown edge cases, role-config-missing branches.
- `storms_cog.py`: storm-state transitions, ESM tier multipliers, channel-not-configured.
- `config_cog.py`: every `BadArgument` raise, every `dependentDbSwitches` / `dependenciesDbSwitches` combination not already covered.
- `gcoin_cog.py`: leaderboard-side-effect coverage.

---

## Per-session prompt template

Most sessions you can just type `/plan` and say "next session from plans/completed/100-percent-test-coverage.md" — Claude will read the file, find the first unticked box, and proceed. Use the longer template below if you want to be explicit, or if you're skipping ahead:

> Read `plans/completed/100-percent-test-coverage.md`. Pick the first unticked session in the **Progress tracker** (or use Session N if I name one). Plan that session per its `## Session N — ...` description, then implement. Follow [Ground rules](#ground-rules) — repo conventions (Docker-only test runs via `docker-compose-test.yml`, Firebase mocked via direct module reassignment, slash + prefix duality, `pagination.FieldPageSource.__init__` mocked with try/except wrap) are non-obvious.
>
> Before declaring done: run `coverage run` + `coverage report`, tick the session's checkbox in `plans/completed/100-percent-test-coverage.md`, and fill the new coverage % into the tracker. Commit format: `Test coverage Session N: <summary> (coverage: XX% → YY%)`.

---

## Final steps — bug fixes discovered along the way

As sessions progress, bugs discovered in `GBotDiscord/src/**` that don't fit the
current session's scope are accumulated here. Address all of these in a dedicated
bug-fix session **after** the coverage tracker hits 100% — fixing them earlier
risks expanding any one session's scope. Each fix should be paired with branch
tests for the affected code path.

- ~~**Session 1 — `utils.purgePreviousMessages` chunker (`utils.py` lines 200–211):**
  drops every 101st message (current message lost on chunk boundary) and never
  flushes the final partial batch.~~ **Fixed:** chunker rewritten to a slice-based
  loop (`range(0, len(deleteMessages), 100)`); `@unittest.expectedFailure` removed
  from `test_purgePreviousMessages_over_100_chunks`. Coverage still 100%.

---

## When the plan is done

The exit criteria for "100% coverage achieved":

1. `docker-compose -f docker-compose-test.yml run --rm gbot-test -m coverage run GBotDiscord/test/test.py` exits 0.
2. `docker-compose -f docker-compose-test.yml run --rm gbot-test -m coverage report` shows 100% for every file not in the `omit` list of `.coveragerc`.
3. `fail_under = 100` in `.coveragerc` means CI will reject any future regression.
4. The README's new "Coverage" section is updated with the final command and the 100% claim.
