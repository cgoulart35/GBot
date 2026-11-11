# Plans

Multi-session working plans. Each one is written so a **fresh session with no prior context** can
pick it up: read the file top-to-bottom, find the first non-done milestone, run that milestone's
pre-flight, do **that milestone only**, and update the status tracker in the same commit set.

Plans live in one of two directories, by whether there is work left in them:

- **[`active/`](active)** — has unfinished milestones. This is where "start/continue the next plan"
  goes, in the order listed below. **Which milestone each is currently on is tracked in
  [`CLAUDE.md`](../CLAUDE.md) §Active effort, not here** — this index is deliberately free of
  status that churns, so a milestone landing only ever edits one file.
- **[`completed/`](completed)** — finished or superseded. Kept deliberately, not archived away:
  they carry the recon notes, maintainer decisions, and traps that later work keeps needing. A
  superseded plan says so in its header and names its replacement.

> **This is a public repo.** Plans may name paths and the Pi's SSH alias, but never credential
> locations, host-access mechanics, or anything else that would help someone reach the deployment.
> Report those to the maintainer in conversation instead.

## Active

| Order | Plan | Covers |
|:---:|---|---|
| 1 | [gbot-8.3.md](active/gbot-8.3.md) | GBot 8.3 — exact permissions and a setup check, a 7-day trial, time zones, reminders, and the agent acting through commands. |

## Completed

| Plan | Outcome |
|---|---|
| [feature-modernization-roadmap.md](completed/feature-modernization-roadmap.md) | Post-modernization Plan 2 — the missed-bug sweep and its ledger, the multi-instance decision, the music, Spotify and whole-bot passes. Complete 2026-11-08; its agent backlog moved to the 8.3 plan. |
| [ui-ux-overhaul-8.2.md](completed/ui-ux-overhaul-8.2.md) | GBot 8.2's UI/UX overhaul: every feature one command opening a card of buttons, right-click menus, reporting, Storms v2, the music card and Help as the front door. Shipped 2026-11-08 (PR #64) |
| [presentation-and-ux-consistency.md](completed/presentation-and-ux-consistency.md) | Post-modernization Plan 3 — a shared presentation layer, private errors, `/help`, the welcome message, the `defer()` audit, the per-cog bug review and the fun pass. All done 2026-11-02 |
| [modernization-2026-roadmap.md](completed/modernization-2026-roadmap.md) | Master plan for the `modernization-2026` branch — all six phases done, merged to `develop` 2026-07-25. |
| [pi-deployment-and-updater-retirement.md](completed/pi-deployment-and-updater-retirement.md) | Post-modernization Plan 1 — bot live on the Pi via image-based CD and GitProjectUpdateHandler retired across all three repos (2026-07-26). Kept for its recon notes and recorded traps. |
| [100-percent-test-coverage.md](completed/100-percent-test-coverage.md) | Drove `GBotDiscord/src` to 100% line + branch coverage across 15 sessions; the gate is now enforced by `.coveragerc` (`fail_under = 100`). Its one open box is explicitly optional and skipped. |
| [dependency-vulnerability-patches.md](completed/dependency-vulnerability-patches.md) | Multi-session dependency CVE patching; superseded in flight by the modernization roadmap's Phase 1, which carried its results forward. |
| [python-base-image-bump.md](completed/python-base-image-bump.md) | **Superseded** by the modernization roadmap. Session 2 never ran; its Session 1 audit remains the dependency-pin source for Phase 1. |
