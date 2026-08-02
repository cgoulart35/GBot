---
name: prod-logs
description: Show status and tail recent logs for the running production GBot container. Use to check whether the bot is up and healthy, or to inspect recent output when debugging the live instance.
argument-hint: "[tail-count]"
---

# Production status & logs (read-only)

Shows container status and recent log output for the prod bot. Safe and read-only — it never starts,
stops, or changes anything (the only kind of prod-container interaction allowed on the Pi without
the maintainer).

**Arguments** (`$ARGUMENTS`, optional): a number → how many log lines to tail (default **50**).

## Steps

1. **Always start with status:**

   ```bash
   docker compose -f docker-compose-prod.yml ps
   ```

   If the service isn't listed/`running`, say so — bringing it back is **`/prod-up`** (on the Pi,
   the maintainer's call).

2. **Tail the logs** (substitute the count):

   ```bash
   docker compose -f docker-compose-prod.yml logs --tail=50 gbot-7.0-prod
   ```

3. **Summarize for the user**: whether the container is up, and anything notable in the logs. Lines
   are JSON (`CustomFormatter` in `main.py`); healthy startup includes `GBot logged in as
   GBot#6890.` (`gbot.prod01`; `#9690` is the **dev** bot `gbot.dev01` and means the wrong
   `gbot.env` is deployed); Storms scheduling lines are routine. Quote tracebacks or repeated
   errors verbatim.

## Notes

- **Do not** stream with `-f`/`--follow` by default — it blocks indefinitely. Only if the user
  explicitly wants a live stream, and warn them it won't return on its own.
- To narrow a time window, add `--since=10m` (or `--since=1h`) to the `logs` command.
- Deploy history is separate: `Logs/deploy-watcher.log` in the repo dir on the Pi (gitignored) —
  `tail` it for "new image detected — deploying" / "deploy complete" lines.
- The bot also writes `Logs/GBotDiscord.log` inside the container; `docker compose logs` (stdout)
  carries the same JSON lines.
- On the local dev machine substitute `podman compose` for `docker compose`.
