# Python base image bump — 2-session plan

## How to use this plan across multiple `/clear`'d sessions

Same model as [dependency-vulnerability-patches.md](dependency-vulnerability-patches.md): each new session reads top-to-bottom, finds the first unticked checkbox, runs the [Pre-flight](#pre-flight-run-before-every-session) check, and does *only* that one session's work. Update this file in the same commit as the code change.

---

## Context

GBot's `Dockerfile` pins `FROM python:3.9.7` (line 1). Python 3.9 reached end-of-life in October 2025 — no further security updates. This is now actively blocking dep upgrades:

- **yt-dlp CVE-2026-26331** is marked `blocked` in dep-vuln-patches.md because the fix shipped in `2026.02.21`, which requires Python 3.10+. yt-dlp dropped Python 3.9 support in `2025.10.22+`.
- **numpy** is pinned at `1.22.4` (post-dep-vuln Session 4); the next ABI line on Python 3.13 is 2.0+ since 1.26.x supports only up to 3.12.
- **ipython 8.12.x** is documented in the dep-vuln plan as "the last line supporting Python 3.9."
- **Base-image packages** (pip 21.2.4, setuptools 57.5.0, wheel 0.37.0) account for 9 of the 19 CVEs in the current pip-audit baseline — bumping the Python image refreshes these as a side effect.

This effort lifts the Python base image and pairs the dep bumps that ride alongside it. **It is the natural follow-on to the dep-vuln-patches plan** — dep-vuln Session 6 completed at commit `c34725c`, so this plan is unblocked and ready to start.

## Goals & hard rules

1. **Bump the Python base image to a single, well-chosen target** (see [Target Python version](#target-python-version)). One bump, not a series.
2. **Bump only the deps that the Python bump *requires*** (numpy/pandas ABI ceiling, yt-dlp / ipython upper bounds, debugpy 3.13 wheel availability). Resist the urge to also re-promote `skip`-marked rows from the dep-vuln plan unless their metadata genuinely gates the Python target.
3. **The full Docker test suite is the commit gate** (same as dep-vuln plan).
4. **Must run the `main.py` import smoke-test** — Python-version changes can break module-load imports, and `main.py` is excluded from coverage (`.coveragerc:5`). See dep-vuln plan's smoke-test block at `dependency-vulnerability-patches.md:158-170` — reuse verbatim, do not re-derive.
5. **Must run the prod container startup smoke-test.** The test suite mocks Firebase/Discord; only `docker-compose-prod.yml up` proves the entrypoint actually starts on the new Python interpreter (debugpy listener, Quart API loop, Firebase scheduler init, every cog's `setup()` running for real). The dev container is *not* usable for this — its entrypoint passes `debugpy --wait-for-client`, so main.py hangs forever until a debugger attaches and `on_ready` never fires. See Session 2 Part A step 7. **Without this, "tests pass" does not imply "the bot still works."**
6. **No GBot source edits to make tests pass.** Same rule as dep-vuln plan #4. If a Python-version-driven syntax/stdlib change breaks a cog test, that's a *refactor*, not a base-image bump — revert and mark blocked.
7. **If the build is red, revert the Dockerfile + requirements.txt change atomically.** Don't ship a partial state.
8. **Known failure mode — newer pip's stricter resolver.** The image bump pulls a much newer pip (21.2.4 → 24.x+). Some current pins may install under pip 21 but fail dependency resolution under pip 24 (`ResolutionImpossible` errors). This is *not* a fix-on-the-spot — it's an immediate revert + investigate as a Blocked entry. Common culprits: deps with conflicting transitive requirements that pip 21 silently let through.

## Target Python version

Pick once at Session 1 and stick with it. Recommendation: **Python 3.13** for long-term runway.

| Target | EOL (from 2026-05) | Gating dep changes | Notes |
|---|---|---|---|
| 3.12 (fallback) | Oct 2028 (~30 months) | numpy ≥1.26, pandas ≥2.1.4, yt-dlp ≥2026.02.21, ipython ≥8.13 | Use only if 3.13 audit surfaces a blocker. |
| **3.13** (latest patch) — recommended | Oct 2029 (~42 months) | numpy ≥2.0, pandas ≥2.2.3, yt-dlp ≥2026.02.21, ipython ≥8.27, **nextcord 2.4.2 wheels** (see [Gating deps](#gating-deps-must-bump-in-the-same-commit-as-the-dockerfile) — whole-plan blocker if missing) | Current security-supported line. |
| 3.14 (stretch) | Oct 2030 (~53 months) | Same as 3.13; verify *every* transitive dep has 3.14 wheels (released Oct 2025, ~7 months in at session time) | Longest runway but freshest = most likely to surface a missing-wheel surprise. Only if Session 1 audit comes back fully clean. |

**Default to 3.13.** It picks up ~12 months over 3.12 and lands on Python's current security-supported line. The trade-off is the nextcord 2.4.2 wheel verification: if 3.13 wheels are missing, this plan is blocked (per Gating deps table). Fall back to 3.12 only if Session 1 finds an unavoidable wheel-availability blocker for 3.13. Step up to 3.14 only if Session 1 confirms every dep (including transitives) has wheels for it.

> **Session 1 decision (2026-07-23): 3.13 locked.** Audit found no blockers (see [Session 1 results](#session-1-results-2026-07-23--audit-complete-target-locked)); 3.14 was not pursued — no appetite for freshest-image risk when 3.13 already clears every goal.

## Image pin format

**Use the minor+distro tag, not the exact patch.** Default pin: `python:3.13-slim-bookworm`.

Reasoning:
- **`3.13` (no patch)** lets `docker build` pick up CPython security patches on every rebuild — matches the broader theme of periodic rebuilds catching dep-tree rot. Pinning the exact patch (e.g., `3.13.7`) freezes you out of CPython security updates between explicit bumps, which is the opposite of what this effort exists for.
- **`-slim`** over the full image is a ~6× size reduction (~150MB vs ~1GB) and is the standard production-Python base. If Session 2 hits a missing `apt` package, install it explicitly in the Dockerfile rather than reverting to the full image.
- **`-bookworm`** is the current Debian stable codename. Without an explicit suffix, the tag floats and could break unexpectedly on a Debian major bump; pinning the distro is cheap insurance.

Session 1 confirms the chosen tag exists on Docker Hub (`docker pull python:3.13-slim-bookworm` succeeds) before locking the decision.

> **Confirmed 2026-07-23:** `podman pull docker.io/library/python:3.13-slim-bookworm` succeeded; image reports Python 3.13.14, OpenSSL 3.0.20 preinstalled. (This machine runs Podman, not Docker Desktop — all `docker-compose -f <file> ...` commands in this plan run as `podman compose -f <file> ...` with identical args.)

## Gating deps (must bump in the same commit as the Dockerfile)

Verify each version at Session 1 by reading the dep's PyPI `requires_python` metadata against the chosen Python target. Targets below are *minimum* fix versions for **Py 3.13** (recommended default) — going newer is fine if test-suite green. If Session 1 picks 3.12 instead, use the 3.12 row's floors from the [Target Python version](#target-python-version) table.

**No version-floor guesses below.** Each row's "Target floor" is a directional hint; Session 1's per-dep PyPI audit (Step 2) determines the exact pin. Treat the floors as "no lower than this" — go newer if test-suite green.

| Dep | Current | Confirmed pin (Session 1, 2026-07-23) | Reason |
|---|---|---|---|
| numpy | 1.22.4 | **2.5.1** — latest 2.x (`requires_python >=3.12`, cp313 wheels) | ABI ceiling; 1.22.4 has no 3.13 wheels |
| pandas | 2.0.0 | **2.3.3** — latest 2.x (`>=3.9`, cp313 wheels; requires numpy ≥1.26 on 3.12+, no upper cap → 2.5.1 OK) | 2.0.0 has no 3.13 wheels. pandas 3.0.x now exists but is excluded by df2img 0.2.10's `pandas <3.0.0` cap — staying on 2.x is required, not just conservative |
| yt-dlp | 2025.2.19 | **2026.7.4** — latest (`>=3.10`, pure) | Clears dep-vuln-patches Blocked entry (CVE-2026-26331; fix floor was 2026.02.21) |
| ipython | 8.12.0 | **8.39.0** — latest 8.x (`>=3.10`, pure py3 wheel) | 8.12.0's PyPI metadata (`>=3.8`) doesn't actually cap 3.13, but the 8.12 line predates it and is untested there; plan floor says latest 8.x. (ipython 9.x exists, `>=3.11` — not taken; beyond floor for no gain) |
| debugpy | 1.6.7 | **1.8.21** — latest (cp313 wheels) | 1.6.x predates Python 3.12 and its bundled pydevd is interpreter-version-specific. Required because dev/prod entrypoints invoke `python3 -m debugpy` directly — it is in the startup path, not just a dev tool |
| nextcord | 2.4.2 | **2.4.2 — no change; verified compatible** | `requires_python >=3.8.0`, pure Python. The 2.4.2 release is sdist-only on PyPI (no wheel) → installs via a trivial source build, no C toolchain involved. Deps are `typing_extensions` (pure) + `aiohttp` with a permissive range — the current 3.9.7 image resolved it to aiohttp **3.13.5**, which ships cp313 wheels, so the resolver is free to pick a 3.13-compatible aiohttp. **Whole-plan blocker cleared** |

**Probably-fine deps — all verified compatible at current pins (Session 1, 2026-07-23); none moved to the table:** df2img 0.2.10 (`>=3.8,<4.0`; pins `pandas>=2.0,<3.0`, `plotly>=5.3.1,<6.0`, `kaleido==0.2.1` — all satisfied by confirmed pins, kaleido/plotly wheels are Python-version-independent), emoji 2.2.0 (pure sdist), httpx 0.23.3 (pure; its `httpcore<0.17` pin has no other consumer), nbformat 5.8.0, nextcord-ext-menus 1.5.6, Pyrebase4 4.6.0 (pure; transitives pure or with cp313 wheels — pycryptodome), quart 0.19.9 (`>=3.8` — no bump needed, dep-vuln Session 5 already landed 0.19.9), quart-cors 0.7.0, urllib3 1.26.19 (pure, allows 3.13), requests-toolbelt 0.10.1, Werkzeug 3.1.8 (already latest), coverage 7.10.7 (cp313 wheels).

## Branch strategy

**Use `modernization-2026` — continue stacking.** The dep-vuln plan closed cleanly at commit `c34725c` (Session 6 wrap-up), so this work continues on the same branch. Rationale: single long-lived branch keeps history coherent, and the dep-vuln + Python-bump efforts are naturally one cohesive modernization story at PR-review time.

The alternative — cutting a fresh `python-bump-2026` off `develop` after the dep-vuln plan merges — was considered but rejected: it would force the dep-vuln work to merge first (a separate decision the user hasn't made yet) and produce two PRs for review when one suffices.

## Progress tracker

| Item | Status | Session |
|---|---|---|
| Pick Python target version (3.12 fallback / **3.13 default** / 3.14 stretch) | **done — 3.13** | 1 |
| Confirm image pin `python:3.13-slim-bookworm` exists on Docker Hub | **done** | 1 |
| Audit every direct dep's `requires_python` on target | **done** | 1 |
| Audit Dockerfile `apt` packages on bookworm-slim availability | **done** | 1 |
| Verify `nextcord 2.4.2` has wheels for target Python (whole-plan blocker if missing) | **done — compatible, no bump** | 1 |
| Bump `Dockerfile` `FROM python:3.9.7` → `FROM python:3.13-slim-bookworm` | pending | 2 |
| Bump numpy + pandas (paired) | pending | 2 |
| Bump yt-dlp (clears dep-vuln Blocked entry) | pending | 2 |
| Bump ipython | pending | 2 |
| Bump debugpy (3.13 wheel availability) | pending | 2 |
| Full Docker test suite green | pending | 2 |
| `main.py` import smoke-test green | pending | 2 |
| Prod container startup smoke-test green (`on_ready` fires, no tracebacks) | pending | 2 |
| `pip-audit` re-run; update CVE counts in dep-vuln plan | pending | 2 |
| Update `dependency-vulnerability-patches.md` Blocked section: clear yt-dlp entry | pending | 2 |
| Add `docker` ecosystem to `.github/dependabot.yml` for future Python-tag bumps | pending | 2 |

## Pre-flight (run before EVERY session)

Same as dep-vuln plan — full Docker test suite must be green on whichever branch this work is happening on, before any change.

```bash
docker-compose -f docker-compose-test.yml build
docker-compose -f docker-compose-test.yml run --rm gbot-test GBotDiscord/test/test.py
```

A red pre-flight is *never* this plan's bug to fix — it means the prior state was already broken; stop and investigate before bumping anything.

---

## Session 1 — Compatibility audit (no changes)

**Goal:** decide the Python target, confirm the image pin tag exists, audit every direct dep against it, fill in the [Gating deps](#gating-deps-must-bump-in-the-same-commit-as-the-dockerfile) table. **No `Dockerfile` or `requirements.txt` edits this session.**

### Step 1 — Image pin verification

Confirm the chosen image tag exists on Docker Hub:

```bash
docker pull python:3.13-slim-bookworm
```

If the pull fails or returns a deprecation notice (e.g. the `-bookworm` tag has been superseded by a newer Debian codename), pick the current alternative from https://hub.docker.com/_/python/tags and update the [Image pin format](#image-pin-format) section before continuing.

### Step 2 — Per-dep compatibility audit

For each direct dep in `requirements.txt`, fetch its PyPI JSON metadata and read `info.requires_python` — that's the authoritative field for Python compatibility:

```
https://pypi.org/pypi/<package>/<version>/json
```

Use a browser, `curl`, or WebFetch. For deps where the *current* pin already supports the target Python, no bump is needed. For deps where it doesn't, find the lowest version on PyPI that supports the target Python — that's the new pin.

Capture results in the [Gating deps](#gating-deps-must-bump-in-the-same-commit-as-the-dockerfile) table above. Move any "probably-fine" deps that turn out to be gated into the table too.

**If `nextcord 2.4.2` lacks wheels for the target Python:** stop and escalate per the [Gating deps](#gating-deps-must-bump-in-the-same-commit-as-the-dockerfile) table — this is a whole-plan blocker, not a fix-on-the-spot. Record it in [Blocked / known conflicts](#blocked--known-conflicts) and halt the session. The dep-vuln plan deliberately left nextcord on 2.4.2 (skip, no CVE justification); bumping nextcord is a major-surface change that belongs to a separate effort, not this one.

### Step 3 — Dockerfile `apt` audit (bullseye → bookworm drift check)

The current `python:3.9.7` image is Debian bullseye-based; `python:3.13-slim-bookworm` is Debian bookworm-based with the `-slim` variant (fewer pre-installed packages). The Dockerfile (`Dockerfile:5-9`) currently installs three apt packages plus does a `pip3 install pynacl` with `SODIUM_INSTALL=system`:

- `openssl` — used for the self-signed TLS cert generation at `Dockerfile:16-20`
- `ffmpeg` — required by `Music` cog audio playback
- `libsodium-dev` — required for pynacl source build (`SODIUM_INSTALL=system`)

Verify each is available on bookworm-slim *before* Session 2, not discovered as a Part A build failure:

```bash
# For each of openssl, ffmpeg, libsodium-dev:
docker run --rm python:3.13-slim-bookworm sh -c \
  "apt-get update -qq && apt-cache show <pkg> 2>&1 | head -5"
```

Expected: all three are common Debian packages and should map 1:1 on bookworm-slim. Any unexpected miss or rename: note the substitution in [Blocked / known conflicts](#blocked--known-conflicts) preemptively so Session 2 Part A can apply the Dockerfile fix in the same atomic edit as the `FROM` line.

**openssl 1.1.1 → 3.0.x note:** bullseye ships openssl 1.1.1, bookworm ships openssl 3.0.x. The `-des3` flag at `Dockerfile:16` is deprecated in openssl 3 but still functional; if a future openssl removes it, the cert generation step dies. Not an immediate blocker, just calibration for what to look for if the cert RUN steps red unexpectedly.

**Build-toolchain check (most likely Part A failure mode if missed).** `Dockerfile:9` builds `pynacl` from source. The current `python:3.9.7` image is the *full* image and ships `gcc`, `make`, and `python3-dev` pre-installed; **`python:3.13-slim-bookworm` does not.** Without these, `pip3 install pynacl` fails at the C-extension compile step. Session 2 Part A's Dockerfile edit must add the toolchain to the apt install line. Verify availability on bookworm-slim:

```bash
docker run --rm python:3.13-slim-bookworm sh -c \
  "apt-get update -qq && apt-cache show build-essential python3-dev 2>&1 | head -2"
```

To keep the slim-image size advantage, install the toolchain in the same `RUN` layer as the pynacl build, then purge it afterward (compiled pynacl doesn't need the toolchain at runtime). Suggested Dockerfile shape for Session 2 Part A:

```dockerfile
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        openssl \
        ffmpeg \
        libsodium-dev \
        build-essential \
        python3-dev \
    && SODIUM_INSTALL=system pip3 install pynacl \
    && apt-get purge -y build-essential python3-dev \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*
```

Treat the exact shape as a hint, not a prescription — Session 2 picks the final layout. The load-bearing parts are: (a) toolchain present during `pip install pynacl`, (b) toolchain removed before the layer commits, (c) apt lists cleaned to keep the layer small.

**Completion:** target Python version chosen, image pin confirmed, dep table populated, apt audit done, commit as `chore(plan): Python-bump Session 1 audit results`.

### Session 1 results (2026-07-23) — audit complete, target locked

- **Target locked: Python 3.13** via `python:3.13-slim-bookworm` (pull verified; image reports Python 3.13.14, OpenSSL 3.0.20 preinstalled).
- **Pre-flight:** full Docker suite green (true exit code 0) on the current `python:3.9.7` image before any audit conclusions.
- **Gating deps:** confirmed pins captured in the [Gating deps](#gating-deps-must-bump-in-the-same-commit-as-the-dockerfile) table — numpy 2.5.1, pandas 2.3.3, yt-dlp 2026.7.4, ipython 8.39.0, debugpy 1.8.21; nextcord 2.4.2 verified compatible and unchanged.
- **apt audit (bookworm-slim), all present:** openssl `3.0.20-1~deb12u2` (also preinstalled in the base image, so the cert-gen RUN steps work even without the apt line), ffmpeg `7:5.1.9-0+deb12u1`, libsodium-dev `1.0.18-1+deb12u1`, build-essential `12.9`, python3-dev `3.11.2-1+b1`.
  - **python3-dev caveat:** on bookworm it provides *Debian's Python 3.11* headers — irrelevant to the image's `/usr/local` CPython 3.13, which bundles its own headers. Session 2's toolchain line should install `build-essential` only; **skip `python3-dev`** (the plan's earlier suggested-Dockerfile hint included it — superseded by this finding).
  - **pynacl nuance:** pynacl ≥1.5.0 ships abi3 manylinux wheels (incl. aarch64) that install with no compile; `SODIUM_INSTALL=system` only takes effect on a source build. The toolchain is insurance for a wheel-miss fallback, not the expected path.
- **pip-24 resolver scan (plan rule 8):** checked cross-dep constraints that could newly conflict under the strict resolver — df2img 0.2.10's `pandas>=2.0,<3.0` / `plotly<6.0` / `kaleido==0.2.1` are all satisfied by the confirmed pins; httpx 0.23.3's `httpcore<0.17` has no competing consumer; Pyrebase4 transitives are pure or have cp313 wheels. No predicted `ResolutionImpossible`.
- **Blockers:** none. [Blocked / known conflicts](#blocked--known-conflicts) stays empty; Session 2 is unblocked.

## Session 2 — Execute the bump + wrap-up

**Goal:** atomic Dockerfile + dep bumps, verified green, then update downstream artifacts (dep-vuln plan, dependabot config). Two commits total — Part A (the bump) and Part B (the bookkeeping).

### Part A — Execute the bump

1. Run pre-flight (must be green).
2. Edit `Dockerfile` line 1: `FROM python:3.9.7` → `FROM python:<target-tag-from-Session-1>` (default: `python:3.13-slim-bookworm`).
3. Edit `requirements.txt`: apply every row from the [Gating deps](#gating-deps-must-bump-in-the-same-commit-as-the-dockerfile) table.
4. Rebuild: `docker-compose -f docker-compose-test.yml build`. Expect **~15–25 min on first build** — fresh Python 3.13 base layer download, every wheel re-downloaded under newer pip, and native compilation for pynacl. Subsequent rebuilds with warm layer cache are ~2–5 min. `-slim` may need explicit `apt-get install` lines in the Dockerfile if a transitive native build fails — add them rather than reverting to the full image.
5. Run the full suite: `docker-compose -f docker-compose-test.yml run --rm gbot-test GBotDiscord/test/test.py`.
6. **Run the `main.py` import smoke-test** (verbatim from dep-vuln plan §"`main.py` import smoke-test exception").
7. **Run the prod container startup smoke-test.** The test suite mocks Firebase/Discord — only the prod container proves the bot actually starts on the new interpreter. **Must be prod, not dev:** the dev entrypoint passes `debugpy --wait-for-client` (Dockerfile:28), so main.py hangs forever until a debugger attaches and `on_ready` never fires; the prod entrypoint passes `debugpy --listen` without `--wait-for-client` (Dockerfile:36), so the bot starts immediately and debugpy can attach later. Requires `Shared/gbot.env` and `Shared/serviceAccountKey.json` to be present (per README §"Setup Guide"):
   ```bash
   docker-compose -f docker-compose-prod.yml up -d --build
   # Wait ~30s for entrypoint + Firebase scheduler + every cog's setup() + Discord login.
   # Check for the on_ready log line (main.py:89 logs "GBot logged in as <user>.") and any tracebacks:
   docker logs GBot_7.0_prod 2>&1 | grep -E '(ERROR|Traceback|Exception|GBot logged in as)'
   # Pass: at least one "GBot logged in as ..." line; ZERO ERROR/Traceback/Exception lines.
   docker-compose -f docker-compose-prod.yml down
   ```
   Pass criteria: the `GBot logged in as <user>.` line appears (proves Discord login + every cog's `setup()` ran without error + on_ready listener fired), and there are no tracebacks during startup. A traceback here is a Part A failure even if all unit tests passed. (Note: if the container name differs from `GBot_7.0_prod`, confirm with `docker ps --format '{{.Names}}'`.)
8. Branch on result:
   - **Green** (test suite + main.py smoke-test + prod container smoke-test all pass): commit as `chore(deps): bump Python base image 3.9.7 -> <target>; pair numpy/pandas/yt-dlp/ipython/debugpy bumps`. Tick the Part A boxes. Continue to Part B.
   - **Red** (any of the three failed): `git checkout -- Dockerfile requirements.txt`; ensure the prod container is torn down (`docker-compose -f docker-compose-prod.yml down`); record the failure in [Blocked / known conflicts](#blocked--known-conflicts) below with which check failed and the exact error. **Stop the session** — debugging is a separate effort, and Part B has nothing to do if Part A reverted.

**Functional validation limit (read this before claiming "the bot works"):** Even with all three checks green, the unit tests mock Firebase and Discord, and the prod smoke-test only proves the bot *starts* and reaches `on_ready` — it does NOT exercise individual cog commands, the Quart API endpoints, background `tasks.loop` iterations (Patreon validation, Storms, etc.), GCoin transaction flow, music playback, or any user-visible feature. Per CLAUDE.md: "tests verify code correctness, not feature correctness." For full confidence in "100% functional," after Part A the user must deploy the prod container to a test Discord guild and manually exercise each cog at minimum (Config, GCoin, GTrade, Hype, Music, Patreon, Presence, Storms, Who Dis) plus hit the Quart `/GBot/private/development/` endpoint. This manual validation is *out of scope for the plan itself* but is the only way to claim the bump didn't break a runtime behavior the tests don't cover.

### Part B — Wrap-up

1. Re-run pip-audit in the new image:
   ```bash
   docker-compose -f docker-compose-test.yml run --rm --entrypoint sh gbot-test -c \
     "pip install pip-audit -q && pip-audit"
   ```
2. Update `dependency-vulnerability-patches.md`:
   - CVE baseline summary "Current" column reflects the new totals (yt-dlp's CVE gone; pip/setuptools/wheel CVEs gone or drastically reduced).
   - Blocked / known conflicts: strikethrough the yt-dlp bullet (now cleared) and add a one-line note pointing to this plan's Part A commit hash for traceability.
   - Append a new appendix entry mirroring the Session 6 Appendix format: full pip-audit output + delta paragraph vs. the dep-vuln Session 6 baseline.
3. Extend `.github/dependabot.yml` with the docker ecosystem so future Python-tag bumps get auto-PRs. **Edit, do not replace** — the existing `pip` ecosystem entry (with its `groups.patch-and-minor` block) must stay intact. Append the new entry under the existing `updates:` list. Expected final file state:

   ```yaml
   version: 2
   updates:
     - package-ecosystem: "pip"
       directory: "/"
       target-branch: "develop"
       schedule:
         interval: "weekly"
       open-pull-requests-limit: 10
       groups:
         patch-and-minor:
           update-types:
             - "patch"
             - "minor"
       labels:
         - "dependencies"
       commit-message:
         prefix: "chore(deps)"
     - package-ecosystem: "docker"
       directory: "/"
       target-branch: "develop"
       schedule:
         interval: "weekly"
       labels:
         - "dependencies"
       commit-message:
         prefix: "chore(deps)"
   ```
4. Tick all remaining Progress tracker boxes. Commit as `chore: complete Python base image bump effort (pip-audit + dependabot docker ecosystem)`.
5. **User-side post-merge step (not blocking the commit):** after `modernization-2026` merges to `develop`, visit https://github.com/cgoulart35/GBot/network/updates to confirm dependabot is processing both `pip` and the new `docker` ecosystem. Same caveat as dep-vuln Session 6 — alerts on `develop` are pre-existing GHSA alerts, not evidence of dependabot.yml processing.

## Done when

1. Dockerfile is on the chosen Python target (default: `python:3.13-slim-bookworm`).
2. All rows in [Progress tracker](#progress-tracker) are `done` or `blocked` (with reason).
3. Full Docker test suite green on the new image.
4. `main.py` import smoke-test green.
5. Prod container startup smoke-test green (`GBot logged in as ...` line present in `docker logs`, no tracebacks).
6. `pip-audit` on the new environment shows yt-dlp CVE-2026-26331 cleared *and* the pip/setuptools/wheel base-image CVEs cleared (a ~10-CVE drop from the dep-vuln Session 6 baseline of 19).
7. dep-vuln-patches.md's Blocked section is updated to reflect yt-dlp being cleared, with a pointer to this plan's Part A commit.
8. `.github/dependabot.yml` has both `pip` and `docker` ecosystems configured (existing pip ecosystem preserved with its `groups.patch-and-minor` block intact).

## Blocked / known conflicts

Accumulator — append per Session 2 failure if any dep can't be bumped to its target floor without breaking tests.

*(empty)*

---

## Notes — what this plan deliberately does NOT do

- **No source refactors of `GBotDiscord/src/**`.** Same rule as the dep-vuln plan. If Python 3.12 deprecates something GBot uses (`asyncio.get_event_loop()` removal, `imp` module, etc.) and a cog needs to change, that's a separate effort. *(Pre-check during plan QA on 2026-05-17: grep of `GBotDiscord/src/` found zero matches for the common 3.10+/3.12 deprecation patterns — `get_event_loop`, `asyncio.coroutine`, `imp`, `distutils`, `datetime.utcnow`, `collections.Mapping`/`Iterable`/`Callable`. GBot's source is unlikely to need refactors for this bump; risk is concentrated in deps, not source.)*
- **No `requirements.txt` lockfile adoption.** That's listed in dep-vuln-patches's "Notes on CI/CD reliability" section as a future improvement; still future.
- **No CI/CD additions** (GitHub Actions, etc.). Also from the dep-vuln-patches future-improvements list.
- **No nextcord/quart/Werkzeug major bumps.** Those are still owned by the dep-vuln plan's Sessions 4 and 5. If the dep-vuln plan reaches `Done when` with any of those still `pending` or `blocked`, this plan doesn't pick them up.
- **No Pyrebase4 replacement.** Pyrebase4 4.6.0 is effectively abandoned (last release 2022) and is the load-bearing reason `urllib3==1.26.x` and `requests-toolbelt==0.10.1` stay pinned — clearing 5 unreachable CVEs documented in dep-vuln-patches Blocked. The Python base-image bump will *not* dislodge this; Pyrebase4 imports `requests_toolbelt.adapters.appengine` at module load, which 1.0.0 dropped. **This plan is a prerequisite to any future Pyrebase4 replacement:** the natural replacement target is Google's official `firebase-admin` SDK, which requires modern Python — attempting Pyrebase4 replacement on the current 3.9.7 base would be wasted work since the new SDK wouldn't install. After this plan lands, a "swap to `firebase-admin` (or `pyrebase5`)" effort becomes the next debt-reduction milestone and would close the largest remaining CVE cluster. *(Session 1 note, 2026-07-23: PyPI now shows Pyrebase4 releases up to 4.9.0 — the "abandoned, last release 2022" claim is stale. Whether 4.9.x drops the `requests_toolbelt.adapters.appengine` import is unverified; checking that is the cheap first step of the future Pyrebase effort before reaching for firebase-admin.)*
- **No `.dockerignore` adoption.** The repo has no `.dockerignore` and `Dockerfile:14` does `COPY . .`, so any file present at build time (notably `Shared/serviceAccountKey.json` and `Shared/gbot.env` if the maintainer builds with them in place) gets baked into the image layer. The compose files mount these at runtime, but mounting does not override the baked-in copy — the secret would still live in image history if the image were ever pushed to a registry. This is a pre-existing concern, not introduced by the Python bump, but fits the same modernization arc. A future "add `.dockerignore` (at minimum: `Shared/`, `.git/`, `Logs/`, `__pycache__/`, `*.pyc`) + rebuild + verify secrets aren't in image layers via `docker history --no-trunc`" effort would close it.
