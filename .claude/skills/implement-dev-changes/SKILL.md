---
name: implement-dev-changes
description: Orchestrate a GBot dev change end-to-end — explore, plan, branch, implement (+ tests), /test (+ the coverage gate), optional /qa, commit, push, open a PR, work the review feedback, then pre-deploy checks, merge (only on your explicit OK), and verify the publish + Pi deploy. Composes the atomic skills and pauses at every human gate. Use for fixes, features, vulnerability fixes, and tooling/dependency upgrades.
---

# Implement a dev change, end to end

> 🚦 **Orchestrator — runs in the main context so you see and steer every step.** It **composes** the
> atomic skills (`/test`, `/qa`, `/prod-logs`) instead of reimplementing them, and it **stops at the
> human gates**: plan approval, the optional QA call, and the **merge**. Branch pushes and opening
> the PR are done for you (they publish no image — only a code merge to `develop` triggers a
> deploy). The merge itself happens **only when you explicitly say so in the conversation** ("we're
> good to merge"); it is never done unprompted.

Works for any change — **fix, feature, vulnerability fix, or tooling/dependency upgrade**; the
phases are the same, only the emphasis shifts (a dep bump leans on `/test audit`; a behavior change
leans on tests and maybe `/qa`).

## Phases

**0 — Frame & precondition.** Restate the goal in one line and classify it (fix / feature / vuln /
upgrade). Confirm a clean working tree (`git status`); surface anything dirty before starting.

**1 — Explore.** For anything beyond a one-file change, dispatch the built-in **Explore** agent
(read-only fan-out) to map the relevant cogs/queries/resources and how the change fits; for a small
localized change, grep/read inline. Report what you found. **Don't edit yet.**

**2 — Plan (gate).** Enter plan mode and draft the **smallest** change that does the job — call out
anything that adds or bumps a dependency (pins here are deliberate; justify it) and list the tests
you'll add or extend. Refine with the user and get explicit approval before writing code.

**3 — Branch.** `git fetch origin`, then create `<type>/<short-kebab-desc>` (`fix/…`, `feat/…`,
`ci/…`, `chore/…`) **from `origin/develop`**. Never implement on `develop` — a code merge to it
publishes an image and deploys to the Pi. *(While the `modernization-2026` integration branch is
active — see CLAUDE.md §Active effort — branch from and PR against that branch instead; nothing
deploys until it merges.)*

**4 — Implement (+ tests).** Follow repo conventions (CLAUDE.md: full `GBotDiscord.src...` package
imports, `#region` banners, camelCase, the dual slash/prefix command pattern with a shared
`commonX`, Decimal money via `utils.roundDecimalPlaces`, all DB I/O through the
`GBotFirebaseService` facade). Add/extend tests in `GBotDiscord/test/<area>/` — new test modules are
auto-discovered by pytest **and must be wired into `test.py`'s suite list** (both runners stay
supported). Keep the diff tight.

**5 — `/test`.** Run **`/test`** until green. Touched `GBotDiscord/src`? Also run
**`/test coverage`** — the 100% line+branch gate must stay green. Touched dependencies? Also
**`/test audit`** (expected: `No known vulnerabilities found`).

**6 — `/qa` (optional — the user decides).** The suite is the primary gate; QA covers only what
tests can't (gateway login, slash-command sync/execution, live Firebase round-trips). It requires
the maintainer to **stop the live Pi bot** for the window (one token, one DB — never two instances),
so ask whether they want it; for pure docs/tests/CI changes, note QA doesn't apply. When wanted,
drive it with **`/qa`** and make sure the Pi instance is restored afterward.

**7 — Self-review + commit (verified code only).** With `/test` (and any `/qa`) green, do a
deliberate pass over the **full diff** (`git diff`) for bugs, scope creep, leftover debug, and
missed doc updates — README/CLAUDE.md sections the change invalidates move in the same commit set.
If the change is part of a new GBot version, bump `GBOT_VERSION` in `Shared/gbot.env.example` and
remind the user to update the real `Shared/gbot.env` on the Pi (you can't see it). Stage
**explicitly by name** — never `git add -A`/`-u`, never stage `Shared/gbot.env` /
`Shared/serviceAccountKey.json`. Commit with the repo's `Co-Authored-By` trailer.

**8 — Push + open PR.** Push the branch and open a **non-draft** PR against `develop` with `gh` (so
the CI auto-review runs immediately — drafts are skipped). Summarize the change and link the PR.

**9 — Work the review loop.** Watch `gh pr checks` (CI `test` + `audit`) and the inline auto-review
comments (`gh pr view --comments`). Address real findings with follow-up commits — re-run `/test`
first, same verify-then-commit order. For anything on the **accepted-trade-offs list in CLAUDE.md**,
don't "fix" it — note it's settled. A local **`/code-review`** pass first is fine; `/ultrareview` is
user-triggered/billed — you can't launch it. Loop until checks are green and the review is clean.
> If the PR edits `.github/workflows/claude-review.yml`, expect its own review to skip with a
> workflow-validation warning (green check, no review) — by design (an accepted trade-off); such
> workflow changes merge on their own first.

**10 — Pre-deploy checks.** Before recommending a merge, verify (report results; don't silently
fix):
- working tree clean on the PR branch; `git log --oneline origin/develop..HEAD` shows exactly what
  will deploy;
- **no secrets** staged/tracked — `git ls-files Shared/gbot.env Shared/serviceAccountKey.json`
  prints nothing and `git diff --cached --name-only` is clean;
- `GBOT_VERSION` handled per phase 7 if it applies;
- `/test` green on the final state.

**11 — Merge (gated on your explicit OK).** Present the pre-deploy results and the PR, and ask
whether to merge. **Merge only if the user affirmatively says so in this turn** (e.g. "yes, merge
it") — `gh pr merge --merge --delete-branch` (use `--squash` if preferred). If they don't, **stop
and hand off** the merge. Never merge, push to `develop`, or deploy unprompted. A code merge to
`develop` is the deploy trigger.

**12 — Verify the build + Pi deploy.** First check what CI did: if the change touched **only**
docs/CI config (`**.md` / `.claude/` / `.github/`), the `changes` gate **skips the publish build** —
nothing redeploys, so confirm `test` + `audit` passed and the merge landed, and you're done.
Otherwise give CI a few minutes to build & publish the arm64 image plus one watcher interval
(default 120s), then confirm the chain — **Pi checks are read-only over SSH (`ssh StormerPi2`);
never start/stop its containers yourself**:
- CI **publish** job succeeded (`gh run list` / `gh run view` on `develop`);
- the watcher deployed it — `tail Logs/deploy-watcher.log` in `/home/cgoulart/Code/GBot` shows
  "new image detected — deploying" / "deploy complete"; `docker compose -f docker-compose-prod.yml
  ps` shows `Up`; logs show `GBot logged in as GBot#6890.` — `gbot.prod01`; `#9690` is the **dev**
  bot and means the wrong `gbot.env` is deployed — with no startup tracebacks (or just run
  **`/prod-logs`** on the Pi).

Report success plainly, or quote the errors if it didn't come up cleanly.

**Done when:** PR merged → CI published the image → the watcher deployed it → the bot is logged in
on the Pi with no tracebacks.
