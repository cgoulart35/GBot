# GBot 1.0
Welcome to GBot! A multi-server Discord bot, Dockerized and written in Python! GBot utilizes Google Firebase Realtime Database to save server and user data.

## Features
- Server-specific configuration settings
- Weekly Halo Infinite competitions with random challenges
- Daily Halo Infinite Message of the Day checks

## Future Updates
- Music bot functionality to play YouTube videos
- User-specific GBot currency and wallet functionality
- 'Storm' mini-games returning from [StormBot](https://github.com/cgoulart35/StormBot)

## Commands

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
         * `featureType options are: halo`
      *  Example:
         * `.toggle halo`
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
         * `.help Config`
         * `.help role`
      </details>
</details>
  
## Setup Guide

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
13. Set your preferred Halo MOTD and Competition trigger times in the GBot/Shared/env.variables file. (Ex: HALO_INFINITE_COMPETITION_DAY=5 if you want competitions to start/end on Saturdays)
14. Verify all files have read/write/execute permissions.
15. From the GBot directory, run 'docker-compose -f docker-compose-prod.yml up -d' to start the bot!