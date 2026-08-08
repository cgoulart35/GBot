---
name: prod-down
description: Stop and remove the production GBot container. Use when asked to take down, stop, shut down, or halt the production bot.
---

# Take down the production bot

Stops and removes the prod container (`GBot_8.0_prod`).

> ⚠️ **This takes the live bot offline** in every guild until it's brought back with **`/prod-up`**
> (or the deploy watcher's next new-image deploy). State is safe — it lives in Firebase (external),
> not the container — so nothing is lost. On the Pi (`StormerPi2`) the containers are
> **maintainer-managed**: don't run this over SSH yourself; stopping the live bot is the
> maintainer's call.

## Steps

1. **Stop and remove the container:**

   ```bash
   docker compose -f docker-compose-prod.yml down
   ```

2. **Verify nothing prod is still running:**

   ```bash
   docker compose -f docker-compose-prod.yml ps
   ```

   The list should be empty (no `GBot_8.0_prod`). Report the result.

## Notes

- `down` removes the container and the default network but **not** images or any data — state is in
  Firebase, not the container.
- The deploy watcher only acts on a **new** published image — a bot left `down` stays down until
  then; use **`/prod-up`** to bring it back now.
- If you only need to cycle the container, prefer
  `docker compose -f docker-compose-prod.yml restart` over a full down/up.
- On the local dev machine substitute `podman compose` for `docker compose`.
