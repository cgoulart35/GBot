# GBot 2.0
Welcome to GBot! A multi-server Discord bot, Dockerized and written in Python! GBot utilizes Google Firebase Realtime Database to save server and user data.

## Features
- Server-specific configuration settings
- Weekly Halo Infinite competitions with random challenges
- Daily Halo Infinite Message of the Day checks
- (NEW) Music bot functionality to play YouTube videos

## Future Updates
- User-specific GBot currency and wallet functionality
- 'Storm' mini-games returning from [StormBot](https://github.com/cgoulart35/StormBot)

## Commands
### Config
- .channel  - Set the channel for a specific GBot feature in this server. (admin only)
- .config   - Shows the server's current GBot configuration. (admin only)
- .prefix   - Set the prefix for all GBot commands used in this server. (admin only)
- .role     - Set the role for a specific GBot feature in this server. (admin only)
- .toggle   - Turn on/off all functionality for a GBot feature in this server. (admin only)
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
10. Sign up for a Cryptum token to utilize the free [HaloDotAPI](https://developers.halodotapi.com/docs/cryptum) service (purchase developer license if exceeding free API rate limit).
11. Update the GBot/Shared/env.variables file with your Discord bot token, Cryptum token, and Firebase data.
12. Set your preferred time zone (TZ) in the GBot/Shared/env.variables file. (Ex: TZ=America/New_York)
13. Set your preferred Halo MOTD and Competition trigger times in the GBot/Shared/env.variables file. (Ex: HALO_INFINITE_COMPETITION_DAY=5 if you want competitions to start/end on Saturdays)
14. Set your preferred music bot timeout in the GBot/Shared/env.variables file. (Ex: MUSIC_TIMEOUT_SECONDS=300 if you want the music bot to leave after 5 minutes of inactivity)
15. Set your preferred cached music timeout for deletion in the GBot/Shared/env.variables file. This timeout should be set to a higher length of time than the length of the longest videos being played in elevator mode to ensure downloaded sounds aren't deleted before they should be used. (Ex: MUSIC_CACHE_DELETION_TIMEOUT_MINUTES=180 if you want the music bot to delete cached song downloads after 3 hours of not being used, and to prevent songs over 3 hours long from being played.)
16. Verify all files have read/write/execute permissions.
17. From the GBot directory, run 'docker-compose -f docker-compose-prod.yml up -d' to start the bot!