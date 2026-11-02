<p align="center">
  <img src="site/assets/images/gbot-logo.png" alt="The GBot logo: a glitching green letter G above the word BOT" width="140">
</p>

<h1 align="center">GBot 8.0</h1>

<p align="center"><strong>Games, music and a currency for your Discord server.</strong></p>

<p align="center">
  <a href="https://gbot.stormerg.com/"><img alt="Website" src="https://img.shields.io/badge/website-GBot-39FF14?style=for-the-badge"></a>
  <a href="https://www.patreon.com/StormerG/membership"><img alt="Get GBot on Patreon" src="https://img.shields.io/badge/get%20GBot-Patreon-39FF14?style=for-the-badge"></a>
  <a href="https://github.com/cgoulart35/GBot/actions/workflows/ci.yml"><img alt="CI" src="https://img.shields.io/github/actions/workflow/status/cgoulart35/GBot/ci.yml?branch=develop&label=CI&style=for-the-badge"></a>
</p>

<p align="center">
  <a href="https://gbot.stormerg.com/">Website</a> •
  <a href="https://gbot.stormerg.com/commands.html">Commands</a> •
  <a href="https://gbot.stormerg.com/leaderboards.html">Leaderboards</a> •
  <a href="#changelog">Changelog</a> •
  <a href="#setup-guide">Setup Guide</a>
</p>

GBot is a multi-server Discord bot, Dockerized and written in Python, with its server and user data in Google Firebase Realtime Database.

## Features

| Feature | What it does |
|---|---|
| 🎵 **Music** | Play searches, video links, livestreams and playlists from YouTube in your voice channel, with full queue controls and Spotify sync. |
| 🌧️ **Storms** | Surprise number-guessing storms. Guess from 1 to 200 or bet your GCoin, with up to a x10 multiplier for a quick win. |
| 💰 **GCoin** | A currency that follows you across every server. Earn it, send it, and climb the wallets. |
| 🏪 **GTrade** | Craft image items, show them off, and trade them directly or through the server's market. |
| ❓ **Who Dis** | Chat anonymously with a random member of your server. Guess who they are to win GCoin. |
| ↩️ **Hype** | Set up automatic replies and emoji reactions that fire when a message matches a pattern. |

Admins turn each feature on or off with `/config toggle`, and set the roles, channels and prefix they need with the rest of `/config`:

- **Storms** also need a channel for incoming storms, and **Who Dis** needs a role for the members who opted in.
- Mini-game rewards need **GCoin** to be on.
- Every command is a slash command. **Legacy prefix commands** can be turned on too, using a prefix each server picks.

## Getting GBot

