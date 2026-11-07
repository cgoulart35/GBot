#### GBot 8.2
- <ins>Buttons instead of typed answers</ins> — lists you manage, like the agent's memories and Hype matches, are one card with a dropdown and Add, Edit and Delete buttons, with forms for typing. Nothing waits for your next message in the channel, so there's no more typing `cancel`
- <ins>One `/hype`</ins> — `/hype respond`, `react` and `remove` are replaced by `/hype`, where matches are added, edited and deleted
- <ins>Trade buttons</ins> — trade requests have Accept, Decline and Cancel buttons, and market listings a Buy button, which keep working after the bot restarts
- <ins>Crafting takes its image</ins> — `/gtrade craft` takes the image with the command, attached or as a link, and its `type` option is gone
- <ins>Confirm before it's gone</ins> — resetting the agent, removing its key and destroying an item ask first
- <ins>How it works</ins> — `/help` explains how each feature works, with its real numbers, and the agent reads the same guides
- <ins>Agent sees link previews</ins> — and works in announcement, voice and forum channels

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
