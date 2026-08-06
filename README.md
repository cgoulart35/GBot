# GBot 8.0
Welcome to GBot! A multi-server Discord bot, Dockerized and written in Python! GBot utilizes Google Firebase Realtime Database to save server and user data. Spice up your Discord server today!

## Main Features

#### <ins>Configuration Settings</ins>
- Enable or disable any of the features described below to your liking (Hype, GCoin, GTrade, Storms, Who Dis, Music).
- All commands are slash commands, however you can enable legacy prefix support to allow commands to be triggered with a prefix.
- Ability to configure an admin role & channel for admin notifications/user reports, a channel for Storm mini-games, a role for 'Who Dis?' participants, and a desired command prefix.

#### <ins>Automated & Randomized Reactions & Replies</ins> (Hype)
- Utilize and configure regular expressions to match against incoming messages to automate replies and reactions.
- Provide multiple replies or reactions for one regular expression to randomize the bot's response.

#### <ins>Currency & User Items</ins> (GCoin & GTrade)
- Every user can earn, spend, and send their GCoin balance the way they want to.
- A user's GCoin balance is carried across all Discord servers and not just limited to one server.
- Create image items and trade them with other users across all Discord servers (more coming soon).

#### <ins>Mini-Games</ins>
- Random Storm mini-games where you guess or bet on a random number from 1-200 to win GCoin.
  - In addtion to enabling Storms functionality, a channel must be configured for incoming Storms for the mini-game work.
- 'Who Dis?' mini-games where you guess a random user in the server you are anonymously paired with to win GCoin.
  - In addtion to enabling 'Who Dis?' functionality, a role must be configured for GBot to know which users are opted into 'Who Dis?'.
- Mini-games that reward users with GCoin require GCoin functionality to be enabled.

#### <ins>Music Bot</ins>
- Ability to play sounds streamed from YouTube to your active voice channel by providing a URL or generic description.
- Type less! Use Spotify activity syncing functionality to add songs playing in your Spotify activity to the bot's music queue.

