# Post-modernization Plan 1 — Pi deployment cut-over & legacy updater retirement

**This is the master plan for the first post-`modernization-2026` effort.** It is written to be executed by a fresh session with no prior context, on any model. Driving convention (same as the modernization roadmap): each session reads this file top-to-bottom, finds the first non-done milestone, runs its pre-flight, does that milestone only, and updates the status tracker in the same commit set.

**Why this is first:** the Pi's GBot has been **offline since the 2026-07-24 Phase-2 live-gate window** (recon 2026-07-25 confirmed no GBot container exists on the host at all). Milestone 1 brings the bot back up — on the new image-based CD pipeline instead of the old checkout.

## Recon facts (verified 2026-07-25, read-only over `ssh StormerPi2`)

- Repo at `/home/cgoulart/Code/GBot`, branch `develop` at `72da214` (pre-modernization). **`Shared/gbot.env` is modified + still tracked in that old checkout** — the modernization untracked it (renamed to `gbot.env.example`), so a plain `git reset --hard origin/develop` there would **delete the Pi's real credentials**. Milestone 1 step 1 exists because of this.
- `Shared/serviceAccountKey.json` present on the Pi (never tracked).
- Container runtime is real **Docker** (`/usr/bin/docker`), invokable by the SSH user directly. Unrelated containers share the host — scope every command to GBot's, never `docker stop`/`prune` broadly.
- **GitProjectUpdateHandler (GPUH) runs on the Pi today**: `python3 GitProjectUpdateHandler/main.py`, started by a line in `/etc/rc.local`, clone alongside the other repos under `~/Code`. That file also carries HalloweenEvent's `scripts/start.sh` line (verified present 2026-07-25 — it's the anchor GBot's line goes next to) plus lines for unrelated projects, which stay untouched. No gbot/deploy systemd units; user crontab empty. A `GBot-Docs` clone also lives at `~/Code/GBot-Docs` (relevant to Milestone 2b).
- Image: `ghcr.io/cgoulart35/gbot` (`:latest` + `:<short-sha>`), **public**, arm64; the `publish` CI job fires on every code push to `develop`. Phase 6 removed the prod debug port — prod publishes only the API port (5004).
- Standing convention: **Pi containers are maintainer-managed.** Sessions do read-only checks freely; container mutations and sudo steps below are run by the maintainer (or by the session only with the maintainer explicitly confirming, live, step by step).

## Milestone 1 — Pi cut-over (the deferred Phase-4 on-Pi gate)

Pre-flight: `modernization-2026` merged to `develop`; latest `develop` publish run green (`gh run list --branch develop`); image pullable anonymously.

**Pre-flight already satisfied (2026-07-25):** PR #11 merged → `develop` CI run **30179060538 all green including `publish`** (the first `develop`-triggered publish, as designed). Verified by anonymous `podman pull`: `ghcr.io/cgoulart35/gbot:latest` is **linux/arm64**, digest `sha256:49ed00cf…`, and carries the Phase-6 hardening — `ENTRYPOINT ["python3","GBotDiscord/src/main.py"]` (no debugpy) with `PYTHONPATH=/GBot`. So the Pi can start at step 1 immediately; `docker pull` there should land the same digest.

