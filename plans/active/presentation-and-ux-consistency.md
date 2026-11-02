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

## Decisions (Phase 0, maintainer, 2026-11-01)

These settle the design proposal above, and win wherever the two differ.

| # | Topic | Decision |
|---|---|---|
| 1 | Colour | **Logo green is the brand colour**, used for general and success replies. Errors red, warnings yellow. **No per-feature colours**, so Storms' orange and the proposal's feature accents go. Take the exact hex from the logo in Phase 1 |
| 2 | Embeds | **Mixed.** Embeds for anything with structure or worth a screenshot; plain text for one-line confirmations like "Paused." |
| 3 | Private replies | **Errors and personal data are ephemeral on slash**: refusals, balances, history, inventories. Games and social events stay public. Prefix replies cannot be ephemeral, so they stay public |
| 4 | Others' data | Looking up **someone else's** wallet or history is ephemeral too |
| 5 | Footer | **`GBot 8.0 • Music`**: version from `GBOT_VERSION`, plus the feature name |
| 6 | Help (P-5) | **GBot owns it:** a dual `/help` and `.help` embed that lists only what is available in that server, names what is turned off and how to enable it, and replaces the bare group output (`.config`) and `.help <group>` |
| 7 | Welcome | **One short message on join**, in the system channel or else the first channel it can post in, covering `/config toggle` and `/help`. Stays silent if it cannot post anywhere. Never repeats on a restart |
| 8 | Numbers (P-6) | **Commas plus a unit:** `1,250.00 GCoin`, `3 songs`, `42 wins`. Never shortened, because exact balances matter for trades. Display only |

## Phases

### Phase 0 — Design decisions (maintainer gate; no code) — DONE 2026-11-01, see Decisions above

Decide and record **in this file** before any implementation: brand/base colour; whether to go embed-first everywhere or keep short confirmations as plain text (recommendation: **embeds for anything with structure or that a user might screenshot; plain text for one-line acks**); the ephemeral policy above; whether footers carry the version; and **how help is rebuilt** (P-5 — subclass `HelpCommand` and restyle, or own it as a dual slash/prefix command that filters by feature toggle and subscription). Cheap to change now, expensive after 166 call sites move.

### Phase 1 — Build the layer + pilot on the error handlers — BUILT 2026-11-01

**Scope corrected when built.** There are now **93** `Sorry ...` sends, not 24, with 120 test assertions pinning that text, and some are game results rather than errors ("you guessed incorrectly"). So Phase 1 moved `main.py`'s central handler, which every refusal passes through, into a tested `presentation.sendCommandError`, and fixed P-7 along the way. **Each cog's own errors move in that cog's phase.** Number helpers land with their first use in the GCoin phase, and the logo colour `#7CFC50` was sampled from a screenshot, so swap it if the exact hex turns up. A reply after a public `defer()` stays public, because Discord fixes that when deferring, and the defer audit needs to account for it.

Original scope:


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

- **Welcome message on join** (Decision 7) — **BUILT 2026-11-01.**

- **`defer()` audit** — every slash command that does I/O before its first response.
- **Pagination consistency** — `pagination.py`'s two embed shapes adopt the semantic colours/footer.
- **Rebuild help (P-5) — BUILT 2026-11-01, moved ahead of the cogs at the maintainer's request** — the one send site nobody owns, and the only user-facing surface with **no slash equivalent at all**. See the ledger entry; it wants a design decision (own the rendering vs. keep subclassing nextcord's) at the Phase 0 gate, because a `/help` that answers per-guild is a different object from a static text dump.
- **Final visual QA** — one `/qa` pass exercising each feature's output in a real guild (the suite can't judge "pretty").

**What the 2026-11-01 rollout did, by rule, rather than phase by phase:** every cog's errors and refusals became `sendError` red cards, private on slash. One-line confirmations stayed plain text. All embeds and pagination turned brand green with the standard footer, and `utils.sendDiscordEmbed` became the keyword-only `presentation.sendEmbed`. GCoin amounts use `formatGCoin`, wallets and history and inventories are private, and the welcome message posts on join.

**Settled in QA (maintainer, 2026-11-01):** Who Dis opt-out and report confirmations and Hype setup are private too; config changes, GTrade changes and `/gcoin wallets` stay public. Who Dis game messages are cards, while what players type to each other stays plain. An unexpected crash gets a generic private card. On slash, Who Dis start refusals are private replies rather than a public line plus a DM; prefix keeps the deleted line and DM, because a public reply would reveal who started a game. Amount inputs accept commas, because GBot now displays them. Wording was reviewed per feature: Who Dis headings say what happened while keeping their voice, Storms use one emoji and state GCoin, Music says "song" throughout, the wallet card leads with the balance, and trade requests say how to accept.

