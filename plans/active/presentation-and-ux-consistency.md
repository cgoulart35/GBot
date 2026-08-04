# Post-modernization Plan 3 — Presentation & UX consistency ("everything the user sees")

**Scoped from the maintainer's brief (2026-07-26).** Written to be executed by a fresh session with no prior context, on any model. Driving convention: read top-to-bottom, find the first non-done phase, run its pre-flight, do that phase only, update the status tracker in the same commit set.

**Why this is its own plan:** the maintainer asked to review how GBot prints *everything* — messages, command replies, slash replies, embeds — and make it fresh, pretty, and consistent, considering every feature for bugs / enhancements / regressions / customer risk. The survey below found **166 plain-text send sites across 8 live cogs**. That is far more than one session, so it is phased here rather than folded into [feature-modernization-roadmap.md](feature-modernization-roadmap.md) Workstream E — that workstream's "message/embed consistency" bullet now points here.

**Prerequisite:** Plan 1 Milestone 1 (bot live on the Pi via image-based CD) — done. Every phase rides the pipeline: branch → PR → auto-review → merge on maintainer OK → publish → watcher redeploys. Method for each phase: `/implement-dev-changes`. Invariants: **100% line+branch coverage on `GBotDiscord/src`**, pip-audit 0, no regressions to the dual slash/prefix command pattern, and no violation of the accepted trade-offs in CLAUDE.md.

## Survey (measured 2026-07-26 on `develop` @ `51a5de6`)

