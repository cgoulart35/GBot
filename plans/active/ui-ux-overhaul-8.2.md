# GBot 8.2 — UI/UX overhaul

**Status: design approved 2026-11-07, building.** The maintainer approved the mockups as drawn, every proposal included. Built on `feat/buttons-and-agent-polish`, shipping as one PR, GBot 8.2. A fresh session: read the rules, then the build checklist, and carry on at the first unticked item.

**Already built on this branch** (the start of 8.2): the shared button module (`pagination.py`), `/agent memory` and `/hype` as cards, trade request and listing buttons, confirmations for reset, remove key and destroy, crafting with the image in the command, feature guides, link previews.

## The rules everything follows

1. **One command per feature.** With no fields it opens the feature's card. Optional fields give a fast path where one is worth having: `/music <search>`, `/storms [number] [bet]`, `/whodis [user]`, `/gcoin [user]`. Prefix commands have the same shape, and keep each feature's aliases (`.m`, `.s`, `.ag` …).
2. **Cards for managing, buttons on what GBot posts.** Anything you browse and change is a card. Anything GBot posts that people react to (a Storm, a song, a trade) carries the buttons for what you'd do next.
3. **Nothing waits for a typed reply.** Text goes in a form, choices in a dropdown, button or Discord's own member, channel and role pickers.
4. **Private when it's about you or settings, public when it's a moment.** Wallets, settings and lists are private. Games, wins, trades, songs and 🔎 Show are public.
5. **Results replace the question on the same message,** rather than piling up new ones.
6. **Only whoever opened a card can press it,** except buttons meant for everyone: a Storm's, a trade's, the music card's (for people in GBot's voice channel), a report card's (for admins).
7. **One look:** brand, warning and error colours as now, the standard footer, a feature emoji leading every one-line confirmation. Buttons: green adds or confirms, blue edits, red can't be undone, grey moves around or closes.
8. **Refusals stay red, private, and say what to do instead.**
9. **Buttons on long-lived messages survive restarts:** their `custom_id` says what they're for, answered by a cog listener, as trade buttons are.
10. **Every permission is re-checked on every press,** never only when the card opened.

## The design, feature by feature

The approved mockups (`gbot-8.2-mockups.html`, built in the session scratchpad, not in the repo) drew each of these. This is the written record of them.

### Help — `/help [feature]`
Front door: every feature with a one-line summary, a button opening each feature's card (only those on in the server and usable by the caller), a "Turned off here" field, and a 📖 dropdown for each feature's page. A feature's page: its guide, its command, ◀️ Back and an Open button.

### Music — `/music [search]`
With a search it plays. Without, it opens the card, or a private "Nothing is playing" with ➕ Add song.
- **Now-playing card**, public, one per session, edited in place as songs change: song, length, progress, voice channel, who added it, up next, elevator and queue size. Buttons: ⏸️ Pause / ▶️ Resume, ⏭️ Skip, ⏹️ Stop, 🔀 Shuffle, 🛗 Elevator; ➕ Add song, 📜 Queue, 🎧 Follow Spotify, 🔁 Restart.
- Only people in GBot's voice channel can press it; anyone else gets a private red refusal.
- **📜 Queue**, private, paged: pick a song, then ⬆️ Up, ⬇️ Down, ⏩ Play next, 🗑️ Remove, ✖️ Close.
- **➕ Add song**: a form with one box, a search or a link.
- **🎧 Follow Spotify**: a member picker, and 🛑 Stop following.
- Replaces: `play`, `queue`, `skip`, `pause`, `resume`, `stop`, `restart`, `remove`, `move`, `shuffle`, `elevator`, `spotify`.

### Storms — `/storms [number] [bet]`, version 2: private hints
- **Incoming card**: ☂️ Umbrella. The first press starts it and pays the umbrella reward.
- **Live card**, the same message edited as people play: the range, the multipliers, each player and their tries (never their numbers), who started it. Buttons: 🎯 Guess, 🎲 Bet (forms), 📖 How it works.
- **Hints are private** to whoever guessed: "42 is too low ⬆️ — that was try 3, so a win now pays 2.5x." A typed `/storms 42` gets the same private hint; a prefix guess gets its hint by DM (or a short public "wrong" if DMs are closed).
- **The win** turns the live card into the result: the winner, the number, the multiplier and everyone's tries.
- `/storms` with no fields shows the live card's state privately, or says when the next Storm is due.
- Replaces: `umbrella`, `guess`, `bet`.

