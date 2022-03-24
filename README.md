# GBot 3.0
Welcome to GBot! A multi-server Discord bot, Dockerized and written in Python! GBot utilizes Google Firebase Realtime Database to save server and user data.

## Features
- Server-specific configuration settings
- Weekly Halo Infinite competitions with random challenges
- Daily Halo Infinite Message of the Day checks
- Music bot functionality to play YouTube videos
- (NEW) User-specific GCoin currency and transaction functionality
- (NEW) User-specific GTrade items and crafting functionality
- (NEW) Halo Infinite competition enhancement with GCoin integration

## Future Updates
- GTrade enhancement with item value appreciation and new item types
- 'Storm' mini-games returning from [StormBot](https://github.com/cgoulart35/StormBot)

## Commands
### Config
- .channel  - Set the channel for a specific GBot feature in this server. (admin only)
- .config   - Shows the server's current GBot configuration. (admin only)
- .prefix   - Set the prefix for all GBot commands used in this server. (admin only)
- .role     - Set the role for a specific GBot feature in this server. (admin only)
- .toggle   - Turn on/off all functionality for a GBot feature in this server. (admin only)
### GCoin
- .send     - Send GCoin to another user in this server.
- .history  - Show your transaction history, or another user's transaction history in this server. (admin optional)
- .wallet   - Show your wallet, or another user's wallet in this server.
- .wallets  - Show wallets of all users in this server.
### GTrade
- .craft    - Craft items to show off and trade.
- .rename   - Rename an item in your inventory.
- .destroy  - Destroy an item in your inventory.
- .items    - List all items in your inventory, or another user's inventory in this server.
- .item     - Show off an item in your inventory.
- .market   - Show all market items for sale and personal trade requests in the discord server.
- .buy      - Buy another user's item for sale in the discord server.
- .sell     - Sell an item to another user in this discord server.
### Music
- .pause    - Pauses the current sound being played.
- .play     - Play videos/music downloaded from YouTube.
- .queue    - Displays the current sounds in queue.
- .resume   - Resumes the current sound being played.
- .skip     - Skips the current sound being played.
- .stop     - Stops the bot from playing sounds and clears the queue.
- .elevator - Toggle elevator mode to keep the last played sound on repeat.
### Halo
- .halo     - Participate in or leave the weekly GBot Halo competition. (admin optional)
### Help
- .help     - Get more info on commands, or commands in a certain category.

## Setup
1. Clone GBot.
2. Install Docker (and Docker compose if on Linux).
3. Create a [Google Firebase Realtime Database](https://console.firebase.google.com/) project.
4. Create a user for authentication and a service account in project settings.
5. Download the service account key .json file to the GBot/Shared/ directory and rename it to serviceAccountKey.json.
6. Navigate to project settings and copy your Firebase configuration variables into the following json string respectively and save it:
{"apiKey":"","authDomain":"","databaseURL":"","projectId":"","storageBucket":"","messagingSenderId":"","appId":"","measurementId":"","serviceAccount":"/GBot/Shared/serviceAccountKey.json"}
7. Create a Discord bot project in the [Discord Developer Portal](https://discord.com/developers/applications) and save the bot token.
8. Under the Discord bot project's bot settings, enable all intents and add the bot to your server with administrator privileges.
9. Move GBot's role above other roles you create in the server that GBot will assign to server members.
10. Sign up for an Autocode token to utilize the free [Halo API](https://autocode.com/lib/halo/infinite/) service.
11. Update the GBot/Shared/env.variables file with your Discord bot token, Autocode token, and Firebase data.
12. Set your preferred time zone (TZ) in the GBot/Shared/env.variables file. (Ex: TZ=America/New_York)
13. Set your preferred timeout for user responses to GBot messages. (Ex: USER_RESPONSE_TIMEOUT_SECONDS=300 if you want the bot to stop listening for a user response after 5 minutes)
14. Set your preferred Halo MOTD and Competition trigger times in the GBot/Shared/env.variables file. (Ex: HALO_INFINITE_COMPETITION_DAY=5 if you want competitions to start/end on Saturdays)
15. Set your preferred music bot timeout in the GBot/Shared/env.variables file. (Ex: MUSIC_TIMEOUT_SECONDS=300 if you want the music bot to leave after 5 minutes of inactivity)
16. Set your preferred cached music timeout for deletion in the GBot/Shared/env.variables file. This timeout should be set to a higher length of time than the length of the longest videos being played in elevator mode to ensure downloaded sounds aren't deleted before they should be used. (Ex: MUSIC_CACHE_DELETION_TIMEOUT_MINUTES=180 if you want the music bot to delete cached song downloads after 3 hours of not being used, and to prevent songs over 3 hours long from being played.)
17. Set your preferred transaction request timeout for buy and sell requests to be cancelled. (Ex: GTRADE_TRANSACTION_REQUEST_TIMEOUT_SECONDS=300 if you want transaction requests to be cancelled after 5 minutes of not being accepted.)
18. Set your preferred market sale timeout for market sales to be taken down. (Ex: GTRADE_MARKET_SALE_TIMEOUT_MINUTES=180 if you want market sales to be taken down after 3 hours of no completed transaction.)
19. Verify all files have read/write/execute permissions.
20. From the GBot directory, run 'docker-compose -f docker-compose-prod.yml up -d' to start the bot!