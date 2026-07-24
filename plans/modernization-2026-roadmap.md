# Modernization 2026 roadmap — the HalloweenEvent playbook applied to GBot

**This is the master plan for the `modernization-2026` branch.** It supersedes the session plans in this directory ([dependency-vulnerability-patches.md](dependency-vulnerability-patches.md) — complete; [python-base-image-bump.md](python-base-image-bump.md) — superseded, but its Session 1 audit results carry forward into Phase 1). The branch does **not** merge to `develop` until every phase here is done or explicitly deferred.

**Method:** mirror the modernization arc executed on [HalloweenEvent](https://github.com/cgoulart35/HalloweenEvent) during 2026 — same fixes, same package switches, same Firebase migration, same CI/CD shape — adapted only where GBot genuinely differs (nextcord bot vs Flask webapp, unittest vs pytest, one container vs two). HalloweenEvent reached **pip-audit 0 vulnerabilities** and runs image-based CD on the same Raspberry Pi 4 (aarch64) that GBot will deploy to. Reference commits are cited per phase; the clone lives at the maintainer's discretion — cite hashes, not local paths.

## Non-negotiables (every phase, no exceptions)

1. **Full test suite green** before and after every phase, run the canonical way (in-image). Pass rate stays 100%.
2. **Coverage stays 100% on `GBotDiscord/src`** (the `100-percent-test-coverage` effort is the foundation — don't erode it). Run the coverage suite when a phase touches source.
3. **No functional regressions.** Phases that touch runtime deps or source must pass the `main.py` import smoke-test AND the prod-container startup smoke-test (`GBot logged in as ...`, zero tracebacks). The prod smoke-test logs into Discord with the real token — coordinate timing with the maintainer if a production instance is live elsewhere.
4. **Atomic phases.** Each phase is one coherent commit (or small commit set) that leaves the branch green. If a phase goes red, revert it fully — no partial states.
5. **No source refactors beyond what the phase requires.** Halo remains commented in place. Dual-command pattern, facade pattern, logging format all preserved.
6. **Docs move with the code.** Every phase updates the README/CLAUDE.md sections it invalidates, in the same commit set — HalloweenEvent did this continuously (`d765a88`, `9f2e19a`, `b2aefbf`, `28f6c96`) and it's why its docs stayed trustworthy. GBot sections that will need it: test-running (pytest runner), Firebase setup (firebase-admin), deployment (CI/CD + Pi watcher), and the Podman note for local dev.

## Environment notes (Session-1 findings, still true)

- Local dev machine runs **Podman**, not Docker: every `docker-compose -f <file> ...` command runs as `podman compose -f <file> ...` (delegates to Docker Compose v5.3.1). Start the VM with `podman machine start` first.
- The Raspberry Pi target runs **64-bit (aarch64)** — same Pi that runs HalloweenEvent, which validated every heavy wheel family GBot needs (numpy 2.x aarch64 etc.).
- The deploy target uses real `docker compose` (see HalloweenEvent `scripts/`), so compose files must stay engine-agnostic.
- **The live deployment (verified 2026-07-23):** host `StormerPi2` (SSH alias), repo at `/home/cgoulart/Code/GBot/`, secrets in `Shared/` there. The running GBot container is **`GBot_7.0_dev`** (the dev compose file, up weeks at a time) alongside HalloweenEvent's prod containers and Cloudflare tunnels — don't assume `GBot_7.0_prod`. **The Pi bot keeps running throughout this plan's phases 1–3; it is only touched at Phase 4 cut-over.** Local prod smoke-tests use the real `Shared/` secrets copied from the Pi — **the maintainer must stop the Pi's GBot container first** (`ssh StormerPi2`, then `docker stop GBot_7.0_dev` or compose down in `/home/cgoulart/Code/GBot`) so two instances never share one Discord token/Firebase state; restart it after the local check.

---

## Phase map (mirrors HalloweenEvent's arc)

| Phase | GBot work | HalloweenEvent reference |
|---|---|---|
| 0 | ✅ Already done: 100% coverage; dep-vuln patches (22→19 advisories); Py-3.13 compatibility audit | (GBot-specific groundwork) |
| 1 | Python base image 3.9.7 → 3.13 + paired dep bumps + **drop unused ipython/nbformat** + dev-reqs split | `2ca8aad` "Modernize to Python 3.12 and patch dependency vulnerabilities" |
| 2 | **Pyrebase4 → firebase-admin** behind the same facade; unpin urllib3, drop requests-toolbelt → **pip-audit 0** | `744a002` "Replace Pyrebase4 with firebase-admin and drop torch" |
| 3 | GitHub Actions **CI**: test + pip-audit + doc-change filter; retire dependabot.yml (security-only via settings) | `df58506` ci.yml, `905ea0d` Node-24 majors, `744a002` dependabot removal |
| 4 | **Secrets/build-context hygiene**, then **image-based CD**: GHCR arm64 publish job + in-repo deploy watcher on the Pi; prod compose pulls `ghcr.io` image | env.example pattern: `a3b65a3`; CD: `3da60bb`, `32206eb` watcher-loop fix + publish gating, `82d14b1` QA/`IMAGE_TAG=test` isolation |
| 5 | **Claude PR review** workflow + CLAUDE.md "accepted trade-offs" section + **repo Claude skills** | review: `c2b367c` + fix chain `afa42b7`/`80be7c2`/`ce8baf4`/`c4e2528`/`88d9276`/`a3169ba` (final form is authoritative); skills: `32683b2`, `293b726` |
| 6 | Hardening & accuracy review pass over GBot's API surface (scoped last, informed by phases 1–5) | `3beb5e7` security hardening, PR #10 accuracy passes |

**Sequencing rationale:** 1→2 ordered because firebase-admin requires modern Python (would not install on 3.9). 3 lands before 4 because the publish job extends ci.yml. 5 is independent after 3 (it reviews PRs; CI must exist for the flow to feel complete). 6 last so the review pass covers the post-migration surface.

---

## Phase 1 — Python 3.13 base + paired dep bumps

Mirrors HalloweenEvent `2ca8aad`, which went to `python:3.12` (full image, floating patch) because torch capped it at 3.12. **GBot has no torch → take 3.13** for +12 months of security support; the [python-base-image-bump.md Session 1 audit](python-base-image-bump.md) (2026-07-23) verified every GBot dep against 3.13, including the nextcord 2.4.2 blocker check (clear — permissive aiohttp range, resolver already picks aiohttp 3.13.5).

Changes:
1. `Dockerfile`: `FROM python:3.9.7` → `FROM python:3.13` (**full image like HalloweenEvent, not slim** — ships the toolchain for the pynacl `SODIUM_INSTALL=system` build, keeps the apt lines unchanged; simplicity over ~800MB on a Pi with ample disk). Add `RUN pip install --upgrade pip` before `pip install -r requirements.txt` (clears base-image pip advisories — HalloweenEvent does exactly this).
2. `requirements.txt` (pins from the Session 1 audit): numpy `1.22.4 → 2.5.1`, pandas `2.0.0 → 2.3.3`, yt-dlp `2025.2.19 → 2026.7.4` (clears CVE-2026-26331), debugpy `1.6.7 → 1.8.21`.
3. **Drop `ipython` and `nbformat` entirely** — verified 2026-07-23: zero imports in `GBotDiscord/src/` and `GBotDiscord/test/`. This replaces the old plan's "bump ipython to 8.39.0" row (GBot's analog of HalloweenEvent dropping torch: delete unused weight instead of upgrading it).
4. **`requirements-dev.txt` split** (HalloweenEvent pattern): move `coverage==7.10.7` out of `requirements.txt`; add `pytest==9.0.3` + `pip-audit==2.10.0` (HalloweenEvent's exact pins). Runtime image installs only `requirements.txt`; the test flow installs dev reqs on the fly. *(pytest 9 requires Python ≥3.10 — another reason the dev-reqs split pairs with the 3.13 bump in this phase.)*
5. **Standardize the test runner on pytest — without touching a single test file.** The 762 existing `unittest.TestCase` tests are collected and run natively by pytest, and the `<cog>_test.py` naming already matches its default discovery pattern. **Verified 2026-07-23 on the current image: `python -m pytest GBotDiscord/test/` → 762 passed, same count as `test.py`'s unittest runner.** Add a minimal `pytest.ini` whose only job is preserving the archived-Halo convention that `test.py` encodes via commented imports: `addopts = --ignore=GBotDiscord/test/halo --ignore=GBotDiscord/test/quart_api/halo_resource_test.py`. Gitignore `.pytest_cache/`. Keep `GBotDiscord/test/test.py` working as the documented local/VS Code entry point (it's also the pre-flight definition in these plans) — retire it, if ever, in Phase 6.
6. `scripts/test.sh` (port of HalloweenEvent's): deterministic wrapper — builds the test image, runs `python -m pytest -q` in an ephemeral container with dev reqs installed ad hoc. Adapt to `podman compose`-compatible invocation (plain `docker compose` works via podman's socket too; use `docker compose` if available, else `podman compose` — keep it one line, engine-agnostic).
7. **numpy 2.x API sweep** (mirror of HalloweenEvent's `views.py` `fromstring → frombuffer` fix): grep `GBotDiscord/src/` for APIs removed by numpy 2.x / the 1.24 alias purge (`fromstring`, `np.float`, `np.int`, `np.bool`, `np.object`) before the bump; fix the call sites the grep names (this is migration work the phase requires, not an out-of-scope refactor).
8. **Dependency-import + version-floor lock tests** (HalloweenEvent `tests/` pattern): a small new test module that (a) imports every runtime dep top-level, (b) asserts security floors that must never regress (yt-dlp ≥ 2026.02.21 now; urllib3 ≥ 2 arrives with Phase 2). Additive tests only — coverage stays 100%.
9. Everything else stays pinned as-is (nextcord 2.4.2, quart 0.19.9, Werkzeug 3.1.8, df2img, emoji, httpx, Pyrebase4 + its urllib3/requests-toolbelt pins — **Pyrebase4 is Phase 2's job, do not touch here**).

*Execution calibration: HalloweenEvent's prod entrypoint needed `ENV PYTHONPATH` in the Dockerfile (`c1e2e26`). GBot resolves `GBotDiscord.src...` imports via the `/GBot` workdir today — expect no change, but if the 3.13 import smoke-test fails on package resolution, that one-line `ENV PYTHONPATH=/GBot` is the known fix, not a refactor signal.*

Gates: full suite green in-image; coverage 100%; `main.py` import smoke-test (see dep-vuln plan §smoke-test, reuse verbatim); prod startup smoke-test; `pip-audit` re-run and delta recorded (expect the yt-dlp CVE + base-image pip/setuptools/wheel CVEs gone; urllib3 1.26.x advisories remain until Phase 2).

### Phase 1 execution record (2026-07-24)

All planned items landed as specified, plus **two dependency additions the 3.13 migration forced** — both stdlib/base-image removals invisible to the Session-1 `requires_python` audit (correction to its "nextcord 2.4.2 verified compatible" conclusion, which checked metadata + wheels but could not see stdlib imports):

1. **`audioop-lts==0.2.2`** — Python 3.13 removed `audioop` (PEP 594); nextcord 2.4.2 `player.py` imports it at module load, breaking all 26 test-module collections. Same backport discord.py uses on 3.13.
2. **`setuptools==81.0.0`** — the `python:3.13` image no longer preinstalls setuptools, and Pyrebase4→gcloud imports `pkg_resources` at module load. setuptools ≥82 **removed** `pkg_resources` entirely (83.0.0 verified empty; 81.0.0 is the newest release still shipping it). Knowingly carries PYSEC-2026-3447 (fixed only in 83) — the pin dies with Pyrebase4 in Phase 2.

Gate results: pytest **764 passed** (762 pre-existing + 2 new dependency-lock tests) and legacy `test.py` runs the same 764 green; coverage **100%** (3427 stmts / 1006 branches, `fail_under=100` exit 0); `main.py` import smoke-test OK; prod startup smoke-test OK (local, Pi container stopped for the window). `pip install --upgrade pip` in the Dockerfile plus the new base cleared the old pip/setuptools-57/wheel advisory block; nextcord 2.4.2 source-builds cleanly on 3.13 and the resolver picked aiohttp 3.14.3.

**pip-audit delta: 19 → 9 advisories (8 unique IDs, 4 packages)** — environment scan and `-r requirements.txt` agree:
- urllib3 1.26.19 ×5 (PYSEC-2026-141/-1994/-1996/-1998/-1999) — Pyrebase4-pinned, Phase 2 clears.
- setuptools 81.0.0 ×1 (PYSEC-2026-3447, reported twice) — introduced by the pkg_resources bridge above, Phase 2 clears.
- quart 0.19.9 ×1 (PYSEC-2026-1860, fix 0.20.0) — published after the dep-vuln baseline; **new Phase 2 work**.
- h11 0.14.0 ×1 (PYSEC-2026-348, fix 0.16.0) — transitive forced by httpx 0.23.3's `httpcore<0.17` pin; published after the dep-vuln baseline; **new Phase 2 work**.

## Phase 2 — Pyrebase4 → firebase-admin (the 0-CVE phase)

Mirrors HalloweenEvent `744a002`. GBot's surface is even smaller than HalloweenEvent's was: `firebase.py` is ~50 lines, no streams, no `.each()` call sites, `push()` return value never consumed, 29 `.val()`-style call sites across queries.

Changes:
1. `requirements.txt`: remove `Pyrebase4`, remove the pinned `urllib3==1.26.19` and `requests-toolbelt==0.10.1` lines (the entire pin block + its comments — the constraint dies with Pyrebase4; urllib3 resolves to patched 2.x via firebase-admin's transitive `requests`). Add `firebase-admin` (7.4.0 or current latest).
2. `firebase.py` rewrite behind the **same `GBotFirebaseService` facade** (same five primitives + `authenticate` + `startFirebaseScheduler` name kept so `main.py` doesn't change):
   - Init: `firebase_admin.initialize_app(credentials.Certificate(<serviceAccountKey path>), {"databaseURL": <from FIREBASE_CONFIG_JSON>})`. The service-account file is already required by the README setup and mounted by compose — verify the in-container path at execution time.
   - `get(children)` returns a tiny adapter object exposing `.val()` (and `.key()` if any call site needs it — audit says at most a handful; check during execution) wrapping `db.reference("/".join(children)).get()`, so the 29 call sites stay untouched.
   - `set/push/update/remove` map 1:1 to `db.reference(...)` methods.
   - `authenticate(username, password)`: firebase-admin cannot do password sign-in (server SDK). Replace the Pyrebase call with one Identity Toolkit REST call — `POST https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=<apiKey from FIREBASE_CONFIG_JSON>` via httpx (already a dependency); `returnSecureToken: true`, 200 = authenticated. Same truthy/falsy contract as today.
3. `GBotDiscord/test/firebase_test.py`: rewrite to mock `firebase_admin` instead of `pyrebase` — keep the same behavioral assertions (this is migration work, not test-weakening; coverage on `firebase.py` stays 100%).
4. `FIREBASE_CONFIG_JSON` env var stays (still supplies `databaseURL` + `apiKey`). README setup section gains a one-line note that the service-account key is now the primary credential.
5. Sweep for stale transitives in the final image (`gcloud`, `oauth2client`, `python-jwt`, `jwcrypto` should all disappear — HalloweenEvent confirmed the same).

Gates: full suite green; coverage 100%; import smoke-test; prod startup smoke-test **plus a live read/write check** (HalloweenEvent's bar: "the running stack reads/writes the live Firebase DB" — e.g., bot starts, `on_ready` lazy-upgrade writes server configs, and a `.toggle`-style command round-trips); **`pip-audit` = 0 vulnerabilities** — the goal state. Record the final audit output in this file.

*Scope addition from Phase 1's audit (2026-07-24): reaching 0 now also requires clearing quart PYSEC-2026-1860 (bump 0.19.9 → 0.20.0), h11 PYSEC-2026-348 (0.16.0 needs httpx > 0.23.3 to lift the `httpcore<0.17` pin), and removing the `setuptools==81.0.0` pkg_resources bridge pin (dies with Pyrebase4). The urllib3/requests-toolbelt/setuptools removals fall out of item 1 automatically; quart + httpx are small additional bumps to verify against the suite.*

## Phase 3 — CI (GitHub Actions)

Port HalloweenEvent's `ci.yml` (final form on their default branch), adapted:
- Jobs: `changes` (doc/CI-only filter: `.md`, `.claude/`, `.github/`), `test`, `audit`, `publish` (Phase 4 adds publish; land 3 without it if preferred, but HalloweenEvent's history shows they're separable — `df58506` then `3da60bb`).
- `test` job: `setup-python 3.13` + pip cache, `pip install -r requirements.txt -r requirements-dev.txt`, then `PYTHONPATH=$GITHUB_WORKSPACE python -m pytest -q` — **identical job shape to HalloweenEvent's**, possible because Phase 1 standardized the runner on pytest (762 unittest-style tests collected natively, Halo ignores in `pytest.ini`). System deps: **none expected** (tests mock Firebase/Discord and never start Quart/ffmpeg; if a nextcord import needs libopus at import time, add the apt line the failure names — do not preinstall speculatively).
- `audit` job: `pip-audit -r requirements.txt` (pinned pip-audit version like HalloweenEvent).
- Action versions: copy HalloweenEvent's current majors (checkout@v6, setup-python@v6 — their `905ea0d` Node-24 bump is the reference).
- Branch triggers: GBot's default branch is `develop` (plus PRs). Add `master` if/when Phase 4 picks it as the deploy branch.
- **Retire `.github/dependabot.yml`** (added by the dep-vuln plan) and flip the repo to Dependabot **security-updates-only** in GitHub settings — HalloweenEvent's end state (`744a002` removed the config; security PRs still flow, e.g. their pillow 12.3.0 bump). The settings flip is a maintainer-side step.

Gate: CI green on a real PR against this branch.

## Phase 4 — Image-based CD to the Raspberry Pi

**Step 0 — secrets & build-context hygiene (hard prerequisite, before the first GHCR push):**
- ✅ **Done early (2026-07-23**, when real secrets were first copied to the dev machine for local smoke-testing**):** `Shared/gbot.env` un-tracked — renamed to the committed `Shared/gbot.env.example` template, real file gitignored (HalloweenEvent `a3b65a3` pattern; their `.gitignore` comment documents the load-bearing reason: the deploy watcher's `git reset --hard` never touches *ignored* files, but it **would wipe real values written into a tracked file on the Pi**). History audited first: no non-blank credential was ever committed — no rotation needed. `Logs/` + `.pytest_cache/` added to `.gitignore`.
- ✅ **Done early (same commit):** `.dockerignore` modernized. *(Correction to this plan's earlier claim, inherited from the superseded python-bump plan's notes: a tracked `.dockerignore` already existed and already excluded `Shared/` and `Logs/` — no image ever baked secrets. The modernization added `.git/`, `plans/`, `.claude/`, coverage/pytest artifacts and collapsed the per-directory pycache lines.)*
- **Remaining at Phase 4 time:** verify the freshly built image really contains no `Shared/` content (`podman run --rm <img> ls /GBot/Shared` errors or comes back empty) before the first GHCR push.

Port HalloweenEvent's publish job + scripts (`3da60bb`, hardened by `32206eb`):
- `publish` job in ci.yml: `runs-on: ubuntu-24.04-arm` (free native arm64 for public repos), needs `[test, changes]`, push-only + code-changed-only; buildx build of `Dockerfile` target `prod`, `platforms: linux/arm64`, push to `ghcr.io/cgoulart35/gbot:latest` + `:<short-sha>`, GHA layer cache. Optional: `APP_VERSION` build-arg stamped like HalloweenEvent (GBot has no version display today — skip unless wanted).
- `docker-compose-prod.yml`: service gains `image: ghcr.io/cgoulart35/gbot:${IMAGE_TAG:-latest}`, `restart: unless-stopped`, `init: true` (HalloweenEvent prod compose is the template). Build stanza stays for local builds.
- `scripts/deploy-watcher.sh` + `scripts/deploy.sh` + `scripts/start.sh`: near-verbatim ports (compose-file name, container/repo paths, and **deploy branch** swapped in). Keep the two hard-won HalloweenEvent details: sorted image-ID comparison (prevents the endless-redeploy loop) and the watcher `exec`-restart after deploy (survives its own file being rewritten by `git reset`).
- **Decision to make at execution (maintainer input):** deploy branch. HalloweenEvent deploys `origin/master`; GBot's flow has historically been `develop`-centric with the external `GIT_UPDATER_HOST` rebuild lever. Recommendation: mirror HalloweenEvent — publish + deploy from `master`, treat `develop` as integration. Whichever is chosen, the `Development.rebuildLatest` API action + `GIT_UPDATER_HOST` become legacy — note their retirement (or leave dormant) explicitly in the phase commit.
- Pi-side bring-up (maintainer-run, documented in README): the repo + secrets already live at `StormerPi2:/home/cgoulart/Code/GBot/` — remaining work is switching that checkout to the deploy branch, retiring the long-running `GBot_7.0_dev` container in favor of the prod compose service, and adding the `start.sh` line to `/etc/rc.local` exactly like HalloweenEvent's.
- **Optional QA-sandbox port** (`qa.sh` / `qa_lifecycle.py`, from `a3b65a3`/`82d14b1`): watcher-safe manual-QA runs on the Pi using `IMAGE_TAG=test`. For GBot the near-equivalent already exists locally (`docker-compose-dev.yml`), so port this only if Pi-side manual QA proves wanted; the load-bearing part — `:test` builds being invisible to the watcher — comes free with `scripts/test.sh`.

Gates: publish job pushes a pullable arm64 image; on the Pi, watcher detects a new `:latest`, redeploys, and the prod smoke-test criteria pass on the Pi itself. `scripts/test.sh` builds as `IMAGE_TAG=test` so QA builds never trigger the watcher (`82d14b1`).

## Phase 5 — Claude PR review workflow

Port `claude-review.yml` in its **final** HalloweenEvent form (the fix chain is baked in: checkout step, `id-token: write`, inline-comment tooling in `--allowedTools`, `--edit-last --create-if-none` summary, draft-PR skip, concurrency cancel, `allowed_bots: "dependabot[bot]"`).
- Adapt the prompt paragraph to GBot: nextcord Discord bot + Quart API, single container on a Raspberry Pi; "Read CLAUDE.md FIRST" stays.
- Add a **"Review scope — accepted trade-offs"** section to GBot's CLAUDE.md (the review prompt depends on it). Seed it with GBot's known intentional decisions: Halo code commented in place, self-signed TLS certs, `cors allow_origin="*"` on the public leaderboard, dual slash/prefix command duplication, implicit RTDB schema.
- Maintainer-side prereqs: `CLAUDE_CODE_OAUTH_TOKEN` repo secret (`claude setup-token`) + Claude GitHub App installed on the repo.
- **Repo Claude skills** (HalloweenEvent PR #11 `32683b2`, orchestrator `293b726`, deterministic wrappers `464a266`). Their actual roster, mirrored for GBot: `/test` (wraps `scripts/test.sh`, which also has the `audit` mode), `/qa`, `/prod-up`, `/prod-down`, `/prod-logs`, and the `/implement-dev-changes` orchestrator — adapted to GBot's flow. The HalloweenEvent pattern to preserve: skills call the deterministic shell wrappers rather than re-deriving commands, so safety flags can't be forgotten.

Gate: a review run posts (or correctly stays silent) on a real PR.

## Phase 6 — Hardening & accuracy pass (last)

HalloweenEvent followed the platform work with a security-hardening PR (`3beb5e7`: debug flags, API keys, CSRF/XSS, sessions) and accuracy passes (PR #10). GBot's equivalents to examine — **scoped as a review-then-fix pass, not a rewrite**:
- **Drop debugpy from the prod entrypoint** and remove the debug port mapping from `docker-compose-prod.yml` (dev stack untouched) — the direct GBot mapping of `3beb5e7`'s first item. Today's prod entrypoint listens on `0.0.0.0:5678`, LAN-exposed once on the Pi.
- Quart API auth surface (basic-auth-over-Firebase on `/GBot/private/*`), self-signed-TLS posture, error-message hygiene (their "500-on-bad-JSON" / "403 masking" analogs), and doc/comment drift.
- The webapp-only items in `3beb5e7` (Turnstile, CSRF, XSS escaping, session cookies, profile re-auth) have **no GBot analog** — GBot has no browser UI; its public surface is one read-only leaderboard GET. The wildcard CORS on that endpoint stays an accepted trade-off (documented in Phase 5's CLAUDE.md section).

Findings become small PRs, each under the same gates. *(Secrets/`.dockerignore` hygiene moved to Phase 4 Step 0 — it can't wait for this phase.)*

---

## Progress tracker

| Phase | Status |
|---|---|
| 1 — Python 3.13 base + dep bumps + ipython/nbformat drop + dev-reqs split | **done** (2026-07-24; see Phase 1 execution record) |
| 2 — firebase-admin migration, pip-audit 0 | pending |
| 3 — CI workflow + dependabot retirement | pending |
| 4 — GHCR publish + Pi deploy watcher | pending |
| 5 — Claude PR review workflow + CLAUDE.md trade-offs section + repo skills | pending |
| 6 — Hardening & accuracy pass | pending |
| Merge `modernization-2026` → `develop` | blocked until all above done/deferred |

## Session workflow

Same model as the prior plans: each session reads this file top-to-bottom, finds the first non-done phase, re-runs the pre-flight (full suite green in-image) before changing anything, does that phase only, updates this tracker in the same commit. A red pre-flight is never the new phase's bug — stop and investigate.