| Metric | Value |
|---|---|
| Plain-string `.send("…")` sites | **166** |
| `send(embed=…)` sites | **6** |
| Files constructing `nextcord.Embed` | 4 — `utils.py`, `pagination.py`, `gtrade_cog.py`, `gcoin_cog.py` |
| `utils.sendDiscordEmbed` call sites | 13 — **6 are discontinued Halo**; live use is Storms (6) + 1 |
| Distinct colours in use | 8, no semantic mapping — `orange`×9, `yellow`×3, `dark_blue`×3, `green`×2, `blue`×2, `red`×1, `purple`×1, `0xFFFFFF`×1 |
| `ephemeral` usages | **0** |
| `.defer()` usages | 9 |
| `Sorry {author.mention}, …` error strings | 24 (10 in `main.py`'s error handlers, rest in cogs) |

Plain-send counts per cog — this is the migration workload:

| Cog | Sends | Cog | Sends |
|---|---|---|---|
| `gtrade_cog` | 44 | `gcoin_cog` | 14 |
| `whodis_cog` | 35 | `hype_cog` | 7 |
| `storms_cog` | 20 | `config_cog` | 5 |
| `music_cog` | 19 | `patreon_cog` | 1 |

*(`halo_cog`'s 10 are discontinued — leave them commented, per the archived-feature convention.)*

### Findings that are defects, not just style

1. **No ephemeral replies anywhere (customer risk).** Every slash reply is public, including all 24 error messages and personal data like GCoin balances. In a busy guild this is both noise and a privacy wart. Discord's own UX guidance — and App Directory expectations ([feature-modernization-roadmap.md](feature-modernization-roadmap.md) Workstream F) — assume errors and personal responses are ephemeral.
2. **`defer()` coverage is unaudited.** Only 9 sites defer. Any slash command doing Firebase or network I/O before its first response risks the 3-second interaction timeout → user sees "The application did not respond." Needs a per-command audit, not a blanket change.
3. **`sendDiscordEmbed` has a brittle positional signature.** `(context, title, description, color, file, fileURL, thumbnailUrl, deleteAfter)` forces callers to pad — `storms_cog.py` literally passes `…, None, None, None)`. Adding an option breaks every caller. Should be keyword-only.
4. **No semantic colour contract.** Red is used once and not for errors; green twice and not consistently for success. Users can't learn the visual language.

## Design proposal (Phase 1 delivers this; refine with the maintainer at the Phase 0 gate)

A new `GBotDiscord/src/presentation.py` owning **all** user-facing output construction:

- **Semantic colours** — one named constant per intent, not per call site: `ERROR` (red), `SUCCESS` (green), `WARNING` (yellow), `INFO` (Discord blurple or a GBot brand colour), plus per-feature accents that already have identity: Storms → orange (keep, it's established), GCoin → gold, GTrade → blue, WhoDis → purple, Music → green.
- **Builders, keyword-only**: `errorEmbed(...)`, `successEmbed(...)`, `infoEmbed(...)`, `featureEmbed(feature, ...)`. Consistent shape: title, description, optional thumbnail, standard footer (feature name + `GBOT_VERSION`).
- **Send helpers** that work with *both* `nextcord.Interaction` and `Context` — mirroring the existing dual-command `commonX` pattern, so one call site serves slash and prefix. This is the load-bearing constraint: **any helper must accept either type**, exactly as the cogs' `commonX` coroutines already do.
- **`utils.sendDiscordEmbed` becomes a thin back-compat wrapper** over the new builders (or is migrated away entirely once all call sites move). Don't break it mid-migration.
- **Ephemeral policy** (needs maintainer sign-off — Phase 0): errors ephemeral; personal data (balances, inventories) ephemeral; game/social events (Storms, Hype, WhoDis rounds) stay public.

## Phases

### Phase 0 — Design decisions (maintainer gate; no code)

Decide and record **in this file** before any implementation: brand/base colour; whether to go embed-first everywhere or keep short confirmations as plain text (recommendation: **embeds for anything with structure or that a user might screenshot; plain text for one-line acks**); the ephemeral policy above; whether footers carry the version; and **how help is rebuilt** (P-5 — subclass `HelpCommand` and restyle, or own it as a dual slash/prefix command that filters by feature toggle and subscription). Cheap to change now, expensive after 166 call sites move.

### Phase 1 — Build the layer + pilot on the error handlers

Create `presentation.py` with full tests. Migrate the **24 `Sorry {author.mention}` error strings** (10 in `main.py`'s `on_command_error` / `on_application_command_error`, rest in cogs) to `errorEmbed` + ephemeral-on-slash. Highest consistency win per line changed, single reviewable diff, and it exercises the dual Interaction/Context path immediately. **No cog feature output changes in this phase.**

### Phases 2–N — Per-cog migration, one cog per PR

Order chosen for risk and payoff — smallest first to validate the pattern, then highest-visibility:

| Phase | Cog | Sends | Notes |
|---|---|---|---|
| 2 | `config_cog` + `patreon_cog` | 6 | Smallest; proves the pattern end-to-end |
| 3 | `hype_cog` | 7 | Simple, self-contained |
| 4 | `gcoin_cog` | 14 | **Money — highest customer risk.** Balances → ephemeral. Decimal formatting via `utils.roundDecimalPlaces` must not change |
| 5 | `music_cog` | 19 | Coordinate with [feature-modernization-roadmap.md](feature-modernization-roadmap.md) Workstream C — don't migrate output while the architecture is in flux |
| 6 | `storms_cog` | 20 | Already the most embed-native; mostly normalising |
| 7 | `whodis_cog` | 35 | Timed game flow — watch `deleteAfter` / purge interactions |
| 8 | `gtrade_cog` | 44 | **Largest + money.** Uses `pagination.py`; market/trade flows are the most complex UX in the bot |

**Every per-cog phase must also**, per the maintainer's brief, review that cog for bugs / enhancements / regressions / existing defects / customer risk, and append findings to the ledger below — the presentation pass is the natural moment to read every one of that cog's user-facing paths.

### Phase N+1 — Cross-cutting sweeps (after the cogs)

- **`defer()` audit** — every slash command that does I/O before its first response.
- **Pagination consistency** — `pagination.py`'s two embed shapes adopt the semantic colours/footer.
- **Rebuild help (P-5)** — the one send site nobody owns, and the only user-facing surface with **no slash equivalent at all**. See the ledger entry; it wants a design decision (own the rendering vs. keep subclassing nextcord's) at the Phase 0 gate, because a `/help` that answers per-guild is a different object from a static text dump.
- **Final visual QA** — one `/qa` pass exercising each feature's output in a real guild (the suite can't judge "pretty").

## Bug / enhancement ledger

Append per-cog findings here as phases run. Seeded from the survey:

| # | Area | Finding | Severity |
|---|---|---|---|
| P-1 | all slash commands | No `ephemeral` anywhere — errors and personal data (balances) post publicly | customer risk |
| P-2 | all slash commands | `defer()` coverage unaudited; slow I/O commands risk the 3s interaction timeout | correctness |
| P-3 | `utils.sendDiscordEmbed` | Positional signature forces `None, None, None` padding at call sites | maintainability |
| P-4 | all | No semantic colour contract; 8 colours used arbitrarily | consistency |
| P-5 | `main.py:75` — help | **`.help` exists, `/help` does not.** Help is the only user-facing surface with no slash half — it is nextcord's stock `DefaultHelpCommand(width = 100, indent = 10, no_category = 'Other')`, a `commands.Cog`-era prefix command, so a slash-only guild (or one with `toggle_legacy_prefix_commands` off) has **no in-bot help at all** and depends entirely on Discord's command picker. Three defects in one: **(a) no slash parity** — and Workstream F's slash-first criterion makes prefix-only help a directory liability, not just a gap; **(b) the rendering degrades as strings grow** — `width = 100` hard-wraps into monospace blocks at a width no mobile client has, and `indent = 10` pushes long briefs (`PLAY_DESCRIPTION` is now a full sentence after C-PR6/C-PR8) into a ragged column, then `DefaultHelpCommand` splits the whole thing across multiple 2000-char messages; **(c) it lies about availability** — it walks the command tree with no knowledge of `config_queries`' per-guild feature toggles or `isGuildOrUserSubscribed`, so it lists commands the caller will be refused. Maintainer-raised 2026-08-04. Sequenced into Phase N+1 (it needs the presentation layer to exist first), but the **design choice belongs at the Phase 0 gate**: keep subclassing `HelpCommand` and restyle it, or own help outright as a dual slash/prefix `commonHelp` built from the cogs' own metadata — only the latter can filter by toggle/subscription and reuse the semantic embeds | slash-parity gap + consistency |

## Status

| Phase | Status |
|---|---|
| 0 — design decisions | **blocked on maintainer discussion** |
| 1 — `presentation.py` + error-handler pilot | pending |
| 2–8 — per-cog migration (see table) | pending |
| N+1 — defer audit, pagination, visual QA | pending (last) |
