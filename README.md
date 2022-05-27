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

## Command Glossary

### <ins>Config</ins>
<details>
<summary>Click to expand Config commands.</summary>

  *   <details>
      <summary>.channel</summary>

      *  Description:
         * `Set the channel for a specific GBot feature in this server. (admin only)`
      *  Syntax:
         * `.channel <channelType> <channel>`
         * `channelType options are: admin, halo-motd, halo-competition`
      *  Example:
         * `.channel halo-competition #🏆halo-weekly-scores`
      </details>

  *   <details>
      <summary>.config</summary>

      *  Description:
         * `Shows the server's current GBot configuration. (admin only)`
      *  Syntax:
         * `.config`
      *  Example:
         * `.config`
      </details>

  *   <details>
      <summary>.prefix</summary>

      *  Description:
         * `Set the prefix for all GBot commands used in this server. (admin only)`
      *  Syntax:
         * `.prefix <prefix>`
      *  Example:
         * `.prefix .`
      </details>

  *   <details>
      <summary>.role</summary>

      *  Description:
         * `Set the role for a specific GBot feature in this server. (admin only)`
      *  Syntax:
         * `.role <roleType> <role>`
         * `roleType options are: admin, halo-recent-win, halo-most-wins`
      *  Example:
         * `.role halo-recent-win @🛰️🛡️Spartan`
      </details>

  *   <details>
      <summary>.toggle</summary>

      *  Description:
         * `Turn on/off all functionality for a GBot feature in this server. (admin only)`
      *  Syntax:
         * `.toggle <featureType>`
         * `featureType options are: gcoin, gtrade, halo, music`
      *  Example:
         * `.toggle halo`
      </details>
</details>
  
### <ins>GCoin</ins>
<details>
<summary>Click to expand GCoin commands.</summary>
  
  *   <details>
      <summary>.history</summary>

      *  Description:
         * `Show your transaction history, or another user's transaction history in this server. Admin role needed to show other user's history. (admin optional)`
      *  Syntax:
         * `.[history|hs] [user]`
      *  Example:
         * `.hs`
         * `.hs @MasterChief`
      </details>
  
  *   <details>
      <summary>.send</summary>

      *  Description:
         * `Send GCoin to another user in this server.`
      *  Syntax:
         * `.[send|sd] <user> <amount>`
      *  Example:
         * `.sd @MasterChief 2.50`
      </details>
  
  *   <details>
      <summary>.wallet</summary>

      *  Description:
         * `Show your wallet, or another user's wallet in this server.`
      *  Syntax:
         * `.[wallet|w] [user]`
      *  Example:
         * `.w`
         * `.w @MasterChief`
      </details>
  
  *   <details>
      <summary>.wallets</summary>

      *  Description:
         * `Show wallets of all users in this server.`
      *  Syntax:
         * `.[wallets|ws]`
      *  Example:
         * `.ws`
      </details>
</details>

### <ins>GTrade</ins>
<details>
<summary>Click to expand GTrade commands.</summary>

  *   <details>
      <summary>.buy</summary>

      *  Description:
         * `Buy another user's item for sale in the discord server. Create a request to buy from a user, complete a user's pending sell request, or buy an item for sale in the server's market.`
      *  Syntax:
         * `.[buy|b] <item> <user>`
      *  Example:
         * `.b "gravity hammer" @MasterChief`
         * `.buy shield @MasterChief`
      </details>
  
  *   <details>
      <summary>.craft</summary>

      *  Description:
         * `Craft items to show off and trade. Surround name with double quotes if multiple words.`
      *  Syntax:
         * `.[craft|cr] <name> <value> <type>`
         * `type options are: image`
      *  Example:
         * `.cr "gravity hammer" 6.75 image`
         * `.craft shield 6.75 image`
      </details>
  
  *   <details>
      <summary>.destroy</summary>

      *  Description:
         * `Destroy an item in your inventory.`
      *  Syntax:
         * `.[destroy|d] <item>`
      *  Example:
         * `.d "gravity hammer"`
         * `.destroy shield`
      </details>
  
  *   <details>
      <summary>.item</summary>

      *  Description:
         * `Show off an item in your inventory.`
      *  Syntax:
         * `.[item|i] <item>`
      *  Example:
         * `.i "gravity hammer"`
         * `.item shield`
      </details>
  
  *   <details>
      <summary>.items</summary>

      *  Description:
         * `List all items in your inventory, or another user's inventory in this server.`
      *  Syntax:
         * `.[items|is] [user]`
      *  Example:
         * `.is @MasterChief`
      </details>
  
  *   <details>
      <summary>.market</summary>

      *  Description:
         * `Show all market items for sale and personal trade requests in the discord server.`
      *  Syntax:
         * `.[market|m]`
      *  Example:
         * `.m`
      </details>
  
  *   <details>
      <summary>.rename</summary>

      *  Description:
         * `Rename an item in your inventory.`
      *  Syntax:
         * `.[rename|rn] <item> <name>`
      *  Example:
         * `.rn "gravity hammer" gravityHammer`
         * `.rename shield "my shield"`
      </details>
  
  *   <details>
      <summary>.sell</summary>

      *  Description:
         * `Sell an item to another user in this discord server. Create a request to sell to a user, complete a user's pending buy request, or place an item for sale in the server's market.`
      *  Syntax:
         * `.[sell|sl] <item> [user]`
      *  Example:
         * `.sl gravityHammer @MasterChief`
         * `.sell "my shield"`
      </details>
</details>  
  