**Deliberate exceptions:** Storms' refusals stay public, because they are purged later and a private reply cannot be deleted. A refusal after a public `defer()` (music lookups, for example) stays public because Discord fixes that when deferring.

**Not done:** the per-cog bug review the plan asks for was not repeated cog by cog in this pass, and that review is the plan's one open item.

## Bug / enhancement ledger

Append per-cog findings here as phases run. Seeded from the survey:

| # | Area | Finding | Severity |
|---|---|---|---|
| P-1 | all slash commands | **FIXED 2026-11-01 (PR #46).** No `ephemeral` anywhere — errors and personal data (balances) post publicly | customer risk |
| P-2 | all slash commands | **FIXED 2026-11-01.** Audited with real call counts at about 85ms per Firebase call: most commands answer in under 1s or already defer. `/gcoin send`, `/gtrade destroy`, and completing a `/gtrade buy` or `sell` ran 1.5-2.5s with money already moved, so a timeout invited a second attempt. They now validate first, keeping refusals private, then defer before moving anything. Storms defer outright, as they are public anyway. Blocking Firebase I/O itself remains ledger A-22. `defer()` coverage unaudited; slow I/O commands risk the 3s interaction timeout | correctness |
| P-3 | `utils.sendDiscordEmbed` | **FIXED 2026-11-01 (PR #46).** Positional signature forces `None, None, None` padding at call sites | maintainability |
| P-4 | all | **FIXED 2026-11-01 (PR #46).** No semantic colour contract; 8 colours used arbitrarily | consistency |
| P-5 | `main.py:75` — help | **FIXED 2026-11-01 (PR #46).** **`.help` exists, `/help` does not.** Help is the only user-facing surface with no slash half — it is nextcord's stock `DefaultHelpCommand(width = 100, indent = 10, no_category = 'Other')`, a `commands.Cog`-era prefix command, so a slash-only guild (or one with `toggle_legacy_prefix_commands` off) has **no in-bot help at all** and depends entirely on Discord's command picker. Three defects in one: **(a) no slash parity** — and Workstream F's slash-first criterion makes prefix-only help a directory liability, not just a gap; **(b) the rendering degrades as strings grow** — `width = 100` hard-wraps into monospace blocks at a width no mobile client has, and `indent = 10` pushes long briefs (`PLAY_DESCRIPTION` is now a full sentence after C-PR6/C-PR8) into a ragged column, then `DefaultHelpCommand` splits the whole thing across multiple 2000-char messages; **(c) it lies about availability** — it walks the command tree with no knowledge of `config_queries`' per-guild feature toggles or `isGuildOrUserSubscribed`, so it lists commands the caller will be refused. Maintainer-raised 2026-08-04. Sequenced into Phase N+1 (it needs the presentation layer to exist first), but the **design choice belongs at the Phase 0 gate**: keep subclassing `HelpCommand` and restyle it, or own help outright as a dual slash/prefix `commonHelp` built from the cogs' own metadata — only the latter can filter by toggle/subscription and reuse the semantic embeds. Maintainer flagged the output as ugly on 2026-11-01, and the rebuild must also cover `.help <group>` and the bare group roots like `.config`, which send the same help output since E-PR1 | slash-parity gap + consistency |
| P-6 | all numeric output | **FIXED 2026-11-01 (PR #46).** **Numbers have no display format.** Maintainer-raised 2026-11-01: consider thousands separators and consistent units wherever the bot shows a number, such as GCoin balances and bets, durations, leaderboard stats and queue positions, choosing whatever reads most easily. A single set of helpers in the presentation layer would keep it consistent. Display only: stored values stay as they are, and money still goes through `utils.roundDecimalPlaces` first | consistency |
| P-7 | `main.py` — `on_error` | **FIXED 2026-11-01 (Phase 1).** **Some refused commands get no reply at all.** `on_error` only answers a fixed list of error types, and a missing argument isn't one, so `.config toggle` with no feature logs `feature_type is a required...` and likely says nothing to the user. Seen in the logs during E-PR5's QA, 2026-11-01. Other prefix commands with missing or badly typed arguments should behave the same way, which also covers `.music remove abc`. The deliberate silence for disabled prefix commands stays | consistency |

## Status

| Phase | Status |
|---|---|
| 0 — design decisions | **done 2026-11-01** (see Decisions) |
| 1 — `presentation.py` + error-handler pilot | **built 2026-11-01**, central handler only (see Phase 1) |
| 2–8 — per-cog migration (see table) | **built 2026-11-01** in one pass, at the maintainer's request |
| N+1 — `/help`, welcome message, pagination, visual QA | **done 2026-11-01**; the visual QA was the maintainer's pass on the dev bot |
| N+1 — `defer()` audit (P-2) | **done 2026-11-01**, which completes this plan |