### Who Dis — `/whodis [user]`
- `/whodis` privately: 🕵️ Start a game, 🚪 Leave Who Dis, 📖 How it works. `/whodis user:@x` guesses.
- **DM game card**: 🛑 End game, 🚩 Report (captures that game's messages).
- Replaces: `start`, `guess`, `leave`. `report` moves out, see Reporting.

### Reporting — always on, owned by Config
**Decided 2026-11-08:** reporting isn't Who Dis's. It works with Who Dis off, needs only the admin channel and role Config already manages, and lives in the Config cog with no command of its own:
- Right-click a **message** → Apps → 🚩 Report to admins (captures exactly that message, plus its author's last few in the channel).
- Right-click a **member** → Apps → 🚩 Report (captures their last 5 messages in the channel).
- Both ask an optional "What happened?" in a form, confirm privately, and post the **admin report card** (warning colour) in the admin channel: who, by whom, where, what happened, the captured messages quoted with times. ✅ Handled and 🚫 Not an issue, for admins, edit the card to record the outcome and who chose it.
- The Who Dis DM card's 🚩 Report posts the same card, with the game's messages.
- **Report history per member (decided 2026-11-08):** each report is stored (`reports/<serverId>/<reportId>`: who, by whom, channel, when, what happened, links to the captured messages, outcome and who set it; the message text stays on the card, not in the database). The admin card says "3rd report on @Sam in 30 days" and has 📋 History; Config's card has 🚩 Reports (pick a member, see their reports, paged). Removed with the server's data when GBot leaves it.

### GCoin — `/gcoin [user]`
Private wallet, yours or theirs: balance, last in, last out, rank in this server.
- 💸 **Send**: on your own wallet, a member picker first; on theirs, straight to a form (amount, optional note), then a confirm with what you'll have left.
- 📜 **History**, paged. 🏆 **Ranking**: tabs 🏠 This server and 🌍 Everywhere, paged, with 🔗 Website to the public leaderboard. Also a button on Help.
- Right-click a member → Apps → 💰 View wallet.
- Replaces: `wallet`, `wallets`, `send`, `history`.

### GTrade — `/gtrade`
- **Your items**, private: pick one for 🔎 Show (public), 🏷️ Sell, ✏️ Rename, 💥 Destroy (confirm). Then ⚒️ Craft, 🏪 Market, ✖️ Close, and a tip about crafting from uploads.
- **🏷️ Sell**: 🏪 The market or 🤝 Someone (member picker), at its value.
- **⚒️ Craft**: a form for name, value and an image link. Uploads: right-click the image's message → Apps → 🏪 Craft item, a form for name and value.
- **🏪 Market**: what's for sale here, with "Waiting on you" for requests sent to you. Pick one for 🛒 Buy or 🔎 Show.
- Trade requests and listings keep their buttons (built).
- Right-click a member → Apps → 🏪 View items.
- Replaces: `craft`, `item`, `items`, `market`, `buy`, `sell`, `rename`, `destroy`.

### Hype — `/hype` (built) plus 🧪 Test
🧪 Test: a form for a sample message, answered with what would match and how.

### Agent — `/agent`
- Admins: the home card (`/agent show` today) with a 📍 channel dropdown at the top (whole server, or one channel) that every button acts on. ⚙️ Settings (pick a setting, then its value, then ✅ Save), 📝 Instructions (pre-filled form), 🧠 Memories (built), 🔑 Key (Enter a key, Remove key), ♻️ Reset (what, then confirm).
- Members: their memory card when memory access is everyone, otherwise a refusal.
- Replaces: `key`, `removekey`, `instructions`, `settings`, `memory`, `reset`, `show`.

### Config — `/config`
A card: each feature a toggle button (green on, grey off, including ⌨️ Prefix commands), channel pickers for the Storms and admin channels (text only), 👥 Roles (role pickers for admin and Who Dis), ✏️ Prefix (form), 🤖 Agent settings (opens `/agent`). Turning the agent on keeps its public notice.
- Replaces: `show`, `toggle`, `channel`, `role`, `prefix`.

### Patreon — `/patreon`
No change.

### Right-click menus (Discord allows 5 per kind)
- Member: 💰 View wallet, 🏪 View items, 🚩 Report.
- Message: 🚩 Report to admins, 🏪 Craft item.
They're slash-only by nature. Each still runs the feature's subscription, guild and toggle checks.

## Prefix cards (decided 2026-11-08)
Discord only allows a private reply to an interaction, so a prefix command can't open a card privately by itself. Moments stay public as today: the music card, Storms, trades, 🔎 Show, wallets and the ranking. Anything private (agent, config, hype, memories, your items, history, the Who Dis card) posts a public one-liner with 🔒 **Open**, which opens the same card privately, exactly as the slash command would.
- Pressed by whoever ran it: the card opens, and the one-liner is deleted, with their prefix message too when GBot can manage messages.
- Pressed by anyone else: it opens *their own* version of the same command, with their own permissions checked, as if they had typed it. The one-liner stays for its owner.
- Nobody opens it: both are deleted after a few minutes.
- A prefix Storm guess posts "❌ StormerG guessed wrong" with 🔒 **See your hint**, for the guesser only.

## Build checklist
Tick as each lands, with `/test` and the coverage gate green at each tick.
- [x] Shared: persistent-button routing (one `custom_id` scheme), member/channel/role pickers in `pagination.py`, context menu registration with the standard checks, the prefix-card delivery rule. (`6b1055d`: `pagination.Form`, `openPrivately`, `persistentButton`/`persistentParts`, `predicates.recheck`, `presentation.sendInteractionError`.)
- [x] Config card, and reporting. (`862698c`; menus documented in `site/_data/menus.json` and the README's Right-click menus table, guarded by `site_drift_test`.)
- [x] Agent home card. (`214f709`; the old commands' code runs from the card through `CardReply`.)
- [x] GCoin wallet, Send, History, Ranking, View wallet. (`00a86e1`)
- [x] GTrade items, market, Craft form, Craft item, View items. (`eda006b`; the old commands' engines stay as `commonBuy`/`commonSell`/`commonRename`/`commonCraft`, and `announce` sends a card's public moments to the channel.)
- [x] Hype 🧪 Test.
- [x] Music now-playing card, queue card, Add song, Follow Spotify. (`16e68e8`)
- [x] Storms version 2. (`33678b5`; the 5- and 1-minute warnings stay as messages.)
- [ ] Who Dis card and DM card.
- [ ] Help front door.
- [ ] The whole repo: `strings.py`, `guides.py`, every refusal and confirmation, `command_tree_test.py` (one command per feature), both test runners, README command and feature tables, `site/_data/commands.json` and `features.json`, the changelog in both places, CLAUDE.md (the dual-mode command section, Per-feature layout, presentation), the website's pages that show commands, `FEATURE_EMOJIS`, the agent's tool list and rules, any text that names an old command.
- [ ] A full code review, then live QA of every card on the dev bot.
