---
name: qa
description: Manually QA GBot by running a prod-shaped container built from the working tree — against the REAL Discord token and REAL Firebase — after the live Pi instance is stopped. Use only for surfaces the test suite can't cover (gateway login, slash-command sync/execution, live Firebase round-trips, the Quart API over HTTPS).
argument-hint: "[up|logs [N]|ps|down]"
---

# Manual QA (live-instance swap)

GBot has **no isolated sandbox**: there is one Discord token and one Firebase RTDB, shared with the
live bot on the Pi. QA therefore works by **swapping which instance is running** — stop the live Pi
container, run a prod-shaped container locally from the working tree, verify, then restore the Pi.
`scripts/qa.sh` bakes in the safety rails: `IMAGE_TAG=qa` (the build is invisible to the Pi's deploy
watcher and never clobbers the local `:latest`) and an explicit `QA_CONFIRM=yes` gate on `up`.

> 🔒 **Safety invariants — keep these true:**
> - **Never two instances at once.** The Pi's GBot container must be stopped before `up`, and Pi
>   containers are **maintainer-managed** — ask the user to stop it (`ssh StormerPi2`, then
>   `docker compose -f docker-compose-prod.yml down` in `/home/cgoulart/Code/GBot`); never stop or
>   start Pi containers yourself. Read-only checks over SSH are fine.
> - **Real data.** Every write lands in the real Firebase RTDB and real Discord guilds — QA actions
>   (commands, toggles) are visible to real users. Keep them small and reversible.
> - **Prefer `/test`.** The suite + coverage gate is the primary check; QA only what tests can't
>   reach.
> - Never edit or stage `Shared/gbot.env` / `Shared/serviceAccountKey.json`.

## Steps

1. **Gate (human):** confirm with the user that the Pi's GBot container is stopped for this window.
   Do not proceed on assumption.
2. **Start from the working tree** (build + run detached; the real secrets must exist in `Shared/`):

   ```bash
   QA_CONFIRM=yes sh scripts/qa.sh up
   ```

3. **Verify startup:**

   ```bash
   sh scripts/qa.sh logs 40
   ```

   Healthy: JSON log lines ending with `GBot logged in as GBot#9690.` and **zero tracebacks**
   (Storms scheduling lines are routine). Quart API check:
   `curl -sk https://localhost:5004/GBot/public/leaderboard/` returns 200 JSON (self-signed cert,
   hence `-k`).
4. **Exercise the change** — the user runs the relevant command(s) in Discord (e.g. a
   `.toggle`-style round-trip); tail the logs again for the outcome.
5. **Tear down and restore:**

   ```bash
   sh scripts/qa.sh down
   ```

   Then have the user bring the Pi instance back (on the Pi: `sh scripts/deploy.sh`, or `/prod-up`
   there). Confirm with them before calling QA done.

## Notes

- `up` refuses to run without `QA_CONFIRM=yes` — that flag is your attestation that step 1 actually
  happened, not a formality to skip.
- The QA container reuses the prod compose file (container name `GBot_7.0_prod`, debugpy 5678 + API
  5004 published locally) but runs the `:qa` image built from the current checkout.
- After further code edits: `sh scripts/qa.sh down`, then `QA_CONFIRM=yes sh scripts/qa.sh up`
  again (compose rebuilds the `:qa` image from the working tree).
- Engine note: the wrapper auto-picks `docker compose` or `podman compose` (local dev = Podman;
  `podman machine start` first).
