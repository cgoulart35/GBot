# GBot 8.3 — permissions, a trial, time zones, reminders and an agent that acts

**Status: designing (2026-11-08).** Nothing is built. A fresh session: read the decisions, then carry on at the first unticked item.

**How it ships:** one branch, `feat/gbot-8.3`, and one PR, with a commit (or a few) per milestone, as 8.2 did. Each milestone ends with `/test`, `/test coverage` and a `/qa` pass on `gbot.dev01` before the next one starts, so problems are found while the change is fresh. Merge only on the maintainer's OK, after the last milestone.

## Decisions

| # | Decision | Made |
|---|---|---|
| D-1 | GBot stays invite-only through Patreon. | maintainer, 2026-11-08 |
| D-2 | **7-day trial**, once per server: a server someone adds GBot to gets every feature for 7 days before it needs a subscription. | maintainer, 2026-11-08 |
| D-3 | **Per-person time zone**, used by reminders and the agent. | maintainer, 2026-11-08 |
| D-4 | **Reminders:** a command and an agent tool over one engine. Delivered where the person chooses (the channel they set it in, or a DM). Members remind themselves; admins can also remind a role or everyone. One-off, daily and weekly. | maintainer, 2026-11-08 |
| D-5 | **The agent acts** at three levels, `read`, `safe` and `all`, chosen by admins per server with channel overrides, default `off`. `all` always goes through a confirm button that only the person who asked can press. | maintainer, 2026-11-08 |
| D-6 | GCoin stays points with no cash value: never bought, sold or cashed out, and never a cryptocurrency. | maintainer, 2026-11-08 |
| D-7 | Version 8.3, not 9.0. | maintainer, 2026-11-08 |

## Recon: what GBot actually needs from Discord

From a read of every Discord call in `GBotDiscord/src` (Halo excluded) on 2026-11-08.

### Permissions (the invite link)

| Permission | Needed by | Without it |
|---|---|---|
| View Channels | everything | nothing works |
| Send Messages, Send Messages in Threads | everything that posts | silent failure |
| Embed Links | every card (all output is embeds) | cards don't show |
| Attach Files | leaderboard image (`df2img`), GTrade item images | those fail |
| Read Message History | agent context (`agent_cog.py:792`), reports (`config_cog.py:395`), `fetch_message` on cards | agent loses context, cards can't be edited after restart |
| Add Reactions | Hype reactions, agent reactions | those fail |
| Use External Emojis | Hype responses with other servers' emoji | emoji show as text |
| Connect, Speak | Music | no music |
| Manage Messages | Storms and Who Dis tidy-up, which deletes members' messages and bulk-deletes (`utils.purgePreviousMessages`) | tidy-up fails |
| Manage Roles | Who Dis role (`whodis_cog.py:303,360`); only roles **below GBot's own** | Who Dis can't start, and admins get a vague message |
| Mention Everyone | agent role pings when its `mentions` setting allows, and admins' role reminders (M3) | neither can ping a role |

**Not needed: Administrator**, Manage Server, Manage Channels, Kick, Ban, Manage Webhooks, Manage Events.

Discord's role rule: Manage Roles only reaches roles under the bot's highest role. Today `utils.addRoleToUser` swallows the error and returns `False`. The maintainer's own servers have GBot's role at the top, so this hasn't bitten there; it will in a server someone else sets up.

### Intents

`main.py:55` asks for `nextcord.Intents.all()`. All three privileged intents are really used:

- **Message Content:** prefix commands, Hype, the agent, Who Dis relaying DMs, reports quoting a message.
- **Server Members:** `guild.fetch_members()` (Who Dis pairing, name lookups, the server ranking), `guild.members`.
- **Presence:** Who Dis only pairs people who are online or idle (`utils.getOnlineAndIdleUsers`, `whodis_cog.py:296`), and 🎧 Follow Spotify reads activities (`music_cog.py:210,526`).

GBot is far below the size where Discord reviews these, so keeping all three costs nothing.

### The agent today

Tools in `agent_client.TOOLS`: react, save/update/forget a memory, `get_feature_guide`, stay silent. It is told the time in UTC (`agent_cog.now`) and uses a time zone only if a memory mentions one. Lookups and music control were built once on the deleted `backlog/agent-lookups-and-music` branch: commits `e75d0ed` (lookups) and `989387e` (music), still in `develop`'s history, predating the settings redesign.

### Roadmap leftovers

