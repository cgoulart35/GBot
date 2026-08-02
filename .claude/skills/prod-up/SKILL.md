---
name: prod-up
description: Start the production GBot container from the published GHCR image on this host. Use when asked to bring up, start, boot, or restart the production bot.
---

# Bring up the production bot

Starts the single prod container with `docker-compose-prod.yml`: service `gbot-7.0-prod`, container
**`GBot_7.0_prod`** — Quart API on host port **5004** (HTTPS, self-signed) and debugpy on **5678**.

> ⚠️ **This is the live bot.** It logs into Discord with the **real** token and reads/writes the
> **real** Firebase RTDB, and there must only ever be **one** running instance. The deploy target is
> the Pi (`StormerPi2:/home/cgoulart/Code/GBot`), whose containers are **maintainer-managed** —
> never start it on a second host while the Pi instance is (or should be) running. To exercise
> working-tree changes instead, use **`/qa`** (`:qa` image, watcher-safe, human-gated).
>
> Normal deploys happen automatically: CI publishes a new arm64 image to GHCR on every code push to
> `develop`, and the in-repo `scripts/deploy-watcher.sh` pulls it and redeploys (README
> §Deployment). Run this skill for a deliberate manual (re)start on this host.

## Steps

1. **Confirm the secrets are present** (compose loads/mounts both; without them the boot fails):

   ```bash
   ls -1 Shared/gbot.env Shared/serviceAccountKey.json
   ```

   If either is missing, stop and tell the user — on the Pi they live persistently in the repo dir
   (gitignored); do not fabricate them.

2. **Pull the published image and start** (recreates the container; `-d` = detached):

   ```bash
   docker compose -f docker-compose-prod.yml pull
   docker compose -f docker-compose-prod.yml up -d
   ```

   This runs the current **GHCR** image (`ghcr.io/cgoulart35/gbot:latest`) — the same artifact CI
   publishes and the watcher auto-deploys. For a full sync to `origin/develop` (code + image, like
   the auto-deploy), run `sh scripts/deploy.sh` instead. A local source build (`up -d --build`) is
   dev/debug only — the watcher replaces it on the next published image.

3. **Verify it's up:**

   ```bash
   docker compose -f docker-compose-prod.yml ps
   docker compose -f docker-compose-prod.yml logs --tail=20 gbot-7.0-prod
   ```

   Healthy startup: JSON log lines with `GBot logged in as GBot#6890.` and **zero tracebacks**
   (`#6890` is `gbot.prod01`. `#9690` is the **dev** bot `gbot.dev01` — seeing it here means the
   wrong `gbot.env` is in place; see `plans/completed/pi-deployment-and-updater-retirement.md`.)
   (common failure causes: a missing/blank required env var, or a bad `FIREBASE_CONFIG_JSON`).
   Optional API check: `curl -sk https://localhost:5004/GBot/public/leaderboard/` → 200.

## Notes

- Quick restart without re-pulling (e.g. after a container hiccup):
  `docker compose -f docker-compose-prod.yml restart`.
- `restart: unless-stopped` is set — the container comes back on reboot/crash on its own.
- Rollback: `IMAGE_TAG=<short-sha> docker compose -f docker-compose-prod.yml up -d` (image tags are
  the release history).
- On the local dev machine substitute `podman compose` for `docker compose` (CLAUDE.md note).
- To stop the bot, use **`/prod-down`**. To inspect a running bot, use **`/prod-logs`**.
