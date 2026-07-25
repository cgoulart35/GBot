---
name: test
description: Run GBot's pytest suite (or a single test, the 100% coverage gate, or a dependency CVE audit) the correct way — in an ephemeral container on the gbot-test image. Use when asked to run the tests, check that tests pass, run a specific test, check coverage, or audit dependencies for CVEs.
argument-hint: "[-k filter | GBotDiscord/test/<cog>/<cog>_test.py | coverage | audit]"
---

# Run the tests (or coverage / a CVE audit)

pytest is **not** baked into the runtime image (it installs only `requirements.txt`). Tests run in an
**ephemeral container** on the `gbot-test` image (`docker-compose-test.yml`, `stage` target — runtime
deps only, no entrypoint), with `requirements-dev.txt` (pytest + coverage + pip-audit) installed on
the fly and the repo volume-mounted at `/GBot`, so host edits are picked up without a rebuild. Tests
mock `GBotFirebaseService` and Discord — they **never touch the real database or Discord** and need
no `Shared/gbot.env` / `Shared/serviceAccountKey.json` — safe to run anytime.

**Arguments** (`$ARGUMENTS`):
- empty → run the **whole suite**.
- `coverage` → run the suite under **coverage** and print the report — the **100% line+branch gate**
  for changes touching `GBotDiscord/src` (`fail_under = 100` makes it exit 1 on any regression).
- `audit` → run **pip-audit** over `requirements.txt` (dependency CVE scan) instead of pytest.
- anything else → passed straight to pytest, e.g. `-k storm`, `-x`, or a path like
  `GBotDiscord/test/gcoin/gcoin_test.py`.

## Steps

1. **Run the wrapper.** `scripts/test.sh` does the whole thing deterministically — builds the test
   image, then runs pytest (or coverage / pip-audit) in an ephemeral container. Pick the form from
   `$ARGUMENTS`:

   ```bash
   sh scripts/test.sh                                        # whole suite
   sh scripts/test.sh coverage                               # suite + coverage report (100% gate)
   sh scripts/test.sh audit                                  # pip-audit CVE scan
   sh scripts/test.sh -k storm                               # pytest args pass through
   sh scripts/test.sh GBotDiscord/test/gcoin/gcoin_test.py   # one cog's suite
   ```

   The `gbot-test` image is its own tag, so nothing here ever touches
   `ghcr.io/cgoulart35/gbot:latest` — runs are invisible to the Pi's deploy watcher (which only acts
   on `:latest`) and can never trigger a redeploy.

2. **Report the outcome faithfully.** State pass/fail counts; if anything failed, quote the failing
   test(s) and the assertion/traceback — don't claim green unless the run exited 0. For `coverage`,
   quote any file below 100%. For `audit`, list vulnerable packages with advisory IDs and fixed
   versions (expected state: `No known vulnerabilities found`).

## Notes

- New test modules: name them `GBotDiscord/test/<area>/<x>_test.py` (pytest discovers them
  automatically) **and** wire them into `GBotDiscord/test/test.py`'s suite list — both runners stay
  supported (CLAUDE.md §Tests).
- The archived Halo suites stay ignored (`pytest.ini`'s `--ignore` lines mirror `test.py`'s
  `# DISCONTINUED` imports) — don't "fix" that.
- Engine note: the wrapper auto-picks `docker compose` or `podman compose`. The local dev machine
  runs Podman — if the build can't reach a socket, `podman machine start` first.
