---
name: qa
description: Manually QA GBot by running a prod-shaped container built from the working tree, against a REAL Discord token and REAL Firebase. Defaults to gbot.dev01, which runs only where it is being tested and leaves the production bot serving users. QA as gbot.prod01 means stopping it on the Pi and putting it back. Use only for surfaces the test suite can't cover (gateway login, slash-command sync/execution, live Firebase round-trips, real yt-dlp behaviour, the Quart API over HTTPS).
argument-hint: "[up [dev|prod]|logs [N]|ps|down]"
---

# Manual QA (dev identity by default)

GBot has two Discord applications — **`gbot.dev01`** (`#9690`) and **`gbot.prod01`** (`#6890`) —
differing only by `DISCORD_TOKEN`. **Prod runs on StormerPi2** from `docker-compose-prod.yml`. **Dev runs only where it is
being tested**, from `docker-compose-dev.yml`, and is otherwise down.

The rule QA rests on is **one token runs in exactly one place at a time** — it is *not*
"production must be down". So `scripts/qa.sh` defaults to `dev`, which never interrupts real
users. Only QA as prod has to stop the Pi's instance and put it back when you're done.

Reach for `prod` only when the change genuinely needs the production identity — a real guild's
data, or a Patreon-gated path in a really-subscribed server. That one costs real downtime.

> 🔒 **Safety invariants — keep these true:**
> - **One token, one place.** Never start an identity that is already running. For prod, **stop it on
>   the Pi first** and bring it back afterwards. For dev, confirm it isn't running elsewhere. Pi containers
>   are **maintainer-managed**: ask, or act only on an explicit instruction to drive them. Read-only
>   checks over SSH are always fine.
> - **One Firebase project, only partly partitioned.** Per-guild data (`servers/<id>` — config,
>   toggles, hype) is isolated, so dev-guild QA is clean. But **`gcoin/<userId>`, `leaderboards`,
>   `patreon_members` and `trials` are global roots** — a storm win or a trade in the test guild credits a
>   real balance and real leaderboard stats, and adding
>   either bot to a server off the ignore list uses up that server's one free trial for both. **Music writes nothing to Firebase at all**, so music
>   QA is entirely safe on dev.
> - **Prefer `/test`.** The suite + coverage gate is the primary check; QA only what tests can't
>   reach.
> - Never edit or stage `Shared/gbot.env*` / `Shared/serviceAccountKey.json`.

## Steps

1. **Pick the identity and confirm it is free.** Default to `dev`, which should already be down
   everywhere. Check rather than assume, and for prod stop it on StormerPi2 first:

   ```bash
   ssh StormerPi2 'docker ps --format "{{.Names}}" | grep -i gbot'                                  # dev should not be listed
   ssh StormerPi2 'cd /home/cgoulart/Code/GBot && docker compose -f docker-compose-prod.yml down'   # prod QA only
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
   trip needed: `podman exec GBot_prod python3 /tmp/probe.py`.
5. **Tear down.** `sh scripts/qa.sh down`. Keep the container up until the user says they are done
   — a passing scenario is not the same as being finished, and teardown loses the logs. Dev stays
   down afterwards. If this was prod QA, bring it back on the Pi with `sh scripts/deploy.sh` (it
   also re-syncs the checkout) and confirm it logged in as `#6890` before calling QA done. **Leaving
   prod down is the failure mode to watch for**, because nothing on the Pi restarts it: the deploy
   watcher only reacts to a new `:latest` image.

## Notes

- `up` refuses to run without `QA_CONFIRM=yes` — that flag is your attestation that step 1 actually
  happened, not a formality to skip. It also refuses an identity whose env file is missing, and
  refuses any identity name other than `dev`/`prod`.
- **One compose file per instance, each naming its own env file** — `docker-compose-dev.yml` →
  `Shared/gbot.env.dev` (`GBot_dev`, API 5003), `docker-compose-prod.yml` → `Shared/gbot.env`
  (`GBot_prod`, API 5004). `qa.sh` only chooses which to bring up; it overrides nothing inside
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
