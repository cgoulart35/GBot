#### GBot 8.3
*The agent acts: ask GBot in plain words and it does what the command would, after a confirm for anything that matters.*

**New**
- <ins>The agent acts</ins> — mention GBot and ask: check a wallet or the market, play and control music, set reminders, guess in Storms, send GCoin, buy, sell, craft and trade items, report someone to the admins, and more. Admins choose how far it goes in each channel with **Abilities**: off, read, safe or all. Anything that moves GCoin or items, changes settings or pings people waits for your press on a confirm card, and it only ever does what you could do yourself
- <ins>Reminders</ins> — `/remind` sets them in your own time zone, here or by DM: once, every day, weekday, week, month or year, or on the days you pick, up to 10 years ahead. "in 90 seconds" counts to the second, a named time goes off on its minute, and one that goes off can be snoozed, skipped, stopped, marked ✅ Done or cleared with ✖️. Admins can remind a role or everyone
- <ins>Time zones</ins> — set yours once in `/remind` and it follows you to every server. Change it and your reminders move with you, so 9am stays your 9am
- <ins>A 7-day free trial</ins> — the invite link is on the website, and a new server gets a week of GBot free. Admins are told at 2 days left, on the last day and when it ends, and a server whose trial or subscription ends gets 3 grace days before GBot leaves
- <ins>Setup check</ins> — `/config` shows ⚠️ Setup when GBot is missing a permission it needs, and says exactly which
- <ins>🤝 Trades</ins> — `/gtrade` lists every trade of yours still open, to accept, decline or take back, without finding the message it was made in. Ask the agent "what offers do I have?" and it reads the same list

**Changed**
- <ins>Exact permissions</ins> — GBot asks for only the permissions it uses, never Administrator
- <ins>Who Dis</ins> — `.whodis` sends your card to your DMs and posts nothing in the channel, so nobody learns when you started a game. Its buttons keep working in your DMs, finished games offer 🕵️ Play again, and leaving Who Dis ends your game
- <ins>Music card</ins> — changing the music from chat brings the card down to the bottom with the change on it, and 🎧 Follow Spotify works with nothing playing yet
- <ins>Private things stay private</ins> — anything only you should see, from GCoin history to your reminders, comes as a 🔒 Open button, whether you typed the command or asked the agent
- <ins>Many items at once</ins> — selling, offering, taking down or accepting many items, through the agent or the buttons, posts one message rather than one for each. A bulk offer has ✅ Accept all, ❌ Decline all, 🚫 Cancel all and 🔎 Choose, to take some and leave the rest, and trades that expire together are told in one notice
- <ins>One message for each trade</ins> — a trade's message says when it's taken down, and a sale or an expiry replaces it rather than standing beside it. A confirm card goes once what it did shows on a message of its own, and a GCoin send pings who it went to
- <ins>The agent does what you mean</ins> — "all my items", "all my reminders" and "all of Sam's offers" work in one go, asking for what's already so (selling, elevator mode, following Spotify) leaves it alone rather than undoing it, and it can change one of your reminders
- <ins>Shown items</ins> — an item shown in the channel has ✖️ Close, for whoever showed it or owns it
- <ins>Reminders in your notifications</ins> — a reminder's words show in its phone notification, not only on its card
- <ins>Music keeps playing</ins> — through a brief voice disconnect, elevator mode included, and the now-playing card's progress bar moves as the song plays
- <ins>Slow presses</ins> — a button whose work takes a moment says ⏳ Working on it… straight away, rather than Discord saying GBot didn't respond

#### GBot 8.2
*Every feature is one command now, opening a card you work with buttons.*

**New**
- <ins>Right-click menus</ins> — right-click a message or a member, then **Apps**, to report it to the admins, see someone's wallet or items, or craft an item from an uploaded image
- <ins>Reports</ins> — work in every server, Who Dis or not, and land in the admin channel as a card with the messages captured, ✅ Handled and 🚫 Not an issue. Each card counts the member's recent reports, leaving out any that were not an issue, and `/config` shows every report on a member
- <ins>Storms, version 2</ins> — one live Storm card with ☂️ Umbrella, 🎯 Guess and 🎲 Bet, and your higher or lower hint is yours alone
- <ins>Help as the front door</ins> — `/help` lists what you can use here with a button opening each one, and explains how every feature works, with its real numbers. The agent reads the same guides
- <ins>Hype's Test</ins> — try a message and see which matches it would set off
- <ins>Agent sees link previews</ins> — and works in announcement, voice and forum channels

