# Plans

Multi-session working plans. Each one is written so a **fresh session with no prior context** can
pick it up: read the file top-to-bottom, find the first non-done milestone, run that milestone's
pre-flight, do **that milestone only**, and update the status tracker in the same commit set.

Plans live in one of two directories, by whether there is work left in them:

- **[`active/`](active)** — has unfinished milestones. This is where "start/continue the next plan"
  goes, in the order listed below.
- **[`completed/`](completed)** — finished or superseded. Kept deliberately, not archived away:
  they carry the recon notes, maintainer decisions, and traps that later work keeps needing. A
  superseded plan says so in its header and names its replacement.

> **This is a public repo.** Plans may name paths and the Pi's SSH alias, but never credential
> locations, host-access mechanics, or anything else that would help someone reach the deployment.
> Report those to the maintainer in conversation instead.

## Active

| Order | Plan | Covers |
|:---:|---|---|
| 1 | [feature-modernization-roadmap.md](active/feature-modernization-roadmap.md) | Post-modernization Plan 2 — the missed-bug sweep and its ledger, the multi-instance/sharding decision (blocked on maintainer discussion), the music/Spotify/whole-bot feature passes, and the App Directory north star. **In progress:** Workstream C is up to C-PR4. |
| 2 | [presentation-and-ux-consistency.md](active/presentation-and-ux-consistency.md) | Post-modernization Plan 3 — make everything the user sees consistent (166 plain-text send sites, no embeds, zero ephemeral replies). Phase 0 is a maintainer design gate. |

## Completed

| Plan | Outcome |
|---|---|
| [modernization-2026-roadmap.md](completed/modernization-2026-roadmap.md) | Master plan for the `modernization-2026` branch — all six phases done, merged to `develop` 2026-07-25. |
| [pi-deployment-and-updater-retirement.md](completed/pi-deployment-and-updater-retirement.md) | Post-modernization Plan 1 — bot live on the Pi via image-based CD and GitProjectUpdateHandler retired across all three repos (2026-07-26). Kept for its recon notes and recorded traps. |
| [100-percent-test-coverage.md](completed/100-percent-test-coverage.md) | Drove `GBotDiscord/src` to 100% line + branch coverage across 15 sessions; the gate is now enforced by `.coveragerc` (`fail_under = 100`). Its one open box is explicitly optional and skipped. |
| [dependency-vulnerability-patches.md](completed/dependency-vulnerability-patches.md) | Multi-session dependency CVE patching; superseded in flight by the modernization roadmap's Phase 1, which carried its results forward. |
| [python-base-image-bump.md](completed/python-base-image-bump.md) | **Superseded** by the modernization roadmap. Session 2 never ran; its Session 1 audit remains the dependency-pin source for Phase 1. |