#### <ins>Patreon Subscription Model</ins>
- In order to have access to GBot, you must be in a Discord server subscribed to GBot.
- GBot will leave Discord servers that are not subscribed. When GBot leaves a server, all server configuration settings will be lost.
- To add GBot to a Discord server, you must subscribe to the [GBot patreon tier here](https://www.patreon.com/StormerG). You will be prompted to join the GBot Patreon Discord Server with your Patreon-linked Discord account where you will register the desired Discord server.

## Command Glossary
![Alt text](<Slash Commands Animation.gif>)
#### <ins>Config</ins>
<details>
<summary>Click to expand Config commands.</summary>

  *   <details>
      <summary>.config channel</summary>

      *  Description:
         * `Set the channel for a specific GBot feature in this server. (admin only)`
      *  Syntax:
         * `.[config|c] [channel|ch] <channel_type> <channel>`
         * `channel_type options are: admin, storms`
      *  Example:
         * `.c ch admin #admin-channel`
      </details>

  *   <details>
      <summary>.config show</summary>

      *  Description:
         * `Shows the server's current GBot configuration. (admin only)`
      *  Syntax:
         * `.[config|c] [show|s]`
      *  Example:
         * `.c s`
      </details>

  *   <details>
      <summary>.config prefix</summary>

      *  Description:
         * `Set the prefix for all GBot commands used in this server. (admin only)`
      *  Syntax:
         * `.[config|c] [prefix|pr] <prefix>`
      *  Example:
         * `.c pr .`
      </details>

  *   <details>
      <summary>.config role</summary>

      *  Description:
         * `Set the role for a specific GBot feature in this server. (admin only)`
      *  Syntax:
         * `.[config|c] [role|rl] <role_type> <role>`
         * `role_type options are: admin`
      *  Example:
         * `.c rl admin @Admin`
      </details>

  *   <details>
      <summary>.config toggle</summary>

      *  Description:
         * `Turn on/off all functionality for a GBot feature in this server. (admin only)`
      *  Syntax:
         * `.[config|c] [toggle|t] <feature_type>`
         * `feature_type options are: gcoin, gtrade, hype, music, storms, 'who dis', 'legacy prefix commands'`
      *  Example:
         * `.c t hype`
      </details>
</details>
  
#### <ins>GCoin</ins>
<details>
<summary>Click to expand GCoin commands.</summary>
  
  *   <details>
      <summary>.gcoin history</summary>

      *  Description:
         * `Show your transaction history, or another user's transaction history in this server. Admin role needed to show other user's history. (admin optional)`
      *  Syntax:
         * `.[gcoin|gc] [history|hs] [user]`
      *  Example:
         * `.gc hs`
         * `.gc hs @MasterChief`
      </details>
  
  *   <details>
      <summary>.gcoin send</summary>

      *  Description:
         * `Send GCoin to another user in this server.`
      *  Syntax:
         * `.[gcoin|gc] [send|sd] <user> <amount>`
      *  Example:
         * `.gc sd @MasterChief 2.50`
      </details>
  
  *   <details>
      <summary>.gcoin wallet</summary>

      *  Description:
         * `Show your wallet, or another user's wallet in this server.`
      *  Syntax:
         * `.[gcoin|gc] [wallet|w] [user]`
      *  Example:
         * `.gc w`
         * `.gc w @MasterChief`
      </details>
  
  *   <details>
      <summary>.gcoin wallets</summary>

      *  Description:
         * `Show wallets of all users in this server.`
      *  Syntax:
         * `.[gcoin|gc] [wallets|ws]`
      *  Example:
         * `.gc ws`
      </details>
</details>

#### <ins>GTrade</ins>
<details>
<summary>Click to expand GTrade commands.</summary>

  *   <details>
      <summary>.gtrade buy</summary>

      *  Description:
         * `Buy another user's item for sale in the discord server. Create a request to buy from a user, complete a user's pending sell request, or buy an item for sale in the server's market.`
      *  Syntax:
         * `.[gtrade|gt] [buy|by] <user> <item>`
      *  Example:
         * `.gt by @MasterChief "gravity hammer"`
         * `.gt by @MasterChief shield`
      </details>
  
  *   <details>
      <summary>.gtrade craft</summary>

      *  Description:
         * `Craft items to show off and trade. Surround name with double quotes if multiple words.`
      *  Syntax:
         * `.[gtrade|gt] [craft|cr] <name> <value> <type>`
         * `type options are: image`
      *  Example:
         * `.gt cr "gravity hammer" 6.75 image`
         * `.gt cr shield 6.75 image`
      </details>
  
  *   <details>
      <summary>.gtrade destroy</summary>

      *  Description:
         * `Destroy an item in your inventory.`
      *  Syntax:
         * `.[gtrade|gt] [destroy|d] <item>`
      *  Example:
         * `.gt d "gravity hammer"`
         * `.gt d shield`
      </details>
  
  *   <details>
      <summary>.gtrade item</summary>

      *  Description:
         * `Show off an item in your inventory.`
      *  Syntax:
         * `.[gtrade|gt] [item|i] <item>`
      *  Example:
         * `.gt i "gravity hammer"`
         * `.gt i shield`
      </details>
  
  *   <details>
      <summary>.gtrade items</summary>

      *  Description:
         * `List all items in your inventory, or another user's inventory in this server.`
      *  Syntax:
         * `.[gtrade|gt] [items|is] [user]`
      *  Example:
         * `.gt is @MasterChief`
      </details>
  
  *   <details>
      <summary>.gtrade market</summary>

      *  Description:
         * `Show all market items for sale and personal trade requests in the discord server.`
      *  Syntax:
         * `.[gtrade|gt] [market|m]`
      *  Example:
         * `.gt m`
      </details>
  
  *   <details>
      <summary>.gtrade rename</summary>

      *  Description:
         * `Rename an item in your inventory.`
      *  Syntax:
         * `.[gtrade|gt] [rename|rn] <item> <name>`
      *  Example:
         * `.gt rn "gravity hammer" gravityHammer`
         * `.gt rn shield "my shield"`
      </details>
  
  *   <details>
      <summary>.gtrade sell</summary>

      *  Description:
         * `Sell an item to another user in this discord server. Create a request to sell to a user, complete a user's pending buy request, or place an item for sale in the server's market.`
      *  Syntax:
         * `.[gtrade|gt] [sell|sl] <item> [user]`
      *  Example:
         * `.gt sl gravityHammer @MasterChief`
         * `.gt sl "my shield"`
      </details>
</details>  
  
#### <ins>~~Halo~~ (DISCONTINUED)</ins>
<details>
<summary>Click to expand Halo commands.</summary>

  *   <details>
      <summary>.halo</summary>

      *  ~~Description:~~
         * ~~`Participate in or leave the weekly GBot Halo competition. (admin optional)`~~
      *  ~~Syntax:~~
         * ~~`.[halo|h] [action] [user]`~~
         * ~~`action options are: <gamertag>, rm`~~
      *  ~~Example:~~
         * ~~`.h XboxGamerTag`~~
         * ~~`.h rm`~~
         * ~~`.halo XboxGamerTag @MasterChief`~~
         * ~~`.halo rm @MasterChief`~~
      </details>
</details>
  
#### <ins>Hype</ins>
<details>
<summary>Click to expand Hype commands.</summary>

  *   <details>
      <summary>.hype respond</summary>

      *  Description:
         * `Set a regular expression to match against new messages in this server, and a list of possible responses to reply to it with. Surround regex and response each with double quotes if multiple words. (admin only)`
      *  Syntax:
         * `.[hype|hy] [respond|rs] [regex] [reply]`
      *  Example:
         * `.hy rs "Hello there!" "General Kenobi!" "You fool! I've been trained in your Jedi arts by Count Dooku."`
         * `.hy rs "It's over Anakin, I have the high ground." "You underestimate my power!"`
      </details>

  *   <details>
      <summary>.hype react</summary>

      *  Description:
         * `Set a regular expression to match against new messages in this server, and a list of possible emojis to react to it with. Surround regex with double quotes if multiple words. (admin only)`
      *  Syntax:
         * `.[hype|hy] [react|re] [regex] [emoji]`
      *  Example:
         * `.hy re "How are you feeling?" 😊🙁`
         * `.hy re "Vrrm vrrm" 🚗`
      </details>

  *   <details>
      <summary>.hype remove</summary>

      *  Description:
         * `Remove an existing regular expression match response in this server. (admin only)`
      *  Syntax:
         * `.[hype|hy] [remove|rm]`
      *  Example:
         * `.hy rm`
      </details>      
</details>

#### <ins>Help</ins>
<details>
<summary>Click to expand Help commands.</summary>

  *   <details>
      <summary>.help</summary>

      *  Description:
         * `Type .help command for more info on a command. You can also type .help category for more info on a category.`
      *  Syntax:
         * `.help [command]`
      *  Example:
         * `.help`
         * `.help GTrade`
         * `.help cr`
      </details>
</details>

#### <ins>Music</ins>
<details>
<summary>Click to expand Music commands.</summary>

  *   <details>
      <summary>.music elevator</summary>

      *  Description:
         * `Toggle elevator mode to keep the last played sound on repeat.`
      *  Syntax:
         * `.[music|m] [elevator|e]`
      *  Example:
         * `.m e`
      </details>
  
  *   <details>
      <summary>.music pause</summary>

      *  Description:
         * `Pauses the current sound being played.`
      *  Syntax:
         * `.[music|m] [pause|ps]`
      *  Example:
         * `.m ps`
      </details>
  
  *   <details>
      <summary>.music play</summary>

      *  Description:
         * `Play videos/music streamed from YouTube. Accepts a search, a video URL, a livestream, or a playlist.`
      *  Syntax:
         * `.[music|m] [play|p] [args...]`
      *  Example:
         * `.m p halo theme song`
         * `.m p https://youtu.be/dQw4w9WgXcQ`
      </details>
  
  *   <details>
      <summary>.music queue</summary>

      *  Description:
         * `Displays the current sounds in queue.`
      *  Syntax:
         * `.[music|m] [queue|q]`
      *  Example:
         * `.m q`
      </details>
  
  *   <details>
      <summary>.music resume</summary>

      *  Description:
         * `Resumes the current sound being played.`
      *  Syntax:
         * `.[music|m] [resume|r]`
      *  Example:
         * `.m r`
      </details>
  
  *   <details>
      <summary>.music skip</summary>

      *  Description:
         * `Skips the current sound being played.`
      *  Syntax:
         * `.[music|m] [skip|s]`
      *  Example:
         * `.m s`
      </details>
  
  *   <details>
      <summary>.music spotify</summary>

      *  Description:
         * `Play current spotify activity streamed from YouTube. Songs are added to the queue as the user's activity changes.`
      *  Syntax:
         * `.[music|m] [spotify|sp] [user]`
      *  Example:
         * `.m sp`
         * `.m sp @MasterChief`
      </details>

  *   <details>
      <summary>.music stop</summary>

      *  Description:
         * `Stops the bot from playing sounds and clears the queue.`
      *  Syntax:
         * `.[music|m] [stop|st]`
      *  Example:
         * `.m st`
      </details>
</details>

#### <ins>Patreon</ins>
<details>
<summary>Click to expand Patreon commands.</summary>

  *   <details>
      <summary>.patreon</summary>

      *  Description:
         * `In the GBot Patreon server, specify a server's ID to enable GBot functionality in that server. (patrons only)`
      *  Syntax:
         * `.[patreon|pt] <server_id>`
      *  Example:
         * `.pt 012345678910111213`
      </details>
</details>

#### <ins>Storms</ins>
<details>
<summary>Click to expand Storms commands.</summary>

  *   <details>
      <summary>.storms bet</summary>

      *  Description:
         * `Make a guess. If you win, you earn the amount of points bet within your wallet. If you lose, you lose those points. Multiplier applied for guesses made in 4 attempts or less.`
      *  Syntax:
         * `.[storms|s] [bet|b] <gcoin> <number>`
      *  Example:
         * `.s b 5.00 65`
      </details>

  *   <details>
      <summary>.storms guess</summary>

      *  Description:
         * `Make a guess with a winning reward of 1.00 GCoin. Multiplier applied for guesses made in 4 attempts or less.`
      *  Syntax:
         * `.[storms|s] [guess|g] <number>`
      *  Example:
         * `.s g 50`
      </details>

  *   <details>
      <summary>.storms umbrella</summary>

      *  Description:
         * `Start the incoming Storm and earn 0.25 GCoin.`
      *  Syntax:
         * `.[storms|s] [umbrella|u]`
      *  Example:
         * `.s u`
      </details>
</details>

#### <ins>Who Dis</ins>
<details>
<summary>Click to expand Who Dis commands.</summary>

  *   <details>
      <summary>.whodis start</summary>

      *  Description:
         * `Start or end a mini-game where you try to guess a random user in the server you are paired with. You have 1 guess, and if you guess correctly you earn GCoin.`
      *  Syntax:
         * `.[whodis|wd] [start|s]`
      *  Example:
         * `.wd s`
      </details>

  *   <details>
      <summary>.whodis guess</summary>

      *  Description:
         * `Guess the name of the user you are paired with for a chance to win GCoin.`
      *  Syntax:
         * `.[whodis|wd] [guess|g] <user>`
      *  Example:
         * `.wd g jonsnow1234`
      </details>

  *   <details>
      <summary>.whodis leave</summary>

      *  Description:
         * `Remove the server's 'Who Dis?' role opting you out of any future games.`
      *  Syntax:
         * `.[whodis|wd] [leave|l]`
      *  Example:
         * `.wd l`
      </details>

  *   <details>
      <summary>.whodis report</summary>

      *  Description:
         * `Report a user to server admins for bad behavior. The reported user's last 5 messages will be captured from the channel sent in, or an ongoing Who Dis game.`
      *  Syntax:
         * `.[whodis|wd] [report|rp]`
      *  Example:
         * `.wd rp`
         * `.wd rp @CerseiLannister`
      </details>
</details>

# GBot Development

## Changelog

#### GBot 8.0
*The 2026 modernization — a rebuild of everything under the bot, alongside the user-facing changes.*

- <ins>Grouped commands</ins> — every command now lives under its cog for both slash and prefix (`/music play`, `.music play`, `.m p`), replacing 36 global command names with 8. This is also what freed the names behind the renames: `.dis` → `.whodis guess`, `.leavedis` → `.whodis leave`, `.hype` → `.hype respond`, `.unmatch` → `.hype remove`, `.config` → `.config show`
- <ins>Music restored and rebuilt</ins> — every voice feature had been dead in production since 2026-03-02, when Discord made end-to-end encryption mandatory for voice. Playback works again and is substantially better: Opus passthrough instead of re-encoding every frame, livestream and playlist support, and video links and lengths in the now-playing message
- <ins>Python 3.13</ins> base image and <ins>nextcord 3.2</ins>, with every dependency repinned
- <ins>Zero known vulnerabilities</ins> — Pyrebase4 replaced by `firebase-admin`, and `pip-audit` runs clean on every pull request
- <ins>100% test coverage</ins> of `GBotDiscord/src`, line and branch, enforced as a merge gate rather than a target
- <ins>Continuous delivery</ins> — GitHub Actions builds a native arm64 image on every push and the Raspberry Pi redeploys itself from it; the old git-pull update handler is retired
- <ins>Automated pull-request review</ins> on every PR, plus a scheduled job that bumps and verifies `yt-dlp` so a YouTube extractor break never sits unnoticed

#### GBot 7.0
- (NEW) <ins>Who Dis</ins> random user chat mini-game functionality
- (NEW) GBot <ins>Leaderboards</ins> track live statistics on new [GBot-Docs](https://cgoulart35.github.io/GBot-Docs/) site

#### GBot 6.0
- <ins>Slash command</ins> functionality for all commmands (Config, GCoin, GTrade, Hype, Music, Patreon, and Storms)
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
15. Set the Patreon URL to promote subscribing when users are unable to execute commands. (Ex: PATREON_URL=https://www.patreon.com/\<INSERT-PATREON-PAGE-NAME\>)
16. Set the Discord IDs of the guild and role that will be used for Patreon integration. (Ex: PATREON_GUILD_ID=012345678910111213 and PATRON_ROLE_ID=012345678910111213)
17. Set the comma delimited list of Discord guild IDs that will bypass Patreon validation. (Ex: PATREON_IGNORE_GUILDS=012345678910111213,012345678910111213,012345678910111213)
18. Set your preferred timeout for user responses to GBot messages. (Ex: USER_RESPONSE_TIMEOUT_SECONDS=300 if you want the bot to stop listening for a user response after 5 minutes)
19. ~~Set your preferred Halo MOTD and Competition trigger times in the GBot/Shared/gbot.env file. (Ex: HALO_INFINITE_COMPETITION_DAY=5 if you want competitions to start/end on Saturdays)~~
20. Set your preferred music bot timeout in the GBot/Shared/gbot.env file. (Ex: MUSIC_TIMEOUT_SECONDS=300 if you want the music bot to leave after 5 minutes of inactivity)
21. Set the longest song the music bot will accept in the GBot/Shared/gbot.env file. (Ex: MUSIC_MAX_DURATION_MINUTES=180 if you want to prevent songs over 3 hours long from being played.) Livestreams are exempt — they have no length to limit.
22. Set how many songs a pasted playlist may add to the queue in the GBot/Shared/gbot.env file. (Ex: MUSIC_MAX_PLAYLIST_SONGS=50 if you want a playlist to contribute at most 50 songs; anything beyond is dropped and the reply says so.)
23. Set your preferred transaction request timeout for buy and sell requests to be cancelled. (Ex: GTRADE_TRANSACTION_REQUEST_TIMEOUT_MINUTES=5 if you want transaction requests to be cancelled after 5 minutes of not being accepted.)
24. Set your preferred market sale timeout for market sales to be taken down. (Ex: GTRADE_MARKET_SALE_TIMEOUT_HOURS=3 if you want market sales to be taken down after 3 hours of no completed transaction.)
25. Set your preferred minimum amount of time between random Storms minigames. (Ex: STORMS_MIN_TIME_BETWEEN_SECONDS=3600 if you want there to be at least 1 hour between each Storm.)
26. Set your preferred maximum amount of time between random Storms minigames. (Ex: STORMS_MAX_TIME_BETWEEN_SECONDS=14400 if you want there to be at most 4 hours between each Storm.)
27. Set your preferred amount of time for Storms-related messages to be deleted after. (Ex: STORMS_DELETE_MESSAGES_AFTER_SECONDS=60 if you want Storm-related messages to be deleted after 60 seconds.)
28. Set your preferred 'Who Dis?' timeout in the GBot/Shared/gbot.env file. (Ex: WHODIS_TIMEOUT_MINUTES=5 if you want Who Dis games to timeout after 5 minutes)
29. If you are a developer, set your development guild IDs in the GBot/Shared/gbot.env file. (Ex: SLASH_COMMAND_TEST_GUILDS=012345678910111213,012345678910111213,012345678910111213 if you want to register the slash commands only in specific guilds)
30. Verify all files have read/write/execute permissions.
31. From the GBot directory, run 'docker-compose -f docker-compose-prod.yml up -d --build' to build and start the bot! (Without `--build`, compose pulls the published `ghcr.io/cgoulart35/gbot` image instead of building your local checkout.)

 ## Bot Identities & Manual QA

 There are two Discord applications — **`gbot.prod01`** (`GBot#6890`, the bot real users talk to) and **`gbot.dev01`** (`GBot#9690`) — differing only by `DISCORD_TOKEN` and sharing one Firebase project. **Both run on the Pi**, from `docker-compose-prod.yml` and `docker-compose-dev.yml` respectively.

 The governing rule is **one token runs in exactly one place at a time**: two connections on the same application receive every gateway event twice, so every storm tick, hype match and command fires twice. QA is therefore a **borrow and return** — stop the identity you want on the Pi, run it locally, put it back when you're done. The other identity keeps serving throughout.

 Each identity has its own compose file naming its own gitignored env file in `Shared/`: `docker-compose-prod.yml` → `gbot.env`, `docker-compose-dev.yml` → `gbot.env.dev`. Only `gbot.env.example` is tracked. `scripts/qa.sh` simply picks which compose file to bring up.

 ### QA with the dev identity (recommended)

 Borrowing `gbot.dev01` **leaves the production bot serving real users**, so this is the default:

 ```bash
 ssh StormerPi2 'cd ~/Code/GBot && docker compose -f docker-compose-dev.yml down'   # free the identity
 QA_CONFIRM=yes scripts/qa.sh up      # builds the working tree as :qa, runs it as gbot.dev01
 scripts/qa.sh logs 40                # expect "GBot logged in as GBot#9690."
 scripts/qa.sh down
 ssh StormerPi2 'cd ~/Code/GBot && docker compose -f docker-compose-dev.yml up -d'  # return it
 ```

 ### QA with the production identity

 Only for changes that genuinely need it — a real guild's data, or a Patreon-gated path in a really-subscribed server. Same cycle against `docker-compose-prod.yml` (bring it back with `scripts/deploy.sh`, which also re-syncs the checkout), but it costs real downtime:

 ```bash
 QA_CONFIRM=yes scripts/qa.sh up prod # expect "GBot logged in as GBot#6890."
 ```

 Either way the build is tagged `:qa`, so it is invisible to the Pi's deploy watcher (which only compares `:latest`) and can never trigger a redeploy. **Nothing on the Pi restarts a borrowed instance for you** — the watcher only reacts to a newly published `:latest`, and only for prod — so returning it is a manual step you must not skip.

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

 CI/CD is **self-contained** (no external deploy service). On every code push to `develop`, the `publish` job builds a native **arm64** image and pushes it to **GHCR** (`ghcr.io/cgoulart35/gbot:latest` + `:<short-sha>`). On the Raspberry Pi, `scripts/deploy-watcher.sh` (started at boot from `/etc/rc.local`) polls GHCR and, when a new image is published, runs `scripts/deploy.sh` — `git reset --hard origin/develop` then `docker compose -f docker-compose-prod.yml pull && up -d`. The trigger is the **published image, not the commit**, so a deploy never races the build. Doc/CI-config-only pushes (`**.md` / `.claude/` / `.github/`) are skipped by the `changes` gate, so they don't build or deploy.

 `Shared/gbot.env` / `Shared/serviceAccountKey.json` are gitignored and live **persistently in the repo dir on the Pi** — injected at runtime (`env_file:` + a volume mount), never baked into the image, and untouched by `git reset --hard`. Only the `Shared/gbot.env.example` template is tracked.

 ### One-time Pi bring-up

 1. Make the `gbot` GHCR package public (GitHub → Packages → `gbot` → Package settings) so the Pi pulls anonymously — or run `docker login ghcr.io` on the Pi instead.
 2. On the Pi checkout (`/home/cgoulart/Code/GBot`): `git checkout develop && git pull`, and verify `Shared/gbot.env` + `Shared/serviceAccountKey.json` are present.
 3. Retire the old long-running container: `docker compose -f docker-compose-dev.yml down` (the `GBot_8.0_dev` instance).
 4. First deploy: `sh scripts/deploy.sh`.
 5. Start the watcher now with `sh scripts/start.sh`, and at every boot by adding this line to `/etc/rc.local`:
    * `su - cgoulart -c "sh /home/cgoulart/Code/GBot/scripts/start.sh"`

 The watcher logs to `Logs/deploy-watcher.log` (gitignored). Poll interval defaults to 120s (`DEPLOY_POLL_INTERVAL` to override).

 ### Rollback

 Pin the previous image tag and redeploy — image tags are the release history:

 * `IMAGE_TAG=<short-sha> docker compose -f docker-compose-prod.yml up -d`

## Quart API

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
         * `{"options":{"action":[{"name":"leaveGuild","serverId":"012345678910111213"},{"name":"sendMessage","message":"Hello world!","channelId":"012345678910111213","optionalMessageIdForReply":"012345678910111213"},{"name":"changePresence","type":"<playing/listening/watching>","value":"my string","expire":"<%m/%d/%y %I:%M:%S %p>"}]},"postBodyTemplate":{"action":{"name":"sendMessage","message":"Hello world!","channelId":"012345678910111213","optionalMessageIdForReply":"012345678910111213"}}}`
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