---
name: qa
description: Manually QA GBot by running a prod-shaped container built from the working tree, against a REAL Discord token and REAL Firebase. Both identities live on the Pi, so a run borrows one — stop it there, run it here, put it back. Defaults to gbot.dev01, which leaves the production bot serving users. Use only for surfaces the test suite can't cover (gateway login, slash-command sync/execution, live Firebase round-trips, real yt-dlp behaviour, the Quart API over HTTPS).
argument-hint: "[up [dev|prod]|logs [N]|ps|down]"
---

# Manual QA (dev identity by default)

GBot has two Discord applications — **`gbot.dev01`** (`#9690`) and **`gbot.prod01`** (`#6890`) —
differing only by `DISCORD_TOKEN`. **Both run on StormerPi2**, from `docker-compose-dev.yml` and
`docker-compose-prod.yml` respectively.

The rule QA rests on is **one token runs in exactly one place at a time** — it is *not*
"production must be down". So QA is a **borrow and return**: stop the identity you want *on the
Pi*, run it here, put it back when you're done. The other identity keeps serving throughout, which
is why `scripts/qa.sh` defaults to `dev` — borrowing dev01 never interrupts real users.

Reach for `prod` only when the change genuinely needs the production identity — a real guild's
data, or a Patreon-gated path in a really-subscribed server. That one costs real downtime.

> 🔒 **Safety invariants — keep these true:**
> - **One token, one place.** Never start an identity that is already running. Both live on the Pi,
>   so **check and stop the matching one there first**, and bring it back afterwards. Pi containers
>   are **maintainer-managed**: ask, or act only on an explicit instruction to drive them. Read-only
>   checks over SSH are always fine.
> - **One Firebase project, only partly partitioned.** Per-guild data (`servers/<id>` — config,
>   toggles, hype) is isolated, so dev-guild QA is clean. But **`gcoin/<userId>`, `leaderboards`
>   and `patreon_members` are global roots** — a storm win or a trade in the test guild credits a
>   real balance and real leaderboard stats. **Music writes nothing to Firebase at all**, so music
>   QA is entirely safe on dev.
> - **Prefer `/test`.** The suite + coverage gate is the primary check; QA only what tests can't
>   reach.
> - Never edit or stage `Shared/gbot.env*` / `Shared/serviceAccountKey.json`.

## Steps

1. **Pick the identity, then free it on the Pi.** Default to `dev`. Whichever you pick, stop *that*
   instance on StormerPi2 first and confirm it is down — do not proceed on assumption:

   ```bash
   ssh StormerPi2 'cd /home/cgoulart/Code/GBot && docker compose -f docker-compose-dev.yml down'   # or -prod
   ```
2. **Start from the working tree** (the matching secret must exist in `Shared/`; `gbot.env.dev` is
   copied from the Pi and is gitignored):

   ```bash
   QA_CONFIRM=yes sh scripts/qa.sh up          # gbot.dev01 — the default
   QA_CONFIRM=yes sh scripts/qa.sh up prod     # gbot.prod01 — Pi must be stopped
   ```

3. **Verify startup:**

   ```bash
   sh scripts/qa.sh logs 40
   ```

   Healthy: JSON log lines ending in `GBot logged in as GBot#<tag>.` and **zero tracebacks**
   (Storms scheduling lines are routine). **The tag must match the identity you asked for** —
   `#9690` is `gbot.dev01`, `#6890` is `gbot.prod01`. A mismatch means the wrong env file was
   picked up; compare `Shared/gbot.env*` md5s against the Pi's before trusting anything you see.
   Quart API check: `curl -sk https://localhost:5004/GBot/public/leaderboard/` returns 200 JSON
   (self-signed cert, hence `-k`). Note `hypercorn.error` is a logger *name*, so an INFO line from
   it is the server starting, not a failure.
4. **Exercise the change** — the user runs the relevant command(s) in Discord; tail the logs again
   for the outcome. Where the behaviour under test is a third-party return shape rather than our
   own branching (yt-dlp's, say), probe it directly in the container instead — no Discord round
   trip needed: `podman exec GBot_8.0_prod python3 /tmp/probe.py`.
5. **Tear down and return the identity.** `sh scripts/qa.sh down`. Keep the container up until the
   user says they are done — a passing scenario is not the same as being finished, and teardown
   loses the logs. Then bring the borrowed instance back up on the Pi and confirm it logged in
   with the expected tag before calling QA done — `sh scripts/deploy.sh` for prod (it also
   re-syncs the checkout), or `docker compose -f docker-compose-dev.yml up -d` for dev. **Leaving
   an identity down is the failure mode to watch for**, because nothing on the Pi restarts it:
   the deploy watcher only reacts to a new `:latest` image, and only for prod.

## Notes

- `up` refuses to run without `QA_CONFIRM=yes` — that flag is your attestation that step 1 actually
  happened, not a formality to skip. It also refuses an identity whose env file is missing, and
  refuses any identity name other than `dev`/`prod`.
- **One compose file per instance, each naming its own env file** — `docker-compose-dev.yml` →
  `Shared/gbot.env.dev` (`GBot_8.0_dev`, API 5003), `docker-compose-prod.yml` → `Shared/gbot.env`
  (`GBot_8.0_prod`, API 5004). `qa.sh` only chooses which to bring up; it overrides nothing inside
  them. `logs`/`ps`/`down` cover **both** files and take no identity argument, so `down` can never
  leave a container running because you named the wrong side.
- `IMAGE_TAG=qa` keeps `up prod` off `:latest`, so the Pi's deploy watcher can never see the build.
  The dev compose names no image at all, so its build is already invisible.
- The dev target runs under debugpy but **does not block on it** — the bot starts on its own and
  you attach only if you want to, through the loopback-bound port.
- After further code edits: `sh scripts/qa.sh down`, then `QA_CONFIRM=yes sh scripts/qa.sh up`
  again (compose rebuilds the `:qa` image from the working tree).
- `scripts/qa.sh`/`test.sh` always `cd` to the repo root, so a run builds **whatever branch the
  shared checkout is on** — check that before `up` if another session is working in the same tree.
- Engine note: the wrapper auto-picks `docker compose` or `podman compose` (local dev = Podman;
  `podman machine start` first).