1. **Back up Pi secrets first** (hard requirement — see recon): `cp Shared/gbot.env ~/gbot.env.bak && cp Shared/serviceAccountKey.json ~/serviceAccountKey.json.bak`.
2. Update the checkout: `git fetch origin && git reset --hard origin/develop`.
3. Restore the env file: `cp ~/gbot.env.bak Shared/gbot.env` (now gitignored). Diff its keys against `Shared/gbot.env.example` for new/renamed vars; `GIT_UPDATER_HOST` stays unset.

   **⚠ Trap hit on 2026-07-25 — the restored file was the DEV config.** The Pi's `Shared/gbot.env` was **not** the prod config: GPUH's `Scripts/UpdateGBot.sh` copied `gbot.env.prod` → built prod → copied `gbot.env.dev` → built dev, so the file left on disk was always **dev**. Restoring it booted `gbot.dev01` (`GBot#9690`) into production; it was online in the test guild and the real guilds saw their bot offline (a bot's presence is global, so "offline in one guild only" always means *a different application is running*).

   The two GPUH configs (`~/Code/GitProjectUpdateHandler/Shared/GBot/gbot.env.{dev,prod}`) are byte-identical **except `DISCORD_TOKEN`** — same `FIREBASE_CONFIG_JSON`, same single `serviceAccountKey.json`, same 22 keys. So both bots share one Firebase project (input to the multi-instance decision in plan 2).

   **Resolution:** both configs are now preserved on the Pi as `Shared/gbot.env.{prod,dev}` with the active one copied to `Shared/gbot.env` (= prod). `GIT_UPDATER_HOST` blanked in all three. `.gitignore` gained a `Shared/gbot.env.*` glob (+ `!Shared/gbot.env.example`) so no instance token can ever be committed — the old rule matched only the exact path `Shared/gbot.env`.
4. First deploy: `sh scripts/deploy.sh` (pulls `:latest`, `docker compose -f docker-compose-prod.yml up -d` → container `GBot_7.0_prod`).
5. Smoke (the Phase-4 prod criteria): `docker logs GBot_7.0_prod` shows `GBot logged in as GBot#9690.` with zero tracebacks; `https://<pi>:5004/GBot/public/leaderboard/` returns 200; maintainer runs one `.toggle`-style command in Discord.
6. ✅ **Done 2026-07-25.** Watcher running (cwd `/home/cgoulart/Code/GBot`), and `/etc/rc.local` **line 26** now carries `su - cgoulart -c "sh /home/cgoulart/Code/GBot/scripts/start.sh"` immediately after HalloweenEvent's line 25; GPUH's line 24 left in place for 2c. Verified `exit 0` still last and `sh -n` clean. Note when checking for the watcher: HalloweenEvent runs a `deploy-watcher.sh` of its own, so identify processes by `readlink /proc/<pid>/cwd`, not by script name — a name-based `pgrep` matches both projects and looks like a duplicate. Original step follows.

   Watcher: `sh scripts/start.sh` (starts `deploy-watcher.sh` detached), then add GBot's line to `/etc/rc.local` **immediately next to HalloweenEvent's existing line** (maintainer preference; that line's presence verified 2026-07-25): `su - cgoulart -c "sh /home/cgoulart/Code/GBot/scripts/start.sh"` adjacent to `su - cgoulart -c "sh /home/cgoulart/Code/HalloweenEvent/scripts/start.sh"` (sudo — maintainer). The same edit session is a natural moment to also drop the GPUH line (formally Milestone 2c step 1).
7. **Gate:** push any small code change to `develop` → publish runs → the watcher redeploys the Pi unattended and the bot comes back logged in. Record the run + timings here.

   **✅ PASSED 2026-07-25** — run [30181799299](https://github.com/cgoulart35/GBot/actions/runs/30181799299) (`test`/`changes`/`audit`/`publish` all green; the `.gitignore` commit correctly classified `code=true`). Nobody touched the Pi:

   | Event | Time (EDT) | Δ |
   |---|---|---|
   | push → CI start | 20:48:34 | — |
   | CI green incl. `publish` | 20:50:28 | 1m54s |
   | watcher: `new image detected` | 20:51:45 | +77s (poll interval 120s) |
   | watcher: `deploy complete` | 20:51:59 | +14s |
   | **push → live in prod** | | **3m25s** |

   Post-redeploy verification: container up on `:latest`, `GBot logged in as GBot#6890.` (prod bot, *not* reverted to dev), guilds `689632030149181468` + `964631679983554653`, 0 ERROR/CRITICAL/WARNING, 0 tracebacks, leaderboard API 200, 0 restarts. `Shared/{gbot.env,gbot.env.prod,gbot.env.dev,serviceAccountKey.json}` all survived `deploy.sh`'s `git reset --hard`, and the tree is clean because the new `Shared/gbot.env.*` glob now ignores the instance configs. The watcher re-exec'd itself afterwards (`exec sh "$0"`), as designed. The replaced image was `sha256:f2d70929…` — the same index digest verified anonymously during pre-flight.

## Milestone 2 — Retire GitProjectUpdateHandler (3 repos)

Do after Milestone 1's gate passes. The updater is dormant from GBot's side (`GIT_UPDATER_HOST` unset; superseded by image-based CD), but the GPUH service itself still runs on the Pi — 2c shuts it down. **Maintainer decision (2026-07-25): GPUH's GitHub repo gets deleted, not archived.**

**2a. GBot (this repo)** — one PR via `/implement-dev-changes`:
- `development_resource.py`: remove the `rebuildLatest` action branch, `sendRequestToGitUpdaterHost()`, and the `doc()` entry.
- `properties.py`: remove `GIT_UPDATER_HOST` (class attr, `startPropertyManager` load, `setProperty` branch).
- Tests: matching removals in `properties_test.py`, `development_resource_test.py`, `api_test.py`.
- Docs: `Shared/gbot.env.example` line; README Setup step 15, the §API `rebuildLatest` rows, and the §Deployment legacy-updater note; CLAUDE.md Quart-API paragraph **and** the accepted-trade-offs entry for the dormant updater (delete it — it's no longer a trade-off once the code is gone).
- Gates: suite + coverage 100% + normal PR review flow.

**2b. GBot-Docs** — clone `cgoulart35/GBot-Docs` (not on the dev machine as of 2026-07-25), grep for updater/`rebuildLatest`/deployment references, rewrite deployment/docs pages to describe the image-based CD flow (README §Deployment is the source of truth), PR.

**2c. GitProjectUpdateHandler shutdown & deletion** — after 2a and 2b confirm no remaining consumers, in this order:
1. Stop the live Pi service: `pgrep -af GitProjectUpdateHandler` → kill the `python3 GitProjectUpdateHandler/main.py` process, and remove its `su - cgoulart -c "sh /home/cgoulart/Code/GitProjectUpdateHandler/start.sh"` line from `/etc/rc.local` (sudo — maintainer, possibly already done alongside Milestone 1 step 6).
2. **Delete the GitHub repo — maintainer-run, destructive; the session pauses here.** (`gh repo delete cgoulart35/GitProjectUpdateHandler` requires the `delete_repo` scope; web UI otherwise. No final-note commit needed since the repo is being deleted, not archived.)
3. **Last, after everything above is verified done**: delete the Pi clone — `rm -rf /home/cgoulart/Code/GitProjectUpdateHandler` (maintainer or maintainer-confirmed).

## Status

| Milestone | Status |
|---|---|
| 1 — Pi cut-over + watcher live | **done 2026-07-25** — bot back online as `gbot.prod01` (`GBot#6890`); watcher live + in `rc.local`; gate passed in 3m25s push→prod |
| 2a — GBot updater-code removal | **done 2026-07-26** — `rebuildLatest` + `sendRequestToGitUpdaterHost` + `GIT_UPDATER_HOST` gone from src, tests, and docs; `httpx` stays (still used by `utils.py`/`firebase.py`). The blank `GIT_UPDATER_HOST=` line left in the Pi's `Shared/gbot.env{,.prod,.dev}` is now inert — harmless, clean up whenever those files are next edited |
| 2b — GBot-Docs deployment-docs rewrite | pending |
| 2c — GPUH shutdown (Pi process + rc.local line) → GitHub repo delete (maintainer, session pauses) → Pi clone delete (very last) | pending (last) |