### <ins>Music</ins>
<details>
<summary>Click to expand Music commands.</summary>

  *   <details>
      <summary>.elevator</summary>

      *  Description:
         * `Toggle elevator mode to keep the last played sound on repeat.`
      *  Syntax:
         * `.[elevator|e]`
      *  Example:
         * `.e`
      </details>
  
  *   <details>
      <summary>.pause</summary>

      *  Description:
         * `Pauses the current sound being played.`
      *  Syntax:
         * `.[pause|pa|ps] `
      *  Example:
         * `.ps`
      </details>
  
  *   <details>
      <summary>.play</summary>

      *  Description:
         * `Play videos/music downloaded from YouTube. No playlists or livestreams.`
      *  Syntax:
         * `.[play|p|pl] [args...]`
      *  Example:
         * `.p halo theme song`
         * `.pl https://youtu.be/dQw4w9WgXcQ`
      </details>
  
  *   <details>
      <summary>.queue</summary>

      *  Description:
         * `Displays the current sounds in queue.`
      *  Syntax:
         * `.[queue|q]`
      *  Example:
         * `.q`
      </details>
  
  *   <details>
      <summary>.resume</summary>

      *  Description:
         * `Resumes the current sound being played.`
      *  Syntax:
         * `.[resume|r]`
      *  Example:
         * `.r`
      </details>
  
  *   <details>
      <summary>.skip</summary>

      *  Description:
         * `Skips the current sound being played.`
      *  Syntax:
         * `.[skip|s|sk]`
      *  Example:
         * `.s`
      </details>
  
  *   <details>
      <summary>.stop</summary>

      *  Description:
         * `Stops the bot from playing sounds and clears the queue.`
      *  Syntax:
         * `.[stop|st] `
      *  Example:
         * `.sk`
      </details>
</details>
  
### <ins>Halo</ins>
<details>
<summary>Click to expand Halo commands.</summary>

  *   <details>
      <summary>.halo</summary>

      *  Description:
         * `Participate in or leave the weekly GBot Halo competition. (admin optional)`
      *  Syntax:
         * `.[halo|h] [action] [user]`
         * `action options are: <gamertag>, rm`
      *  Example:
         * `.h XboxGamerTag`
         * `.h rm`
         * `.halo XboxGamerTag @MasterChief`
         * `.halo rm @MasterChief`
      </details>
</details>
  
### <ins>Help</ins>
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

## Setup Guide
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
13. Set the Git Project Update Handler URL if you would like to utilize streamlined Git upgrades. (GIT_UPDATER_HOST=http://<INSERT-HANDLER-HOSTNAME-AND-PORT>)
14. Set your preferred timeout for user responses to GBot messages. (Ex: USER_RESPONSE_TIMEOUT_SECONDS=300 if you want the bot to stop listening for a user response after 5 minutes)
15. Set your preferred Halo MOTD and Competition trigger times in the GBot/Shared/env.variables file. (Ex: HALO_INFINITE_COMPETITION_DAY=5 if you want competitions to start/end on Saturdays)
16. Set your preferred music bot timeout in the GBot/Shared/env.variables file. (Ex: MUSIC_TIMEOUT_SECONDS=300 if you want the music bot to leave after 5 minutes of inactivity)
17. Set your preferred cached music timeout for deletion in the GBot/Shared/env.variables file. This timeout should be set to a higher length of time than the length of the longest videos being played in elevator mode to ensure downloaded sounds aren't deleted before they should be used. (Ex: MUSIC_CACHE_DELETION_TIMEOUT_MINUTES=180 if you want the music bot to delete cached song downloads after 3 hours of not being used, and to prevent songs over 3 hours long from being played.)
18. Set your preferred transaction request timeout for buy and sell requests to be cancelled. (Ex: GTRADE_TRANSACTION_REQUEST_TIMEOUT_SECONDS=300 if you want transaction requests to be cancelled after 5 minutes of not being accepted.)
19. Set your preferred market sale timeout for market sales to be taken down. (Ex: GTRADE_MARKET_SALE_TIMEOUT_MINUTES=180 if you want market sales to be taken down after 3 hours of no completed transaction.)
20. Verify all files have read/write/execute permissions.
21. From the GBot directory, run 'docker-compose -f docker-compose-prod.yml up -d' to start the bot!

 ## Unit Tests
 * To execute all unit tests (for all cog suites), use the "Python: Current File" run configuration to run tests.py.
 * To execute unit tests for a single cog suite (replace \<cog\> with the cog you would like to test):
   * use the "Python: Current File" run configuration to run \<cog\>_test.py.
   * or execute the following command from the "GBot" directory:
      * python -m unittest GBotDiscord/\<cog\>/\<cog\>_test.py
      * Note: To avoid import errors, please make sure to run the above command from the "GBot" directory.

## API

### <ins>Development</ins>
<details>
<summary>Click to expand /GBot/development endpoints.</summary>

  *   <details>
      <summary>GET</summary>

      *  Description:
         * `Returns available options to be used in POST request.`
      *  Syntax:
         * `GET - http://localhost:5004/GBot/development`
      *  Response:
         * `{"options":["doRebuildLatest"],"postBodyTemplate":{"doRebuildLatest":true}}`
      </details>

  *   <details>
      <summary>POST</summary>

      *  Description:
         * `Use development features.`
      *  Syntax:
         * `POST - http://localhost:5004/GBot/development`
      *  Body:
         * `{"doRebuildLatest": true}`
      *  Response:
         * `{"action": "doRebuildLatest", "status": "success", "message": "Starting GBot upgrade..."}`
      </details>
</details>