# GBot 8.3 — permissions, a trial, time zones, reminders and an agent that acts

**Status: shipped (2026-11-11, PR #65).** Every milestone is done and 8.3 is live on the Pi. Kept for its decisions, QA notes and the "After 8.3" list.

**How it ships:** one branch, `feat/gbot-8.3`, and one PR, with a commit (or a few) per milestone, as 8.2 did. Each milestone ends with `/test`, `/test coverage` and a `/qa` pass on `gbot.dev01` before the next one starts, so problems are found while the change is fresh. Merge only on the maintainer's OK, after the last milestone.

## Decisions

| # | Decision | Made |
|---|---|---|
| D-1 | GBot stays off Discord's App Directory and takes no Discord payments; subscriptions stay on Patreon. ~~Invite-only~~: from 2026-11-09 the invite link is on the website, with the 7-day trial. | maintainer, 2026-11-08, revised 2026-11-09 |
| D-2 | **7-day trial**, once per server: a server someone adds GBot to gets every feature for 7 days before it needs a subscription. | maintainer, 2026-11-08 |
| D-3 | **Per-person time zone**, used by reminders and the agent. | maintainer, 2026-11-08 |
| D-4 | **Reminders:** a command and an agent tool over one engine. Delivered where the person chooses (the channel they set it in, or a DM). Members remind themselves; admins can also remind a role or everyone. One-off, daily and weekly. | maintainer, 2026-11-08 |
| D-5 | **The agent acts** at three levels, `read`, `safe` and `all`, chosen by admins per server with channel overrides, default `off`. `all` always goes through a confirm button that only the person who asked can press. | maintainer, 2026-11-08 |
| D-6 | GCoin stays points with no cash value: never bought, sold or cashed out, and never a cryptocurrency. | maintainer, 2026-11-08 |
| D-7 | Version 8.3, not 9.0. | maintainer, 2026-11-08 |
| D-8 | GBot's own trial is the only one: Patreon's free trial on the tier stays off, as GBot can't see it and the two would stack. | maintainer, 2026-11-09 |
| D-9 | A **lapsed subscription** is handled like an ended trial: refused with how to renew, one notice, and `GRACE_DAYS` before GBot leaves, instead of leaving within a day without a word. | maintainer, 2026-11-09 |

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

- [x] One place, `access.py`, answers "may this server use GBot, and why": ignore list → Patreon → trial → no. `ensureSubscribed`, `recheck` and `patreon_validation` all ask it.
- [x] A trial starts when GBot joins a server that has never had one, recorded by server ID in a top-level table (`trials/<serverId>/{started}`), kept forever, so leaving and re-adding doesn't restart it. Servers GBot is already in when this ships get no trial: they're subscribed or ignored already.
- [x] While on trial: everything works. The welcome message says "Free for 7 days", and `/config` shows the days left.
- [x] Reminders to subscribe: in the admin channel (or the welcome channel if none) at 2 days left, on the last day, and when it ends (with the date GBot leaves). Hourly, each recorded so none repeats.
- [x] **When it ends:** commands (and `/help`) answer with a "Your free trial has ended" card, a 💳 Subscribe on Patreon link and a short how-to (`/patreon` with the server's ID). Running games finish. Storms start no new ones and Hype stops replying, as the agent already did; the same goes for any server not subscribed. After 3 more days without subscribing, `patreon_validation` leaves as it does today, and the server's settings go with it.
- [x] Subscribing during or after the trial switches the server over at once, with nothing lost.
- [x] Settings the maintainer can change without a release: `TRIAL_DAYS` (default 7), `GRACE_DAYS` (default 3, shared with lapses), both mutable through `setProperty`.
- [x] **Lapses (D-9):** the daily check marks a patron who lost the role `lapsed` instead of dropping them. Their server is refused with how to renew, told once by whichever bot is in it, and kept `GRACE_DAYS`; the role coming back, or `/patreon` again, clears it.
- [x] Dev and prod share one database (roadmap Workstream B), so a dev test writes a real trial record for its server. Acceptable, as the test servers are on the ignore list; note it in `/qa`.
- [x] Tests; `/qa` (2026-11-09): `gbot.dev01` added to a server off the ignore list started a trial (welcome and `/config` show it); `TRIAL_DAYS` 0 ended it (commands and `/help` refuse alike with the Patreon button, an open card still works, Hype goes quiet); `GRACE_DAYS` 0 and `syncSubscribers` left; re-adding started no second trial. Not seen live: the hourly reminders, and a lapse, which needs a real patron losing the role.

## M3 — Time zones and reminders

Design round first, with mockups like 8.2's: the reminders card, the time zone picker, and what a delivered reminder looks like.

**Design round, settled 2026-11-09** (mockups `gbot-8.3-m3-mockups.html`, in the session scratchpad, not the repo):
- **Card** (`/remind`, private): your reminders here, soonest first, in your time; a dropdown to pick one; ➕ New, 🗑️ Delete, 🌍 Time zone, 📖 How it works, ✖️ Close. Admins also get 👥 Server's: everyone's reminders here, with Delete, so a role ping can be stopped.
- **➕ New**: a form (When, What), then the card becomes a draft showing exactly when it fires, with 🔁 Repeats (once, daily, weekly), 📍 Where (here or DM) and, for admins only, 👥 Who to ping (me, a role, everyone); ✅ Set it, ✏️ Edit, ↩️ Back.
- **Fast path**: `/remind when what [repeat] [where] [role]` sets it and replies privately "🔔 Reminder set for Tue, Nov 10 at 9:00 AM (in 13 hours)" with ↩️ Undo and 🔔 My reminders. Prefix takes the time quoted: `.remind "tomorrow 9am" call the dentist`. A time it can't read is refused with examples.
- **Reading times**: a small parser of our own, no new dependency.
- **🌍 Time zone**: a dropdown of about 20 zones, each labelled with its current time so people match their own clock, plus ✏️ Other (a form for any IANA name). Asked for first when a reminder is made with none set.
- **Changing your time zone moves your reminders with you**: 9am stays 9am in the new zone.
- **Delivered**: the target pinged above an embed (🔔 the text, who set it, the repeat, the next time). One-offs get 💤 10 min, 💤 1 hour, 💤 Tomorrow; repeats get ⏭️ Skip next and 🛑 Stop repeating (and 💤 10 min by DM). Only the person it's for, or whoever set a role reminder, can press them. One due while GBot was down arrives late in the warning colour, saying so; a repeat that missed several sends once.
- **Toggle**: 🔔 Reminders is off by default, like every feature.

**Time zones (D-3)**
- [x] Stored per person, across servers: `users/<userId>/timezone` as an IANA name (`America/New_York`). Python's `zoneinfo` handles summer time.
- [x] Set from 🌍 Time zone on the reminders card: a dropdown of common zones plus a form for any other name, checked against `zoneinfo`.
- [x] The agent is told the sender's local time when it's set, instead of only UTC, and can set it ("I'm in Denver").
- [x] With none set, reminders ask for one first.

**Reminders (D-4)**
- [x] `/remind [when] [what] [repeat] [where]`, matched by `.remind`. No fields opens the card; with fields it sets one and says when it will fire in the person's time ("🔔 Reminder set for Thu, Nov 13 at 8:00 PM").
- [x] `when` takes plain times: "in 2 hours", "tomorrow 9am", "Thursday 8pm", "Dec 25 10:00". Parsing in code, without the agent, so the command works on its own: `reminders/when.py`, our own.
- [x] The card: your reminders (when, what, repeat, where), ➕ New (a form), 🗑️ Delete, 🌍 Time zone, ✖️ Close.
- [x] `repeat`: none, daily, weekly (since QA also weekdays, monthly, yearly and chosen days, each stored exact).
- [x] `where`: here (the channel it was set in, pinging you) or DM. A DM that fails falls back to the channel.
- [x] Admins can target a role or everyone: the reminder pings it, with allowed mentions opened for that one message only.
- [x] Storage: `reminders/<serverId>/<reminderId>/{userId, channelId, text, nextAt (UTC), repeat, where, target}`. A `tasks.loop` sends what's due (every 30 seconds as first built; since QA once a minute, with a wake-up at its exact second for one due sooner, see After 8.3); a repeat moves `nextAt` forward in the person's time zone; one that came due while GBot was down sends late, saying so.
- [x] Limits: 25 per person per server, text 500 characters, nothing over a year ahead (10 years since QA, 2026-11-10).
- [x] Removing GBot from a server deletes its reminders; a member who left has theirs skipped and deleted.
- [x] Feature emoji 🔔, its own `toggle_reminders` (default off), a guide in `help/guides.py`, `commands.json`, README tables, `command_tree_test`.
- [x] Tests; `/qa` (2026-11-09): one-off in channel and DM, daily with skip and stop, a role reminder, the prefix fast path, a restart with one due (arrived late, in the warning colour), a time zone change, and the agent telling and setting the time zone.

## M4 — The agent acts: `read` and `safe`

- [x] **`abilities`** setting in `/agent`'s settings, server-wide with channel overrides like its others: `off` (default), `read`, `safe`, `all`. Separate from the agent being on.
- [x] Only tools allowed at the channel's level are sent to Claude, so a lower level can't be talked past.
- [x] `read` tools: someone's wallet, the server ranking, a market search ("items under 10 GCoin", more than today's 15-row limit), someone's items, the music queue and now playing, which features are on, someone's reminders (only the sender's own unless an admin asks). Rebuilt from `e75d0ed` onto the current settings.
- [x] `safe` tools: play, skip, pause, resume, stop, shuffle (sender must be in GBot's voice channel, as the card requires), and set or delete the sender's own reminders (setting the time zone was always on from M3, and since the pre-merge reviews sits here at `safe`, behind Reminders and counted as an action). Rebuilt from `989387e`. Music's own messages and the agent's reply mustn't double up: the action reports to the now-playing card, as the 8.2 card does, and the agent's reply only adds what the card doesn't say.
- [x] Every tool runs the same checks as its command (`predicates.recheck` with the feature and admin flags) for the sender, not the agent.
- [x] Update CLAUDE.md's agent section: what it can now do, and why it's still safe.
- [x] Tests; `/qa` (2026-11-09): off, read server-wide and safe in one channel; balance, market, queue; play, skip, set, list and delete a reminder; skip refused out of voice and in the read channel.

## M5 — The agent acts: `all`

**Settled 2026-11-09:** a fixed list of actions rather than one `run_command` tool. Since 8.2 most actions are card buttons, not command arguments, so a generic runner would mostly open cards, which a chat message can't. The maintainer picked all four offered.

- [x] **Confirm, posted by code:** "Send 5.00 GCoin to Bob? You'll have 120.00 left." with ✅ Confirm and ❌ Cancel. Only the sender can press, it expires with the usual timeout, and every press rechecks permissions. GCoin reuses its own `SendFlow`; the rest use `AgentConfirm`.
- [x] **Send GCoin**, **buy an item** (from its owner or the market), **sell an item** (list, unlist, or offer to someone), **switch a feature** (admins only, through Config's own switch, never the agent itself). Each runs the feature's own engine. Storms (changed in QA): a plain guess is at `safe`, with no confirm, and a bet at `all`; both delete the sender's message so the number stays hidden, as a prefix guess's does, and the bet's card leaves the number off. Its reminder lookup was narrowed to the sender's own for the same reason (a public reply); admins have 👥 Server's privately.
- [x] Never through the agent: its own settings and key, Patreon, the API. Nothing typed-only (a key, an item image) is taken from chat.
- [x] The prefix-commands toggle guards the prefix variants only, so it doesn't apply here.
- [x] Tests; `/qa` (2026-11-09): a money send cancelled and confirmed (the card becomes the announcement), someone else pressing Send, a member asking for an admin action, a feature switched by an admin, a confirm after GTrade was turned off, selling by a loose item name, showing an item, a Storms guess and a bet with the number hidden.

## M5b — The agent covers everything

**Settled 2026-11-09:** 8.3 is the agentic release, so the agent covers every chat feature, each at the lowest level that fits and behind the same checks as its command. Only GBot's HTTPS management API stays out, as it isn't a chat feature, and a Claude key is never taken from chat: its card opens the private key form.

- [x] **Hype** (admins): list matches and test a pattern (`read`); add, edit, delete a match, the card showing the exact pattern and replies (`all`).
- [x] **Who Dis:** start a game, leave, end your game, and guess with the message deleted so the name doesn't show (`safe`).
- [x] **GCoin:** history, your own or for admins anyone's (`read`).
- [x] **GTrade:** rename your item (`safe`); craft from an attached image, and accept or decline a trade offered to you (`all`).
- [x] **Music:** remove or move a song, restart, elevator mode, follow someone's Spotify (`safe`, the card's voice rules).
- [x] **Storms:** whether one is on (`read`), the umbrella (`safe`).
- [x] **Reminders:** admins remind a role or everyone (`all`).
- [x] **Config** (admins): the Storms and admin channels, the admin and Who Dis roles, the prefix; reporting a member or message to the admins (`all`).
- [x] **Agent** (admins): its settings, instructions and channel overrides, with the key through its own form (`all`). GBot's own-key rules still apply.
- [x] **Patreon:** registering a server, in the Patreon server, for patrons (`all`).
- [x] Grouped by feature where it saves tools, inside the API's 20-strict-tools limit, and every action checked against the channel's level in code.
- [x] **Settled 2026-11-10, one rule for what the agent shows:** it does what typing the command would. Public where the command is public (the wallet, Storms, the music card), and a 🔒 Open one-liner where it's private (GCoin history, reminders, a report's confirm, whose line names nothing), never DMs. Except Who Dis, where any line in the channel would tell a partner when the game began: the message goes and the card goes to DMs, where the game is played, and `.whodis` (8.2 posted a 🔒 line naming who asked) now does the same. A confirm only for what can't be undone or moves money, items, settings or pings, so deleting a reminder gains one and starting Who Dis loses its own (the card's button starts it). One message per answer. Any music change from chat, `/music <search>` and `.music` included, brings the card down to the bottom with what changed on it; the card's own buttons still edit it where it is.
- [x] **From QA, 2026-11-10:** a reminder the agent couldn't set crashed it, as `load_extension` runs a cog's module again as its own copy and the agent caught the other copy's `ReminderProblem`; it lives in `when.py` now, with a test loading the cog as `main.py` does. Times read months and years by the calendar ("in a year", "next month"), and a year ahead is a calendar year. The Who Dis card keeps its look and its Start, now a lasting button naming the server, so the card in your DMs starts the next game too; Start in a game says so instead of ending it, End lives only on the game's card, and the "starting" line is gone in DMs (a press in a server says the game is in your DMs). Every ending card carries 🕵️ Play again (the same lasting Start), Leave ends your game in that server as End would, and a time in seconds is told reminders are to the minute. Start makes every refusal (cooldown, nobody to play with) before opting anyone in, so a refused press changes nothing, and each press gets one private reply: joining and where the game is, together. Join and leave name the server, without quotes or a mention. Reminders repeat every weekday, month or year or on chosen days (the card's day picker, `mon,wed,fri` typed, or the agent's `days`), go up to 10 years ahead, and a sent one has ✅ Done and, when it's theirs alone, ✖️. "in …" is an exact timer, to the second; a named time falls on its minute, and one named for the minute it is goes off now rather than tomorrow; repeats fall on their minute after the first; ✖️ stays after ✅ Done. From QA 2026-11-11: "delete all my reminders" hit the 3-action cap and posted three cards, so deleting reminders and destroying items take lists under one confirm, GCoin goes to one person per message, and a fixed line says what a message left undone; once snoozed a message loses its snooze buttons (the snooze arrives as its own message) and keeps Skip and Stop, its snooze and skip lines standing together, Done cancels a snooze, ✖️ only clears the message, Stop takes a repeat's snooze with it, and Skip keeps one counted status line. The agent's time zone tool says nothing changed when the zone is theirs already. Times not this year show the year ("Wed, Nov 10, 2027"), as the agent read next year's Nov 10 as tonight. 🎧 Follow Spotify is on the "Nothing is playing" card too, and the agent's follow starts the music from silence, both needing the follower in a voice channel (`Music.followProblem`).
- [x] Tests (1483, 100% coverage); `/qa` of each on the dev bot, 2026-11-10 and 11.

## M6 — Live checks left over, and release

- [x] Still never tried live from earlier rounds (passed 2026-11-11; the memory list's pages already work in prod): agent role pings with "Mention Everyone", the private `/agent memory` list's page buttons, threads following their channel's agent settings.
- [x] Not yet seen live from 8.3: a trial's hourly reminders (2 days left, last day, ended) reaching the admin channel, and a lapse: a patron losing the role, their server's notice and refusal, then the role coming back. Passed 2026-11-11 on the dev server, off its ignore list for the test, its trial's start moved for each notice, then all restored: the three notices, the ended refusal with the agent quiet and old cards working, and a lapsed server's refusal (whose "Sorry @name, This" was fixed) then working again once renewed. Marking a lapse and its notice need the Patreon server, which only prod is in, so those stay with their tests.
- [x] `version.py` to 8.3; changelog in the README and `site/_includes/changelog.md` split into New and Changed; site commands and feature tables (already in step), the site's version, description and lead, and the agent's feature blurb, which now says it acts.
- [x] From the regression pass, 2026-11-11: "delete all my hype matches" still posted a card per match, so one message now gets at most one confirm card (a further one joins it, listing each, one press for all), and Hype deletes, feature switches and song removals take lists.
- [x] Local `/code-review high` of `82adc23..HEAD` before merging, 2026-11-11: ten found and fixed. A press on a merged card runs only what it showed, and one action failing leaves the rest their turn; the agent's words still go beside a card for a result no card shows (a reminder, a memory, a time zone), never after a hidden message; a first-time Who Dis player counts toward the reward; a member's refused admin tool uses no action; a role reminder is read again at the press; a Hype edit shows what it replaces and checks it's still there; a ✖️ that can't delete says so; and CLAUDE.md's time zone level and reminder timing.
- [x] Full `/qa` regression pass on dev, then the PR, review, merge on the maintainer's OK, deploy check (`GBot#6890`). Merged 2026-11-11 as `f215655` after three more review rounds (a second local review, the PR's own, and two whole-repository audits), each fixed and retested on dev; the Pi deployed it and upgraded its servers to 8.3 with no errors.
- [x] Announcement in the 8.1 layout, drafted for the maintainer to post.
- [x] Move this plan to `completed/`.

## After 8.3

- **Server load.** With the invite link public (D-1), the one Pi takes every server that tries GBot. Measure first: CPU, memory and network per active voice connection, the Firebase reads per message (Hype and the agent each check access), and the per-second Storms loop. Then decide what to optimize, cap or cache, and when a second host is worth it (roadmap Workstream B). Music (an ffmpeg process and a voice connection per playing server) and Storms (a per-second loop across every server's state) are the two to look at first; check what the 2026 modernization already settled before re-deciding it.
- **Reminders' look reads every reminder.** Since 8.3 it runs once a minute, with a wake-up at its exact second for each reminder due before the next look (`Reminders.wakeFor`), and sending claims a reminder in one database step, so a wake-up and a look can't both send it. The look still reads the whole `reminders` tree to find what's due. When that grows, ask the database for only what's due in the next minute instead (an index on `nextAt`). It belongs with server load above.