Checked 2026-11-08: the feature-modernization roadmap's remaining items are all closed in its text (API parity, the schema write-up, the dead activity page, all 2026-11-02), but its status table still says "pending". Its agent backlog moves into this plan. M1 tidies the roadmap and moves it to `completed/`.

## M1 — Permissions, intents and housekeeping

- [x] `main.py`: `server_setup.gatewayIntents()`, only the intents GBot uses, instead of `Intents.all()`. (`Intents.default()` plus the three privileged ones would have been identical to `all()`; the narrower set also drops typing, invites, webhooks, integrations, moderation, scheduled events and AutoMod.)
- [x] The invite link with exactly the permissions table (`permissions=275150007360`), in the README's setup section and given to the maintainer to replace the one patrons get.
- [x] **Setup check** on `/config`'s card: a "⚠️ Setup" field, shown only when something is wrong, one line per problem with its fix. Checks, for each feature that's on: GBot can view, post and embed in the feature's channel; Manage Messages there for Storms and Who Dis; Manage Roles and its role above the Who Dis role; Connect and Speak are allowed for music (server-wide).
- [x] Who Dis checks `server_setup.roleProblem` before giving or taking its role, so the member is told an admin has to fix it and the admin channel gets the fix. (`removeRoleFromAllUsers` is only used by the discontinued Halo code, so it's left alone.)
- [x] Setting the Who Dis role refuses a role at or above GBot's, saying why.
- [x] Housekeeping:
  - [x] Roadmap A-17: mark the Hype freeze fixed (`regex` with a time limit).
  - [x] Roadmap status table: E is done; add the agent backlog's move here; move the roadmap to `plans/completed/`.
  - [x] A `LICENSE` file: "Copyright (c) 2021-2026 Christopher Goulart. All rights reserved."
- [x] Tests; `/qa` (2026-11-09): GBot's role moved below the Who Dis role shows the setup warning, the picker refuses the role, and `/whodis` explains it. Without Administrator the invite's permissions are enough and a missing channel permission is named. GBot gives and takes the role for an admin ranked above it.

## M2 — 7-day trial

Today `predicates.ensureSubscribed` checks the Patreon table and the ignore list, and `Patreon.patreon_validation` (every 24 hours) leaves any other server.

- [ ] One place, `access.py`, answers "may this server use GBot, and why": ignore list → Patreon → trial → no. `ensureSubscribed`, `recheck` and `patreon_validation` all ask it.
- [ ] A trial starts when GBot joins a server that has never had one, recorded by server ID in a top-level table (`trials/<serverId>/{started}`), kept forever, so leaving and re-adding doesn't restart it. Servers GBot is already in when this ships get no trial: they're subscribed or ignored already.
- [ ] While on trial: everything works. The welcome message says "Free for 7 days", and `/config` shows the days left.
- [ ] Reminders to subscribe: in the admin channel (or the welcome channel if none) at 2 days left and on the last day.
- [ ] **When it ends:** commands answer with a "Your free trial has ended" card, a 💳 Subscribe on Patreon link and a short how-to (`/patreon` with the server's ID). Running games finish. After 3 more days without subscribing, `patreon_validation` leaves as it does today, and the server's settings go with it.
- [ ] Subscribing during or after the trial switches the server over at once, with nothing lost.
- [ ] Settings the maintainer can change without a release: `TRIAL_DAYS` (default 7), `TRIAL_GRACE_DAYS` (default 3), both mutable through `setProperty`.
- [ ] Dev and prod share one database (roadmap Workstream B), so a dev test writes a real trial record for its server. Acceptable, as the test servers are on the ignore list; note it in `/qa`.
- [ ] Tests; `/qa`: add `gbot.dev01` to a server not on the ignore list, then shorten `TRIAL_DAYS` through the API to watch it end.

## M3 — Time zones and reminders

Design round first, with mockups like 8.2's: the reminders card, the time zone picker, and what a delivered reminder looks like.

**Time zones (D-3)**
- [ ] Stored per person, across servers: `users/<userId>/timezone` as an IANA name (`America/New_York`). Python's `zoneinfo` handles summer time.
- [ ] Set from 🌍 Time zone on the reminders card: a dropdown of common zones plus a form for any other name, checked against `zoneinfo`.
- [ ] The agent is told the sender's local time when it's set, instead of only UTC, and can set it ("I'm in Denver").
- [ ] With none set, reminders ask for one first.

**Reminders (D-4)**
- [ ] `/remind [when] [what] [repeat] [where]`, matched by `.remind`. No fields opens the card; with fields it sets one and says when it will fire in the person's time ("🔔 Reminder set for Thu, Nov 13 at 8:00 PM").
- [ ] `when` takes plain times: "in 2 hours", "tomorrow 9am", "Thursday 8pm", "Dec 25 10:00". Parsing in code, without the agent, so the command works on its own. Settle in the design round: a small parser of our own, or a library (a new dependency to justify).
- [ ] The card: your reminders (when, what, repeat, where), ➕ New (a form), 🗑️ Delete, 🌍 Time zone, ✖️ Close.
- [ ] `repeat`: none, daily, weekly.
- [ ] `where`: here (the channel it was set in, pinging you) or DM. A DM that fails falls back to the channel.
- [ ] Admins can target a role or everyone: the reminder pings it, with allowed mentions opened for that one message only.
- [ ] Storage: `reminders/<serverId>/<reminderId>/{userId, channelId, text, nextAt (UTC), repeat, where, target}`. A `tasks.loop` every 30 seconds sends what's due; a repeat moves `nextAt` forward in the person's time zone; one that came due while GBot was down sends late, saying so.
- [ ] Limits: 25 per person per server, text 500 characters, nothing over a year ahead.
- [ ] Removing GBot from a server deletes its reminders; a member who left has theirs skipped and deleted.
- [ ] Feature emoji 🔔, its own `toggle_reminders` (default on), a guide in `help/guides.py`, `commands.json`, README tables, `command_tree_test`.
- [ ] Tests; `/qa`: one-off in channel and DM, daily, a role reminder, a restart with one due, a time zone change.

## M4 — The agent acts: `read` and `safe`

- [ ] **`abilities`** setting in `/agent`'s settings, server-wide with channel overrides like its others: `off` (default), `read`, `safe`, `all`. Separate from the agent being on.
- [ ] Only tools allowed at the channel's level are sent to Claude, so a lower level can't be talked past.
- [ ] `read` tools: someone's wallet, the server ranking, a market search ("items under 10 GCoin", more than today's 15-row limit), someone's items, the music queue and now playing, which features are on, someone's reminders (only the sender's own unless an admin asks). Rebuilt from `e75d0ed` onto the current settings.
- [ ] `safe` tools: play, skip, pause, resume, stop, shuffle (sender must be in GBot's voice channel, as the card requires), and set, list or delete the sender's own reminders and time zone. Rebuilt from `989387e`. Music's own messages and the agent's reply mustn't double up: the action reports to the now-playing card, as the 8.2 card does, and the agent's reply only adds what the card doesn't say.
- [ ] Every tool runs the same checks as its command (`predicates.recheck` with the feature and admin flags) for the sender, not the agent.
- [ ] Update CLAUDE.md's agent section: what it can now do, and why it's still safe.
- [ ] Tests; `/qa`: each level per channel, a member without voice asking to skip, "what's my balance", "play something chill".

## M5 — The agent acts: `all`

- [ ] **Confirm, posted by code:** "Send 5.00 GCoin to Bob? You'll have 120.00 left." with ✅ Confirm and ❌ Cancel. Only the sender can press, it expires in a few minutes, and every press rechecks permissions.
- [ ] **`run_command`:** one tool that names a command and its arguments. Code finds the real command, checks it for the sender, and runs its `commonX` through `CardReply` after confirm. Commands that need typing (a Claude key, an item listing) never take those values from chat: the confirm opens the command's own form instead.
- [ ] Never through the agent: anything acting on the agent's own settings or key, and the admin-only `Patreon` and API operations.
- [ ] Settle while building: the prefix-commands toggle (it guards the prefix variant only, so it doesn't apply here), and the list of commands it can run, kept in one place and tested against the command tree.
- [ ] Tests; `/qa`: a money send confirmed and cancelled, someone else pressing Confirm, a member asking for an admin command, a confirm after a feature was turned off.

## M6 — Live checks left over, and release

- [ ] Still never tried live from earlier rounds: agent role pings with "Mention Everyone", the private `/agent memory` list's page buttons, threads following their channel's agent settings.
- [ ] `version.py` to 8.3; changelog in the README and `site/_includes/changelog.md` split into New and Changed; site commands and feature tables.
- [ ] Full `/qa` regression pass on dev, then the PR, review, merge on the maintainer's OK, deploy check (`GBot#6890`).
- [ ] Announcement in the 8.1 layout.
- [ ] Move this plan to `completed/`.