**Changed**
- <ins>One command per feature</ins> — `/agent`, `/config`, `/gcoin`, `/gtrade`, `/help`, `/hype`, `/music`, `/patreon`, `/storms` and `/whodis`. With nothing typed after it, each opens a card with a button for everything its old subcommands did. The subcommands and their shortcuts, like `/music play` and `.m s`, are gone, while prefix commands keep each feature's aliases, like `.m` and `.s`
- <ins>Fast paths</ins> — `/music <search>` plays straight away, `/storms 42` guesses and `/storms 42 5` bets, `/gcoin @someone` shows their wallet, and `/whodis user:<name>` is your guess
- <ins>Private from prefix commands too</ins> — a prefix command for something private posts a 🔒 Open button, which shows it to whoever presses it, privately, and tidies itself away
- <ins>Music card</ins> — one now-playing card that updates itself as songs change and shows who added each one, for everyone in the voice channel: pause, restart, skip, stop, add a song, shuffle, elevator, follow Spotify, and a queue to move and remove songs. Elevator and Spotify turn green while they're on
- <ins>Wallets and ranking</ins> — `/gcoin` shows your balance, last in and out and your rank here. Send asks who, then the amount, then confirms, and Ranking covers this server and everywhere
- <ins>Items and the market</ins> — `/gtrade` lists your items to show, sell, rename or destroy, with crafting and the market a press away. Trade requests have Accept, Decline and Cancel buttons, and listings a Buy button, which keep working after the bot restarts
- <ins>Agent card</ins> — `/agent` shows what applies where, with a channel picker, settings from dropdowns, instructions in a form, the key and reset on the same card. Members get their memories there
- <ins>Settings card</ins> — `/config` turns features on and off with a press, and picks channels and roles from Discord's own lists
- <ins>Hype</ins> — matches are added, edited and deleted on one card
- <ins>Nothing waits for a typed reply</ins> — typing goes in forms, choices in dropdowns and buttons, so there's no more typing `cancel`. Anything that can't be undone asks first, and every private card has ✖️ Close

#### GBot 8.1
- <ins>AI agent</ins> — set up an agent in plain words that replies and reacts how you tell it to, channel by channel, and remembers what you ask it to. Powered by Claude, using your own API key

#### GBot 8.0
*The 2026 modernization — a rebuild of everything under the bot, alongside the user-facing changes.*

- <ins>Grouped commands</ins> — every command now lives under its cog for both slash and prefix (`/music play`, `.music play`, `.m p`), replacing 36 global command names with 9. This is also what freed the names behind the renames: `.dis` → `.whodis guess`, `.leavedis` → `.whodis leave`, `.hype` → `.hype respond`, `.unmatch` → `.hype remove`, `.config` → `.config show`
- <ins>Music restored and rebuilt</ins> — every voice feature had been dead in production since 2026-03-02, when Discord made end-to-end encryption mandatory for voice. Playback works again and is substantially better: Opus passthrough instead of re-encoding every frame, livestream and playlist support, and video links and lengths in the now-playing message
- <ins>Queue controls</ins> — remove, move and shuffle queued songs, restart the current one, see a progress bar on it, and elevator mode now loops the whole queue
- <ins>New look</ins> — a consistent and more fun design across every feature: tidy cards with emoji, medals and winner cards, a one-card `/config show`, private errors and balances on slash commands, commas in GCoin amounts, and a welcome message when GBot joins a server
- <ins>New /help</ins> — lists only what is available in your server, and tells you how to turn on what is off
- <ins>All-or-nothing GCoin and trades</ins> — sends, trades, crafting and destroying complete fully or not at all, so a failure can't lose GCoin or items
- <ins>More responsive</ins> — database work no longer holds up the rest of the bot
- <ins>Full bug review</ins> of every feature, from double payouts and Who Dis guesses to Hype, Music and server setup
- <ins>Python 3.13</ins> base image and <ins>nextcord 3.2</ins>, with every dependency repinned
- <ins>Zero known vulnerabilities</ins> — Pyrebase4 replaced by `firebase-admin`, and `pip-audit` runs clean on every pull request
- <ins>100% test coverage</ins> of `GBotDiscord/src`, line and branch, enforced as a merge gate rather than a target
- <ins>Continuous delivery</ins> — GitHub Actions builds a native arm64 image on every push and the Raspberry Pi redeploys itself from it; the old git-pull update handler is retired
- <ins>New website</ins> — a redesigned home for GBot with searchable commands and live leaderboards
- <ins>Automated pull-request review</ins> on every PR, plus a scheduled job that bumps and verifies `yt-dlp` so a YouTube extractor break never sits unnoticed

#### GBot 7.0
- <ins>Who Dis</ins> random user chat mini-game functionality
- GBot <ins>Leaderboards</ins> track live statistics on the [GBot website](https://gbot.stormerg.com/)

#### GBot 6.0
- <ins>Slash command</ins> functionality for all commands (Config, GCoin, GTrade, Hype, Music, Patreon, and Storms)
- <ins>Storms</ins> enhancements to show all Storm activity only in the configured channel & purge messages all at once
- <ins>Config</ins> enhancement allowing admins to enable or disable legacy prefix commands in their servers

#### GBot 5.0
- <ins>Storms</ins> (randomly timed mini-games) have returned from [StormBot](https://github.com/cgoulart35/StormBot)
- <ins>Music bot</ins> enhancement to sync music with user Spotify activity

#### GBot 4.0
- GBot <ins>Patreon</ins> member tracking functionality
- <ins>Hype</ins> message regex matcher functionality for automated replies and reactions

#### GBot 3.0
- User-specific <ins>GCoin currency</ins> and transaction functionality
- User-specific <ins>GTrade items</ins> and crafting functionality
- ~~<ins>Halo Infinite</ins> competition enhancement with <ins>GCoin integration</ins>~~ (DISCONTINUED)

#### GBot 2.0
- <ins>Music bot</ins> functionality to play YouTube videos

#### GBot 1.0
- Server-specific <ins>configuration</ins> settings
- ~~Weekly <ins>Halo Infinite competitions</ins> with random challenges~~ (DISCONTINUED)
- ~~Daily <ins>Halo Infinite Message of the Day</ins> checks~~ (DISCONTINUED)