1. Subscribe to the [GBot tier on Patreon](https://www.patreon.com/StormerG/membership). You'll be prompted to join the GBot Patreon Discord server with your Patreon-linked Discord account.
2. In that server, run `/patreon` with your server's ID to enable GBot there.
3. Admins pick features with `/config toggle`, and everyone can see what's available with `/help`.

GBot only stays in subscribed servers. If it leaves a server, that server's GBot settings are lost.

## Commands

Every command, with its full syntax and examples, is on the [commands page](https://gbot.stormerg.com/commands.html). The shorthand column shows the prefix form with the default `.` prefix.

### 🎵 Music

| Command | Shorthand | What it does |
|---|---|---|
| `/music play` | `.m p` | Play videos/music streamed from YouTube. |
| `/music queue` | `.m q` | Displays the current songs in queue. |
| `/music skip` | `.m s` | Skips the current song being played. |
| `/music pause` | `.m ps` | Pauses the current song being played. |
| `/music resume` | `.m r` | Resumes the current song being played. |
| `/music stop` | `.m st` | Stops the bot from playing songs and clears the queue. |
| `/music restart` | `.m rs` | Restarts the current song from the beginning. |
| `/music remove` | `.m rm` | Removes a song from the queue. |
| `/music move` | `.m mv` | Moves a song to another position in the queue. |
| `/music shuffle` | `.m sh` | Shuffles the songs in the queue. |
| `/music elevator` | `.m e` | Toggle elevator mode to loop the queue. |
| `/music spotify` | `.m sp` | Play current spotify activity streamed from YouTube. |

### 🌧️ Storms

| Command | Shorthand | What it does |
|---|---|---|
| `/storms umbrella` | `.s u` | Start the incoming Storm and earn 0.25 GCoin. |
| `/storms guess` | `.s g` | Make a guess with a winning reward of 1.00 GCoin. |
| `/storms bet` | `.s b` | Make a guess. If you win, you earn the amount of points bet. If you lose, you lose those points. |

### 💰 GCoin

| Command | Shorthand | What it does |
|---|---|---|
| `/gcoin wallet` | `.gc w` | Show your wallet, or another user's wallet in this server. |
| `/gcoin wallets` | `.gc ws` | Show wallets of all users in this server. |
| `/gcoin send` | `.gc sd` | Send GCoin to another user in this server. |
| `/gcoin history` | `.gc hs` | Show your transaction history, or a user's transaction history in this server. (admin optional) |

### 🏪 GTrade

| Command | Shorthand | What it does |
|---|---|---|
| `/gtrade craft` | `.gt cr` | Craft items to show off and trade. |
| `/gtrade item` | `.gt i` | Show off an item in your inventory. |
| `/gtrade items` | `.gt is` | List all items in your inventory, or another user's inventory in this server. |
| `/gtrade market` | `.gt m` | Show all market items for sale and personal trade requests in the discord server. |
| `/gtrade buy` | `.gt by` | Buy another user's item for sale in the discord server. |
| `/gtrade sell` | `.gt sl` | Sell an item to another user in this discord server. |
| `/gtrade rename` | `.gt rn` | Rename an item in your inventory. |
| `/gtrade destroy` | `.gt d` | Destroy an item in your inventory. |

### ❓ Who Dis

| Command | Shorthand | What it does |
|---|---|---|
| `/whodis start` | `.wd s` | Start or end a mini-game where you try to guess a random user in the server you are paired with. |
| `/whodis guess` | `.wd g` | Guess the name of the user you are paired with for a chance to win GCoin. |
| `/whodis leave` | `.wd l` | Remove the server's 'Who Dis?' role opting you out of any future games. |
| `/whodis report` | `.wd rp` | Report a user to server admins for bad behavior. |

### ↩️ Hype

| Command | Shorthand | What it does |
|---|---|---|
| `/hype respond` | `.hy rs` | Set a regex to match against messages, and a list of possible responses to reply with. (admin only) |
| `/hype react` | `.hy re` | Set a regex to match against messages, and a list of possible emojis to react with. (admin only) |
| `/hype remove` | `.hy rm` | Remove an existing regular expression match response in this server. (admin only) |

### ⚙️ Config

| Command | Shorthand | What it does |
|---|---|---|
| `/config show` | `.c s` | Shows the server's current GBot configuration. (admin only) |
| `/config toggle` | `.c t` | Turn on/off all functionality for a GBot feature in this server. (admin only) |
| `/config channel` | `.c ch` | Set the channel for a specific GBot feature in this server. (admin only) |
| `/config role` | `.c rl` | Set the role for a specific GBot feature in this server. (admin only) |
| `/config prefix` | `.c pr` | Set the prefix for all GBot commands used in this server. (admin only) |

### 💡 Help

| Command | Shorthand | What it does |
|---|---|---|
| `/help` | `.help` | See what GBot can do in this server. |

### ⭐ Patreon

| Command | Shorthand | What it does |
|---|---|---|
| `/patreon` | `.pt` | In the GBot Patreon server, specify your server's ID to enable GBot functionality. (patrons only) |

Halo Infinite commands were discontinued and are kept in the code as an archive.

## Changelog

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

## Setup Guide
1. Clone GBot.
2. Install Docker (and Docker compose if on Linux).
3. Create a [Google Firebase Realtime Database](https://console.firebase.google.com/) project.
4. Create a user for authentication and a service account in project settings.
5. Download the service account key .json file to the GBot/Shared/ directory and rename it to serviceAccountKey.json. (The service account key is GBot's primary database credential — the firebase-admin SDK authenticates with it; the apiKey below is used only to verify private API logins.)
6. Navigate to project settings and copy your Firebase configuration variables into the following json string respectively and save it:
{"apiKey":"","authDomain":"","databaseURL":"","projectId":"","storageBucket":"","messagingSenderId":"","appId":"","measurementId":"","serviceAccount":"/GBot/Shared/serviceAccountKey.json"}
7. Create a Discord bot project in the [Discord Developer Portal](https://discord.com/developers/applications) and save the bot token.
8. Under the Discord bot project's bot settings, enable all intents and add the bot to your server with administrator privileges.
9. Move GBot's role above other roles you create in the server that GBot will assign to server members.
10. ~~Sign up for an Autocode token to utilize the free [Halo API](https://autocode.com/lib/halo/infinite/) service.~~
11. Update the GBot/Shared/gbot.env file with your Discord bot token, ~~Autocode token~~, and Firebase data.
12. Set your preferred time zone (TZ) in the GBot/Shared/gbot.env file. (Ex: TZ=America/New_York)
13. Set your preferred log level for the logged info and error messages. (Ex: LOG_LEVEL=INFO)
14. Set your preferred port for the Quart API to run on. (Ex: API_PORT=5004)
15. Set the Patreon URL to promote subscribing when users are unable to execute commands. (Ex: PATREON_URL=https://www.patreon.com/\<INSERT-PATREON-PAGE-NAME\>/membership)
16. Set the Discord IDs of the guild and role that will be used for Patreon integration. (Ex: PATREON_GUILD_ID=012345678910111213 and PATRON_ROLE_ID=012345678910111213)
17. Set the comma delimited list of Discord guild IDs that will bypass Patreon validation. (Ex: PATREON_IGNORE_GUILDS=012345678910111213,012345678910111213,012345678910111213)
18. Set your preferred timeout for user responses to GBot messages. (Ex: USER_RESPONSE_TIMEOUT_SECONDS=300 if you want the bot to stop listening for a user response after 5 minutes)
19. ~~Set your preferred Halo MOTD and Competition trigger times in the GBot/Shared/gbot.env file. (Ex: HALO_INFINITE_COMPETITION_DAY=5 if you want competitions to start/end on Saturdays)~~
20. Set your preferred music bot timeout in the GBot/Shared/gbot.env file. (Ex: MUSIC_TIMEOUT_SECONDS=300 if you want the music bot to leave after 5 minutes of inactivity)
21. Set the longest song the music bot will accept in the GBot/Shared/gbot.env file. (Ex: MUSIC_MAX_DURATION_MINUTES=180 if you want to prevent songs over 3 hours long from being played.) Livestreams are exempt — they have no length to limit.
22. Set how many songs a pasted playlist may add to the queue in the GBot/Shared/gbot.env file. (Ex: MUSIC_MAX_PLAYLIST_SONGS=50 if you want a playlist to contribute at most 50 songs; anything beyond is dropped and the reply says so.)
23. Set the most songs the queue may hold in the GBot/Shared/gbot.env file. (Ex: MUSIC_MAX_QUEUE_SONGS=200 if you want to refuse songs once 200 are queued. Defaults to 200.)
24. Set your preferred transaction request timeout for buy and sell requests to be cancelled. (Ex: GTRADE_TRANSACTION_REQUEST_TIMEOUT_MINUTES=5 if you want transaction requests to be cancelled after 5 minutes of not being accepted.)
25. Set your preferred market sale timeout for market sales to be taken down. (Ex: GTRADE_MARKET_SALE_TIMEOUT_HOURS=3 if you want market sales to be taken down after 3 hours of no completed transaction.)
26. Set your preferred minimum amount of time between random Storms minigames. (Ex: STORMS_MIN_TIME_BETWEEN_SECONDS=3600 if you want there to be at least 1 hour between each Storm.)
27. Set your preferred maximum amount of time between random Storms minigames. (Ex: STORMS_MAX_TIME_BETWEEN_SECONDS=14400 if you want there to be at most 4 hours between each Storm.)
28. Set your preferred amount of time for Storms-related messages to be deleted after. (Ex: STORMS_DELETE_MESSAGES_AFTER_SECONDS=60 if you want Storm-related messages to be deleted after 60 seconds.)
29. Set your preferred 'Who Dis?' timeout in the GBot/Shared/gbot.env file. (Ex: WHODIS_TIMEOUT_MINUTES=5 if you want Who Dis games to timeout after 5 minutes)
30. Set your preferred 'Who Dis?' cooldown in the GBot/Shared/gbot.env file. (Ex: WHODIS_COOLDOWN_MINUTES=10 if you want users to wait 10 minutes before starting another game)
31. If you are a developer, set your development guild IDs in the GBot/Shared/gbot.env file. (Ex: SLASH_COMMAND_TEST_GUILDS=012345678910111213,012345678910111213,012345678910111213 if you want to register the slash commands only in specific guilds)
32. Verify all files have read/write/execute permissions.
33. From the GBot directory, run 'docker-compose -f docker-compose-prod.yml up -d --build' to build and start the bot! (Without `--build`, compose pulls the published `ghcr.io/cgoulart35/gbot` image instead of building your local checkout.)

 ## Bot Identities & Manual QA

 There are two Discord applications — **`gbot.prod01`** (`GBot#6890`, the bot real users talk to) and **`gbot.dev01`** (`GBot#9690`) — differing only by `DISCORD_TOKEN` and sharing one Firebase project. **Prod runs on the Pi** from `docker-compose-prod.yml`. **Dev runs only where it is being tested**, from `docker-compose-dev.yml`, and is otherwise down.

 The governing rule is **one token runs in exactly one place at a time**: two connections on the same application receive every gateway event twice, so every storm tick, hype match and command fires twice. QA therefore defaults to dev, which nothing else is running, so production keeps serving throughout. Only QA as prod has to stop the Pi's instance and put it back.

 Each identity has its own compose file naming its own gitignored env file in `Shared/`: `docker-compose-prod.yml` → `gbot.env`, `docker-compose-dev.yml` → `gbot.env.dev`. Only `gbot.env.example` is tracked. `scripts/qa.sh` simply picks which compose file to bring up.

 ### QA with the dev identity (recommended)

 Using `gbot.dev01` **leaves the production bot serving real users**, so this is the default:

 ```bash
 QA_CONFIRM=yes scripts/qa.sh up      # builds the working tree as :qa, runs it as gbot.dev01
 scripts/qa.sh logs 40                # expect "GBot logged in as GBot#9690."
 scripts/qa.sh down
 ```

 ### QA with the production identity

 Only for changes that genuinely need it — a real guild's data, or a Patreon-gated path in a really-subscribed server. Stop the Pi's instance first (`docker compose -f docker-compose-prod.yml down`) and bring it back afterwards with `scripts/deploy.sh`, which also re-syncs the checkout. This costs real downtime:

 ```bash
 QA_CONFIRM=yes scripts/qa.sh up prod # expect "GBot logged in as GBot#6890."
 ```

 Either way the build is tagged `:qa`, so it is invisible to the Pi's deploy watcher (which only compares `:latest`) and can never trigger a redeploy. **Nothing on the Pi restarts a stopped prod instance for you** — the watcher only reacts to a newly published `:latest` — so returning it is a manual step you must not skip.

 ### Attaching a debugger

 `docker-compose-dev.yml` runs `main.py` under debugpy **without** `--wait-for-client`, so the bot starts on its own and you attach only if you want to. The listener is bound to loopback (`127.0.0.1:5677`), because an open debugpy port is arbitrary code execution for anyone who can reach it — the same reason Phase 6 stripped the debug port from prod. To attach to the Pi's dev instance, tunnel first: `ssh -L 5677:localhost:5677 StormerPi2`.

 ### The shared-database caveat

 Both identities share one Firebase project, and it is only *partly* partitioned by guild. Per-guild data (`servers/<id>` — config, toggles, hype matches) is isolated, so working in a private test guild is clean. But **`gcoin/<userId>`, `leaderboards` and `patreon_members` are global roots** — a storm win or a trade in the test guild credits a real balance and real leaderboard stats. Music is the easy case: it writes nothing to Firebase at all.

 Also note the dev identity's test guild must be listed in `PATREON_IGNORE_GUILDS`, or the 24-hour `patreon_validation` task will force the bot to leave it.

 ## Unit Tests

 ### Running in Docker (recommended)

 Tests run inside the `gbot-test` Docker image — no host pip installs, no need for `Shared/gbot.env` or `Shared/serviceAccountKey.json` (tests mock Firebase and Discord). The suite is standardized on `pytest`, which collects the existing `unittest.TestCase` suites natively; `pytest.ini` keeps the archived Halo suites ignored. Dev-only deps (`pytest`, `coverage`, `pip-audit`) live in `requirements-dev.txt` and are installed ad hoc by the test flow — never baked into the runtime image.

 * One-command wrapper (builds the image, installs dev deps, runs the suite):
   * `scripts/test.sh`
 * Dependency vulnerability audit:
   * `scripts/test.sh audit`
 * Coverage gate (suite under coverage + report; see Coverage below):
   * `scripts/test.sh coverage`
 * Single test / filter (anything else passes through to pytest):
   * `scripts/test.sh -k storm` or `scripts/test.sh GBotDiscord/test/\<cog\>/\<cog\>_test.py`
 * Manual equivalent (build once; re-run the build only after `requirements.txt` changes):
   * `docker-compose -f docker-compose-test.yml build`
   * `docker-compose -f docker-compose-test.yml run --rm --entrypoint sh gbot-test -c "pip install -r requirements-dev.txt -q && python -m pytest -q"`
 * Run a single cog suite (replace `\<cog\>`):
   * `docker-compose -f docker-compose-test.yml run --rm gbot-test -m unittest GBotDiscord/test/\<cog\>/\<cog\>_test.py`
 * Legacy unittest entry point (still supported):
   * `docker-compose -f docker-compose-test.yml run --rm gbot-test GBotDiscord/test/test.py`

 The compose file mounts the repo at `/GBot` so test edits on the host are picked up without rebuilding. Exit codes are CI-safe: `pytest` and `test.py` both exit `0` on success and non-zero on any failure.

 ### Running locally (alternative)

 * To execute all unit tests, use the "Python: Current File" run configuration to run `tests.py`.
 * To execute unit tests for a single cog suite (replace `\<cog\>`):
   * use the "Python: Current File" run configuration to run `\<cog\>_test.py`.
   * or execute the following command from the "GBot" directory:
      * `python -m unittest GBotDiscord/test/\<cog\>/\<cog\>_test.py`
      * Note: To avoid import errors, please make sure to run the above command from the "GBot" directory.

 ## Coverage

 Coverage is measured with `coverage.py` against `GBotDiscord/src/**`. Exclusions (Halo, `main.py`, `__init__.py`s, string constants) live in `.coveragerc`. `coverage` is a dev dep (`requirements-dev.txt`), installed ad hoc like the rest of the test flow.

 * Run the suite under coverage and print the report:
   * `scripts/test.sh coverage`
   * Manual equivalent: `docker-compose -f docker-compose-test.yml run --rm --entrypoint sh gbot-test -c "pip install -r requirements-dev.txt -q && coverage run -m pytest -q && coverage report -m"`

 The suite holds 100% line + branch coverage across every file not in the `.coveragerc` `omit` list. `fail_under = 100` makes the `report` command exit 1 on any regression — the per-file table still prints. That exit code is the coverage gate for changes touching `GBotDiscord/src`; the GitHub Actions workflow runs the plain suite and dependency audit (see Continuous Integration below).

 ## Continuous Integration

 GitHub Actions (`.github/workflows/ci.yml`) runs on every pull request and every push to `develop`:

 * `test` — installs `requirements.txt` + `requirements-dev.txt` on Python 3.13 (no Docker, no system packages needed — tests mock Firebase and Discord) and runs `python -m pytest -q`.
 * `audit` — runs `pip-audit -r requirements.txt` over the pinned runtime dependencies.
 * `changes` — flags doc/CI-only changes (`.md`, `.claude/`, `.github/`) so the `publish` job skips them.
 * `publish` — on code pushes to `develop`, builds the prod image natively on an arm64 runner and pushes `ghcr.io/cgoulart35/gbot:latest` + `:<short-sha>` (see Deployment below).

 Dependabot runs in security-updates-only mode via GitHub repository settings — there is no `dependabot.yml` version-update config. Routine dependency bumps are deliberate, tested changes.

 ### Scheduled yt-dlp bumps

 `yt-dlp` is the one pin that can't wait for a deliberate bump: YouTube breaks extractors on its own schedule, and an extractor break is never a CVE, so security-updates-only Dependabot never fires and the pin rots until someone reports that music is broken. `.github/workflows/yt-dlp-bump.yml` covers that gap — monthly (`17 7 1 * *`) plus a manual `workflow_dispatch` you can fire the moment music breaks. It resolves the latest **stable** from PyPI (`.info.version`, which excludes yt-dlp's near-daily `.dev0` nightlies), rewrites the pin, and opens a PR.

 Two inputs on the manual trigger: `target_version` pins an exact release instead of the latest (validated against PyPI, so a typo fails fast rather than opening a junk PR), and `dry_run` resolves and verifies without pushing a branch or opening anything.

 Dependabot can't do this job: scoping version-updates to yt-dlp requires `allow: [dependency-name: yt-dlp]`, and `allow` governs **security** updates too — it would quietly narrow pip security PRs to yt-dlp alone. Dropping `allow` instead floods every pip dependency with version PRs.

 The PR is opened by `GITHUB_TOKEN`, and GitHub raises no workflow events for token-created PRs, so bump PRs deliberately carry **no CI checks and no Claude review** (a version-string diff gives a reviewer nothing to work with anyway). The job compensates by running `pytest` and `pip-audit` against the new pin itself and putting the verdict table in the PR body — and it opens the PR even when verification fails, so a breaking release surfaces as a reviewable PR rather than a red run nobody opens. A bad pin still can't reach the Pi: `publish` is gated on `needs: [test]`, so a failing suite on `develop` means no image is ever built. Requires the repository's "Allow GitHub Actions to create and approve pull requests" setting.

 ### Pull-request auto-review

 Every non-draft pull request also gets an automated Claude review (`.github/workflows/claude-review.yml`, `anthropics/claude-code-action@v1`): it reads `CLAUDE.md` first — including the "Review scope — accepted trade-offs" list — and posts inline findings (🔴 must-fix / 🟠 should-fix) plus a single self-updating summary comment ("No blocking issues." when the diff is clean). Comments only; it never approves or blocks a merge. Auth is the `CLAUDE_CODE_OAUTH_TOKEN` repository secret (generated with `claude setup-token`; subscription-based, no API billing) plus the Claude GitHub App installed on the repo. Known quirk, by design: the action validates `claude-review.yml` against the **default branch** — a PR that edits it (or that runs before the file exists on `develop`) gets a green *skipped* review with a workflow-validation warning instead of a real one — so merge workflow changes on their own first.

 ## Deployment

 CI/CD is **self-contained** (no external deploy service). On every code push to `develop`, the `publish` job builds a native **arm64** image and pushes it to **GHCR** (`ghcr.io/cgoulart35/gbot:latest` + `:<short-sha>`). On the Raspberry Pi, `scripts/deploy-watcher.sh` (run at boot by the `gbot-deploy-watcher` systemd service) polls GHCR and, when a new image is published, runs `scripts/deploy.sh` — `git reset --hard origin/develop` then `docker compose -f docker-compose-prod.yml pull && up -d`. The trigger is the **published image, not the commit**, so a deploy never races the build. Doc/CI-config-only pushes (`**.md` / `.claude/` / `.github/`) are skipped by the `changes` gate, so they don't build or deploy.

 `Shared/gbot.env` / `Shared/serviceAccountKey.json` are gitignored and live **persistently in the repo dir on the Pi** — injected at runtime (`env_file:` + a volume mount), never baked into the image, and untouched by `git reset --hard`. Only the `Shared/gbot.env.example` template is tracked.

 ### One-time Pi bring-up

 1. Make the `gbot` GHCR package public (GitHub → Packages → `gbot` → Package settings) so the Pi pulls anonymously — or run `docker login ghcr.io` on the Pi instead.
 2. On the Pi checkout (`/home/cgoulart/Code/GBot`): `git checkout develop && git pull`, and verify `Shared/gbot.env` + `Shared/serviceAccountKey.json` are present.
 3. Retire the old long-running container: `docker compose -f docker-compose-dev.yml down` (the `GBot_8.0_dev` instance).
 4. First deploy: `sh scripts/deploy.sh`.
 5. Enable the `gbot-deploy-watcher` systemd service, which runs `/bin/sh scripts/deploy-watcher.sh` from the repo dir at boot and restarts it if it exits.

 The watcher logs to the journal: `journalctl -u gbot-deploy-watcher`. Poll interval defaults to 120s (`DEPLOY_POLL_INTERVAL` to override).

 ### Rollback

 Pin the previous image tag and redeploy — image tags are the release history:

 * `IMAGE_TAG=<short-sha> docker compose -f docker-compose-prod.yml up -d`

## Quart API

Private endpoints answer **401** without a valid login. All endpoints answer **400** for a request that doesn't make sense, and **500** for a failure on GBot's side, which is logged.

#### <ins>Development</ins>
<details>
<summary>Click to expand /GBot/private/development/ endpoints.</summary>

  *   <details>
      <summary>GET (/doc)</summary>

      *  Description:
         * `Returns available options to be used in POST request.`
      *  Syntax:
         * `GET - https://localhost:5004/GBot/private/development/doc/`
      *  Response:
         * `{"options":{"action":[{"name":"runDatabasePatch","patch":"7.0.0_create_leaderboard_table"},{"name":"setProperty","property":"LOG_LEVEL","value":"DEBUG"},{"name":"syncSubscribers"}]},"postBodyTemplate":{"action":{"name":"setProperty","property":"LOG_LEVEL","value":"DEBUG"}}}`
      </details>

  *   <details>
      <summary>POST</summary>

      *  Description:
         * `Use development features.`
      *  Syntax:
         * `POST - https://localhost:5004/GBot/private/development/`
      *  Body:
         * `{"action":{"name":"setProperty","property":"LOG_LEVEL","value":"DEBUG"}}`
      *  Response:
         * `{"action": "setProperty", "status": "success", "message": "Property 'LOG_LEVEL' set to: 10"}`
         * The value is coerced to the property's type before it is stored, and the message reports what was **stored** — so `LOG_LEVEL` reads back as its `logging` constant (`DEBUG` → `10`), and an int property set to `"300"` reads back as `300`.
         * A value that can't be coerced is rejected rather than stored: `{"action": "setProperty", "status": "failure", "message": "Invalid value for property 'MUSIC_TIMEOUT_SECONDS'."}`
         * A property that is unknown or intentionally immutable (`GBOT_VERSION`, `TZ`, `API_PORT`, `DISCORD_TOKEN`, `FIREBASE_CONFIG_JSON`) returns: `{"action": "setProperty", "status": "failure", "message": "Invalid property."}`
      </details>
</details>

#### <ins>Discord</ins>
<details>
<summary>Click to expand /GBot/private/discord/ endpoints.</summary>

  *   <details>
      <summary>GET (/doc)</summary>

      *  Description:
         * `Returns available options to be used in POST request.`
      *  Syntax:
         * `GET - https://localhost:5004/GBot/private/discord/doc/`
      *  Response:
         * `{"options":{"action":[{"name":"leaveGuild","serverId":"012345678910111213","optionalForce":true},{"name":"sendMessage","message":"Hello world!","channelId":"012345678910111213","optionalMessageIdForReply":"012345678910111213"},{"name":"changePresence","type":"<playing/listening/watching>","value":"my string","expire":"<%m/%d/%y %I:%M:%S %p>"}]},"postBodyTemplate":{"action":{"name":"sendMessage","message":"Hello world!","channelId":"012345678910111213","optionalMessageIdForReply":"012345678910111213"}}}`
      </details>

  *   <details>
      <summary>POST</summary>

      *  Description:
         * `Use Discord features.`
      *  Syntax:
         * `POST - https://localhost:5004/GBot/private/discord/`
      *  Body:
         * `{"action":{"name":"sendMessage","message":"Hello world!","channelId":"012345678910111213","optionalMessageIdForReply":"012345678910111213"}}`
      *  Response:
         * `{"action": "sendMessage", "status": "success"}`
      </details>
</details>

#### <ins>~~Halo~~ (DISCONTINUED)</ins>
<details>
<summary>Click to expand /GBot/private/halo/competition/ endpoints.</summary>

  *   <details>
      <summary>GET (/doc)</summary>

      *  ~~Description:~~
         * ~~`Returns available options to be used in POST request.`~~
      *  ~~Syntax:~~
         * ~~`GET - https://localhost:5004/GBot/private/halo/competition/doc/`~~
      *  ~~Response:~~
         * ~~`{"options":{"serverId":["012345678910111213","all"],"startCompetition":[true,false]},"postBodyTemplate":{"serverId":"012345678910111213","startCompetition":false}}`~~
      </details>

  *   <details>
      <summary>POST</summary>

      *  ~~Description:~~
         * ~~`Trigger Halo competition status update for individual or all servers.`~~
      *  ~~Syntax:~~
         * ~~`POST - https://localhost:5004/GBot/private/halo/competition/`~~
      *  ~~Body:~~
         * ~~`{"serverId":"012345678910111213","startCompetition":false}`~~
      *  ~~Response:~~
         * ~~`{"action": "haloPlayerStatsGetRequests(012345678910111213, False)", "status": "success"}`~~
      </details>
</details>
<details>
<summary>Click to expand /GBot/private/halo/motd/ endpoints.</summary>

  *   <details>
      <summary>GET (/doc)</summary>

      *  ~~Description:~~
         * ~~`Returns available options to be used in POST request.`~~
      *  ~~Syntax:~~
         * ~~GET - https://localhost:5004/GBot/private/halo/motd/doc/`~~
      *  ~~Response:~~
         * ~~`{"options":{"serverId":["012345678910111213","all"]},"postBodyTemplate":{"serverId":"012345678910111213"}}`~~
      </details>

  *   <details>
      <summary>POST</summary>

      *  ~~Description:~~
         * ~~`Trigger Halo MOTD update for individual or all servers.`~~
      *  ~~Syntax:~~
         * ~~`POST - https://localhost:5004/GBot/private/halo/motd/`~~
      *  ~~Body:~~
         * ~~`{"serverId":"all"}`~~
      *  ~~Response:~~
         * ~~`{"action": "haloMotdGetRequest(all)", "status": "success"}`~~
      </details>
</details>

#### <ins>Leaderboard</ins>
<details>
<summary>Click to expand /GBot/public/leaderboard/ endpoints.</summary>

  *   <details>
      <summary>GET</summary>

      *  Description:
         * `Returns data for leaderboards.`
      *  Syntax:
         * `GET - https://localhost:5004/GBot/public/leaderboard/`
      *  Response:
         * `{"012345678910111213":{"balance":"2.25","numNetStormRewards":"0.25","numStormStarts":"1","numStormTier1Multi":"0","numStormTier2Multi":"0","numStormTier3Multi":"0","numStormTier4Multi":"0","numStormWins":"0","numWhoDisRewards":"0.00","numWhoDisWins":"0","username":"userA"},"012345678910111213":{"balance":"0.50","numNetStormRewards":"0.00","numStormStarts":"0","numStormTier1Multi":"0","numStormTier2Multi":"0","numStormTier3Multi":"0","numStormTier4Multi":"0","numStormWins":"0","numWhoDisRewards":"0.00","numWhoDisWins":"0","username":"userB"},"012345678910111213":{"balance":"2.00","numNetStormRewards":"0.00","numStormStarts":"0","numStormTier1Multi":"0","numStormTier2Multi":"0","numStormTier3Multi":"0","numStormTier4Multi":"0","numStormWins":"0","numWhoDisRewards":"0.00","numWhoDisWins":"0","username":"userC"}}`
      </details>
</details>

#### <ins>Storms</ins>
<details>
<summary>Click to expand /GBot/private/storms/start/ endpoints.</summary>

  *   <details>
      <summary>GET (/doc)</summary>

      *  Description:
         * `Returns available options to be used in POST request.`
      *  Syntax:
         * `GET - https://localhost:5004/GBot/private/storms/start/doc/`
      *  Response:
         * `{"options":{"serverId":["012345678910111213","all"]},"postBodyTemplate":{"serverId":"012345678910111213"}}`
      </details>

  *   <details>
      <summary>POST</summary>

      *  Description:
         * `Trigger a new Storm for individual or all servers.`
      *  Syntax:
         * `POST - https://localhost:5004/GBot/private/storms/start/`
      *  Body:
         * `{"serverId":"012345678910111213"}`
      *  Response:
         * `{"attemptsMap":{},"fiveMinuteWarning":false,"oneMinuteWarning":false,"stormState":0,"triggerTime":"08/03/22 01:22:24 PM","winningNumber":54}`
      </details>
</details>
<details>
<summary>Click to expand /GBot/private/storms/state/ endpoints.</summary>

  *   <details>
      <summary>GET (/doc)</summary>

      *  Description:
         * `Returns available options to be used in POST request.`
      *  Syntax:
         * `GET - https://localhost:5004/GBot/private/storms/state/doc/`
      *  Response:
         * `{"options":{"serverId":["012345678910111213","all"]},"postBodyTemplate":{"serverId":"012345678910111213"}}`
      </details>

  *   <details>
      <summary>POST</summary>

      *  Description:
         * `Get an individual or all servers' Storm states.`
      *  Syntax:
         * `POST - https://localhost:5004/GBot/private/storms/state/`
      *  Body:
         * `{"serverId":"all"}`
      *  Response:
         * `{"012345678910111213":{"attemptsMap":{},"fiveMinuteWarning":false,"oneMinuteWarning":false,"stormState":0,"triggerTime":"08/03/22 03:51:22 PM","winningNumber":13},"012345678910111214":{"attemptsMap":{},"fiveMinuteWarning":false,"oneMinuteWarning":false,"stormState":1,"triggerTime":"08/03/22 01:22:24 PM","winningNumber":54}}`
      </details>
</details>