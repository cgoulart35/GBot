#region IMPORTS
import asyncio
import logging
from urllib.parse import urlparse
import nextcord
from nextcord import Spotify
from nextcord.ext import commands, tasks
from nextcord.ext.commands.context import Context
from yt_dlp import YoutubeDL

from GBotDiscord.src import strings
from GBotDiscord.src import utils
from GBotDiscord.src import pagination
from GBotDiscord.src import predicates
from GBotDiscord.src.config import config_queries
from GBotDiscord.src.properties import GBotPropertiesManager
#endregion

class Music(commands.Cog):

    def __init__(self, client: nextcord.Client):
        self.client = client
        self.logger = logging.getLogger()
        self.ytdlLogger = self.YTDLPLogger(self)

        self.FFMPEG_OPTIONS = {
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            'options': '-vn'}
        # search-only options: playback always streams the resolved CDN URL, so there is no
        # outtmpl or audio-extraction postprocessor here — nothing is ever written to disk (C-8)
        self.YT_DLP_OPTIONS = {
            'format': 'bestaudio/best',
            'noplaylist': True,
            'logger': self.ytdlLogger
        }

        self.spotifySyncSessions = {}
        self.musicStates = {}

    def newLastPlayed(self):
        # one shape, built in three places (both state initializers and disconnectAndClearQueue).
        # 'song' is the same dict the queue holds, so everything that renders a song renders this
        # one identically — and it deliberately carries no stream URL (C-6/C-14): that link expires,
        # and is resolved fresh in playMusic every time instead.
        return {'song': None, 'channel': None}

    # Events
    @commands.Cog.listener()
    async def on_guild_join(self, guild: nextcord.Guild):
        self.logger.info(f'Adding server music state for guild {guild.id} ({guild.name}).')
        serverMusicState = {
            'isPlaying': False,
            'isElevatorMode': False,
            'voiceClient': None,
            'queue': [],
            'lastPlayed': self.newLastPlayed(),
            'inactiveSeconds': 0,
            'emptySeconds': 0,
            # queueing a song is a read-modify-write of this state, and threading the yt-dlp
            # search (A-23) put an await in the middle of it. Lives in the state dict so the
            # three lifecycle listeners wire it up for free.
            'playLock': asyncio.Lock()
        }
        self.musicStates[str(guild.id)] = serverMusicState

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: nextcord.Guild):
        self.logger.info(f'Removing server music state for guild {guild.id} ({guild.name}).')
        # pop with a default; a guild filtered out by filterGuildsForInstance was never initialized
        self.musicStates.pop(str(guild.id), None)
        # tear down any spotify sync session too, otherwise spotify_sync keeps polling a guild we left
        self.spotifySyncSessions.pop(str(guild.id), None)

    @commands.Cog.listener()
    async def on_ready(self):
        if not self.musicStates:
            servers = utils.filterGuildsForInstance(self.client, config_queries.getAllServers())
            for serverId in servers.keys():
                serverMusicState = {
                    'isPlaying': False,
                    'isElevatorMode': False,
                    'voiceClient': None,
                    'queue': [],
                    'lastPlayed': self.newLastPlayed(),
                    'inactiveSeconds': 0,
                    'emptySeconds': 0,
                    'playLock': asyncio.Lock()
                }
                self.musicStates[serverId] = serverMusicState
        try:
            self.music_timeout.start()
        except RuntimeError:
            self.logger.info('music_timeout task is already launched and is not completed.')
        try:
            self.spotify_sync.start()
        except RuntimeError:
            self.logger.info('spotify_sync task is already launched and is not completed.')

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: nextcord.Member, before: nextcord.VoiceState, after: nextcord.VoiceState):
        # C-12: without this the cog never learns it was disconnected, moved, or left alone in a
        # channel, so recovery depended entirely on music_timeout noticing nothing is playing.
        # only the bot's own voice state is actionable here; an empty channel is handled by
        # music_timeout instead, on a grace period (see isAnyoneListening)
        serverId = str(member.guild.id)
        musicState = self.musicStates.get(serverId)
        if musicState is None or musicState['voiceClient'] is None or member.id != self.client.user.id:
            return
        if after.channel is None:
            # kicked, dropped, or disconnected by hand: stop pretending we hold a session
            self.logger.info(f'GBot Music was disconnected from voice in guild {serverId}.')
            await self.disconnectAndClearQueue(serverId)
        elif before.channel is not None and before.channel != after.channel:
            # dragged to another channel: follow it, so channelSync doesn't move us back
            self.logger.info(f'GBot Music was moved to channel {after.channel.id} in guild {serverId}.')
            musicState['lastPlayed']['channel'] = after.channel

    # Tasks
    @tasks.loop(seconds=1)
    async def music_timeout(self):
        try:
            # iterate a snapshot of the keys; the awaits below can remove entries from musicStates
            for serverId in list(self.musicStates.keys()):
                musicState = self.musicStates.get(serverId)
                if musicState is None:
                    continue
                if musicState['voiceClient'] != None:
                    if not musicState['voiceClient'].is_playing():
                        musicState['inactiveSeconds'] += 1
                        if musicState['inactiveSeconds'] >= GBotPropertiesManager.MUSIC_TIMEOUT_SECONDS:
                            self.logger.info(f'GBot Music timed out for guild {serverId} due to inactivity.')
                            await self.disconnectAndClearQueue(serverId)
                            musicState['inactiveSeconds'] = 0
                    else:
                        musicState['inactiveSeconds'] = 0
                    # elevator mode is deliberately 24/7: it keeps playing to an empty channel so
                    # that whoever joins next hears it. Everything else gives up after the same
                    # timeout — counted here rather than on the voice event so that a listener's
                    # network blip or phone-to-desktop switch doesn't end the session.
                    if musicState['voiceClient'] is None or musicState['isElevatorMode'] or self.isAnyoneListening(musicState['voiceClient']):
                        musicState['emptySeconds'] = 0
                    else:
                        musicState['emptySeconds'] += 1
                        if musicState['emptySeconds'] >= GBotPropertiesManager.MUSIC_TIMEOUT_SECONDS:
                            self.logger.info(f'GBot Music left guild {serverId} because nobody was listening.')
                            await self.disconnectAndClearQueue(serverId)
                            musicState['emptySeconds'] = 0
                else:
                    # no client means nothing can be playing, so clear the flag rather than only
                    # the counters. This is the backstop that lets a guild self-heal from any
                    # teardown that lands between resolving a song and starting it — otherwise
                    # commonPlay's isPlaying gate makes every later /play queue and never start.
                    musicState['isPlaying'] = False
                    musicState['inactiveSeconds'] = 0
                    musicState['emptySeconds'] = 0
        except Exception as e:
            self.logger.error(f'Error in Music.music_timeout(): {e}')

    @tasks.loop(seconds=1)
    async def spotify_sync(self):
        try:
            # iterate a snapshot of the keys; commonPlay below can remove entries from spotifySyncSessions
            for serverId in list(self.spotifySyncSessions.keys()):
                spotifySyncSession = self.spotifySyncSessions.get(serverId)
                if spotifySyncSession is None:
                    continue
                author = spotifySyncSession['author']
                context = spotifySyncSession['context']
                guild: nextcord.Guild = context.guild
                userId = spotifySyncSession['userId']
                lastActivity = spotifySyncSession['lastActivity']

                user = guild.get_member(userId)
                # the followed user left the guild (or the guild is gone); end the session rather
                # than dereferencing None on every tick from here on
                if user is None:
                    self.logger.info(f'GBot Music ended the spotify sync session in guild {serverId} because user {userId} is no longer available.')
                    self.spotifySyncSessions.pop(serverId, None)
                    continue
                for activity in user.activities:
                    if isinstance(activity, Spotify):
                        activityStr = f'{activity.title} by {activity.artist}'
                        if lastActivity != activityStr:
                            self.spotifySyncSessions[serverId]['lastActivity'] = activityStr
                            await self.commonPlay(context, author, [activityStr], False)
        except Exception as e:
            self.logger.error(f'Error in Music.spotify_sync(): {e}')

    # Commands
    # The two group roots. Discord never invokes a slash command that has subcommands, so the slash
    # root's body is unreachable in production — nextcord just needs a callback to hang the group on.
    @nextcord.slash_command(name = strings.MUSIC_GROUP_NAME, description = strings.MUSIC_GROUP_BRIEF, guild_ids = GBotPropertiesManager.SLASH_COMMAND_TEST_GUILDS)
    async def musicSlashGroup(self, interaction: nextcord.Interaction):
        pass

    @commands.group(name = strings.MUSIC_GROUP_NAME, aliases = strings.MUSIC_GROUP_ALIASES, brief = "- " + strings.MUSIC_GROUP_BRIEF, description = strings.MUSIC_GROUP_DESCRIPTION, invoke_without_command = True)
    async def musicGroup(self, ctx: Context):
        # a bare ".music" names no subcommand; list what lives under the group instead of doing nothing
        await ctx.send_help(ctx.command)

    @musicSlashGroup.subcommand(name = strings.MUSIC_SPOTIFY_NAME, description = strings.MUSIC_SPOTIFY_BRIEF)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isMessageSentInGuild(True)
    @predicates.isFeatureEnabledForServer('toggle_music', False, True)
    async def spotifySlash(self,
                        interaction: nextcord.Interaction,
                        user: nextcord.User = nextcord.SlashOption(
                            name = 'user',
                            required = False,
                            description = strings.MUSIC_SPOTIFY_USER_DESCRIPTION
                        )):
        await self.commonSpotify(interaction, interaction.user, user)
    
    @musicGroup.command(name = strings.MUSIC_SPOTIFY_NAME, aliases = strings.MUSIC_SPOTIFY_ALIASES, brief = "- " + strings.MUSIC_SPOTIFY_BRIEF, description = strings.MUSIC_SPOTIFY_DESCRIPTION)
    @predicates.isFeatureEnabledForServer('toggle_music', False)
    @predicates.isFeatureEnabledForServer('toggle_legacy_prefix_commands', False)
    @predicates.isMessageSentInGuild()
    @predicates.isGuildOrUserSubscribed()
    async def spotify(self, ctx: Context, user: nextcord.User = None):
        await self.commonSpotify(ctx, ctx.author, user)

    async def commonSpotify(self, context, author, user):
        serverId = str(context.guild.id)
        authorMention = author.mention
        user = user or author
        userId = user.id
        userMention = user.mention
        if not await utils.isUserInThisGuildAndNotABot(user, context.guild):
            await context.send(f'Sorry {authorMention}, please specify a user in this guild.')
            return
        if serverId in self.spotifySyncSessions and userId == self.spotifySyncSessions[serverId]['userId']:
            self.spotifySyncSessions.pop(serverId)
            self.logger.info(f'GBot Music Spotify sync ended in guild {serverId} for user {userId}.')
            await context.send(f'Spotify activity sync deactivated for {userMention}.')
            return
        if hasattr(user, 'activities'):
            for activity in user.activities:
                if isinstance(activity, Spotify):
                    activityStr = f'{activity.title} by {activity.artist}'
                    self.spotifySyncSessions[serverId] = {
                        'userId': userId,
                        'userMention': userMention,
                        'lastActivity': activityStr,
                        'context': context,
                        'author': author
                    }
                    await context.send(f'Spotify activity sync activated for {userMention}.')
                    self.logger.info(f'GBot Music Spotify sync started in guild {serverId} for user {userId}.')
                    await self.commonPlay(context, author, [activityStr], False)
                    return
        await context.send(f'Sorry {authorMention}, there is currently no Spotify activity to sync with.')

    @musicSlashGroup.subcommand(name = strings.MUSIC_PLAY_NAME, description = strings.MUSIC_PLAY_BRIEF)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isMessageSentInGuild(True)
    @predicates.isFeatureEnabledForServer('toggle_music', False, True)
    async def playSlash(self,
                        interaction: nextcord.Interaction,
                        input = nextcord.SlashOption(
                            name = 'input',
                            description = strings.MUSIC_PLAY_INPUT_DESCRIPTION
                        )):
        await self.commonPlay(interaction, interaction.user, utils.strParamToArgs(input))

    @musicGroup.command(name = strings.MUSIC_PLAY_NAME, aliases = strings.MUSIC_PLAY_ALIASES, brief = "- " + strings.MUSIC_PLAY_BRIEF, description = strings.MUSIC_PLAY_DESCRIPTION)
    @predicates.isFeatureEnabledForServer('toggle_music', False)
    @predicates.isFeatureEnabledForServer('toggle_legacy_prefix_commands', False)
    @predicates.isMessageSentInGuild()
    @predicates.isGuildOrUserSubscribed()
    async def play(self, ctx: Context, *args):
        await self.commonPlay(ctx, ctx.author, args)
    
    async def commonPlay(self, context, author, args, noReplyYet = True):
        if author.voice is None:
            await context.send('Please connect to a voice channel.')
            return
        if isinstance(context, nextcord.Interaction) and noReplyYet:
            await context.response.defer()
        searchString = ' '.join(list(args))
        voiceChannel = author.voice.channel
        serverId = str(context.guild.id)

        songInfo = await self.searchYouTube(searchString)
        if songInfo is None:
            # "use the share button to get a URL" is advice for a search that found nothing; it is
            # nonsense when a link was already pasted and *that* is what failed. Seen in QA: a
            # private playlist (403) and livestreams whose manifest host the network blocks both
            # landed on the search-flavoured message.
            if self.isUrl(searchString):
                await context.send('Could not load that link. It may be private, age-restricted, region-locked, or unavailable.')
            else:
                await context.send('Could not get the video sound. Try using share button to get video URL.')
            return
        # Every playable-input policy lives here rather than in searchYouTube, next to the length
        # limit that was already the only one of its kind.
        isPlaylist = songInfo.get('_type') in ('playlist', 'multi_video')
        truncated = False
        skipped = 0
        if isPlaylist:
            # only reachable because C-11 fetches a pasted URL instead of searching it — a search
            # result is always the single video dict taken from ['entries'][0]. noplaylist strips
            # the list from a watch?v=...&list=... link, so only a bare /playlist?list=... (or a
            # channel tab) arrives here.
            songs, truncated, skipped = self.songsFromPlaylist(songInfo)
            if not songs:
                note = f' Only the first {GBotPropertiesManager.MUSIC_MAX_PLAYLIST_SONGS} entries were checked.' if truncated else ''
                await context.send(f'Nothing in that playlist could be played \u2014 every entry was unavailable or longer than {GBotPropertiesManager.MUSIC_MAX_DURATION_MINUTES} minutes.{note}')
                return
        else:
            song = self.songFromInfo(songInfo)
            if song is None:
                await context.send('Could not determine the length of that sound.')
                return
            # livestreams have no duration to limit — the cap is meaningless for something with
            # no end, and /skip is how you leave one
            if not song['isLive'] and (song['duration'] / 60) >= GBotPropertiesManager.MUSIC_MAX_DURATION_MINUTES:
                await context.send(f'Please play sounds less than {GBotPropertiesManager.MUSIC_MAX_DURATION_MINUTES} minutes.')
                return
            songs = [song]

        # searching off the event loop (A-23) put an await between reading isPlaying and
        # acting on it, so two /play commands in one guild could both see "not playing",
        # both start playback, and the second raise "Already playing audio"
        async with self.musicStates[serverId]['playLock']:
            musicState = self.musicStates[serverId]
            if musicState['isPlaying'] and musicState['isElevatorMode']:
                await context.send("Please disable elevator mode to add songs to the queue.")
                return
            wasIdle = not musicState['isPlaying']
            for song in songs:
                musicState['queue'].append([song, voiceChannel])

            if isPlaylist:
                # Three separate facts, and they have to stay separate. "Added 42 songs... Playlist
                # truncated to the first 50" read as a contradiction, because 42 is how many
                # survived filtering while 50 is how many were looked at — a podcast playlist hits
                # both at once (episodes over the length cap, and 700 entries behind the cap).
                # Keyed off isPlaylist rather than len(songs) > 1, so a playlist yielding exactly
                # one playable song still reports what happened instead of silently rendering as an
                # ordinary single-song play.
                parts = [f'Added {len(songs)} song{"" if len(songs) == 1 else "s"} to the queue.']
                if skipped:
                    parts.append(f'Skipped {skipped} that could not be played or ran over {GBotPropertiesManager.MUSIC_MAX_DURATION_MINUTES} minutes.')
                if truncated:
                    parts.append(f'Only the first {GBotPropertiesManager.MUSIC_MAX_PLAYLIST_SONGS} entries of the playlist were checked.')
                message = ' '.join(parts)
            elif wasIdle:
                # bare link: Discord's client renders its own playable card for the song now
                # playing. There is no audio-player message component, so that embed is the
                # closest thing to one, and it costs no embed design of our own.
                message = f'Playing sound:\n{self.describeSongText(songs[0])}'
            else:
                # suppressed link: queueing five songs would otherwise post five full-size cards,
                # and a queued song is not the one anyone wants to press play on
                message = f'Sound added to the queue ({len(musicState["queue"])}):\n{self.describeSongText(songs[0], suppressEmbed = True)}'
            await context.send(message)

            if wasIdle:
                await self.channelSync(serverId)
                await self.playMusic(serverId)

    @musicSlashGroup.subcommand(name = strings.MUSIC_QUEUE_NAME, description = strings.MUSIC_QUEUE_BRIEF)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isMessageSentInGuild(True)
    @predicates.isFeatureEnabledForServer('toggle_music', False, True)
    async def queueSlash(self, interaction: nextcord.Interaction):
        await self.commonQueue(interaction)

    @musicGroup.command(name = strings.MUSIC_QUEUE_NAME, aliases = strings.MUSIC_QUEUE_ALIASES, brief = "- " + strings.MUSIC_QUEUE_BRIEF, description = strings.MUSIC_QUEUE_DESCRIPTION)
    @predicates.isFeatureEnabledForServer('toggle_music', False)
    @predicates.isFeatureEnabledForServer('toggle_legacy_prefix_commands', False)
    @predicates.isMessageSentInGuild()
    @predicates.isGuildOrUserSubscribed()
    async def queue(self, ctx: Context):
        await self.commonQueue(ctx)

    async def commonQueue(self, context):
        serverId = str(context.guild.id)

        fields = []
        if self.musicStates[serverId]['isPlaying'] and self.musicStates[serverId]['lastPlayed']['song'] is not None:
            fields.append({
                'name': 'Now Playing',
                'value': self.describeSongEmbed(self.musicStates[serverId]['lastPlayed']['song'])
            })
        else:
            fields.append({
                'name': 'Now Playing',
                'value': '`Idle`'
            })

        if self.musicStates[serverId]['isElevatorMode']:
            fields.append({
                'name': 'Elevator Mode',
                'value': '`Enabled`'
            })
        else:
            fields.append({
                'name': 'Elevator Mode',
                'value': '`Disabled`'
            })

        if serverId in self.spotifySyncSessions:
            fields.append({
                'name': 'Spotify Sync',
                'value': self.spotifySyncSessions[serverId]['userMention']
            })
        else:
            fields.append({
                'name': 'Spotify Sync',
                'value': '`Disabled`'
            })

        data = []
        data.append('**Queue**')
        isQueuedSongs = False
        for i in range(0, len(self.musicStates[serverId]['queue'])):
            data.append(f'`{i + 1}.)` ' + self.describeSongEmbed(self.musicStates[serverId]['queue'][i][0]))
            isQueuedSongs = True
        if not isQueuedSongs:
            data.append('`Empty`')
        
        pages = pagination.CustomButtonMenuPages(source = pagination.DescriptionPageSource(data, "GBot Music", nextcord.Color.red(), None, 11, fields))
        await pagination.startPages(context, pages)

    @musicSlashGroup.subcommand(name = strings.MUSIC_ELEVATOR_NAME, description = strings.MUSIC_ELEVATOR_BRIEF)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isMessageSentInGuild(True)
    @predicates.isFeatureEnabledForServer('toggle_music', False, True)
    async def elevatorSlash(self, interaction: nextcord.Interaction):
        await self.commonElevator(interaction)

    @musicGroup.command(name = strings.MUSIC_ELEVATOR_NAME, aliases = strings.MUSIC_ELEVATOR_ALIASES, brief = "- " + strings.MUSIC_ELEVATOR_BRIEF, description = strings.MUSIC_ELEVATOR_DESCRIPTION)
    @predicates.isFeatureEnabledForServer('toggle_music', False)
    @predicates.isFeatureEnabledForServer('toggle_legacy_prefix_commands', False)
    @predicates.isMessageSentInGuild()
    @predicates.isGuildOrUserSubscribed()
    async def elevator(self, ctx: Context):
        await self.commonElevator(ctx)

    async def commonElevator(self, context):
        serverId = str(context.guild.id)
        currentElevatorMode = self.musicStates[serverId]['isElevatorMode']
        newElevatorMode = not currentElevatorMode
        lastPlayedSong = self.musicStates[serverId]['lastPlayed']['song']
        if newElevatorMode and lastPlayedSong is not None and lastPlayedSong['isLive']:
            # repeating something with no end is meaningless — a livestream already never stops,
            # and the repeat would only ever fire if the stream itself died
            await context.send('Elevator mode cannot repeat a livestream.')
            return
        self.musicStates[serverId]['isElevatorMode'] = newElevatorMode
        if newElevatorMode:
            # if syncing with Spotify, stop to enable elevator mode
            if serverId in self.spotifySyncSessions:
                userId = self.spotifySyncSessions[serverId]['userId']
                userMention = self.spotifySyncSessions[serverId]['userMention']
                self.logger.info(f'GBot Music Spotify sync ended in guild {serverId} for user {userId}.')
                await context.send(f'Spotify activity sync deactivated for {userMention}.')
                self.spotifySyncSessions.pop(serverId)
            elevatorStr = 'Elevator mode enabled.'
        else:
            elevatorStr = 'Elevator mode disabled.'
        await context.send(elevatorStr)

    @musicSlashGroup.subcommand(name = strings.MUSIC_SKIP_NAME, description = strings.MUSIC_SKIP_BRIEF)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isMessageSentInGuild(True)
    @predicates.isFeatureEnabledForServer('toggle_music', False, True)
    async def skipSlash(self, interaction: nextcord.Interaction):
        await self.commonSkip(interaction, interaction.user)

    @musicGroup.command(name = strings.MUSIC_SKIP_NAME, aliases = strings.MUSIC_SKIP_ALIASES, brief = "- " + strings.MUSIC_SKIP_BRIEF, description = strings.MUSIC_SKIP_DESCRIPTION)
    @predicates.isFeatureEnabledForServer('toggle_music', False)
    @predicates.isFeatureEnabledForServer('toggle_legacy_prefix_commands', False)
    @predicates.isMessageSentInGuild()
    @predicates.isGuildOrUserSubscribed()
    async def skip(self, ctx: Context):
        await self.commonSkip(ctx, ctx.author)

    async def commonSkip(self, context, author):
        serverId = str(context.guild.id)
        if self.musicStates[serverId]['voiceClient'] != None:
            if self.musicStates[serverId]['isElevatorMode'] and not self.musicStates[serverId]['isPlaying']:
                # playMusic awaits the codec probe (C-4), so this restart has to be serialized with
                # commonPlay's and onSongFinished's the same way they are with each other
                async with self.musicStates[serverId]['playLock']:
                    await self.channelSync(serverId)
                    await self.playMusic(serverId)
            else:
                self.musicStates[serverId]['voiceClient'].stop()
            await context.send(f'Skipped.')
        else:
            await context.send(f'Sorry {author.mention}, there is currently nothing playing.')

    @musicSlashGroup.subcommand(name = strings.MUSIC_STOP_NAME, description = strings.MUSIC_STOP_BRIEF)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isMessageSentInGuild(True)
    @predicates.isFeatureEnabledForServer('toggle_music', False, True)
    async def stopSlash(self, interaction: nextcord.Interaction):
        await self.commonStop(interaction, interaction.user)

    @musicGroup.command(name = strings.MUSIC_STOP_NAME, aliases = strings.MUSIC_STOP_ALIASES, brief = "- " + strings.MUSIC_STOP_BRIEF, description = strings.MUSIC_STOP_DESCRIPTION)
    @predicates.isFeatureEnabledForServer('toggle_music', False)
    @predicates.isFeatureEnabledForServer('toggle_legacy_prefix_commands', False)
    @predicates.isMessageSentInGuild()
    @predicates.isGuildOrUserSubscribed()
    async def stop(self, ctx: Context):
        await self.commonStop(ctx, ctx.author)

    async def commonStop(self, context, author):
        serverId = str(context.guild.id)
        if self.musicStates[serverId]['voiceClient'] != None:
            await self.disconnectAndClearQueue(serverId)
            await context.send(f'Stopped.')
        else:
            await context.send(f'Sorry {author.mention}, there is currently nothing playing.')

    @musicSlashGroup.subcommand(name = strings.MUSIC_PAUSE_NAME, description = strings.MUSIC_PAUSE_BRIEF)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isMessageSentInGuild(True)
    @predicates.isFeatureEnabledForServer('toggle_music', False, True)
    async def pauseSlash(self, interaction: nextcord.Interaction):
        await self.commonPause(interaction, interaction.user)

    @musicGroup.command(name = strings.MUSIC_PAUSE_NAME, aliases = strings.MUSIC_PAUSE_ALIASES, brief = "- " + strings.MUSIC_PAUSE_BRIEF, description = strings.MUSIC_PAUSE_DESCRIPTION)
    @predicates.isFeatureEnabledForServer('toggle_music', False)
    @predicates.isFeatureEnabledForServer('toggle_legacy_prefix_commands', False)
    @predicates.isMessageSentInGuild()
    @predicates.isGuildOrUserSubscribed()
    async def pause(self, ctx: Context):
        await self.commonPause(ctx, ctx.author)

    async def commonPause(self, context, author):
        serverId = str(context.guild.id)
        if self.musicStates[serverId]['voiceClient'] != None and self.musicStates[serverId]['voiceClient'].is_playing():
            self.musicStates[serverId]['voiceClient'].pause()
            await context.send(f'Paused.')
        else:
            await context.send(f'Sorry {author.mention}, there is currently nothing playing.')

    @musicSlashGroup.subcommand(name = strings.MUSIC_RESUME_NAME, description = strings.MUSIC_RESUME_BRIEF)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isMessageSentInGuild(True)
    @predicates.isFeatureEnabledForServer('toggle_music', False, True)
    async def resumeSlash(self, interaction: nextcord.Interaction):
        await self.commonResume(interaction, interaction.user)

    @musicGroup.command(name = strings.MUSIC_RESUME_NAME, aliases = strings.MUSIC_RESUME_ALIASES, brief = "- " + strings.MUSIC_RESUME_BRIEF, description = strings.MUSIC_RESUME_DESCRIPTION)
    @predicates.isFeatureEnabledForServer('toggle_music', False)
    @predicates.isFeatureEnabledForServer('toggle_legacy_prefix_commands', False)
    @predicates.isMessageSentInGuild()
    @predicates.isGuildOrUserSubscribed()
    async def resume(self, ctx: Context):
        await self.commonResume(ctx, ctx.author)

    async def commonResume(self, context, author):
        serverId = str(context.guild.id)
        if self.musicStates[serverId]['voiceClient'] != None and self.musicStates[serverId]['voiceClient'].is_paused():
            self.musicStates[serverId]['voiceClient'].resume()
            await context.send(f'Resumed.')
        else:
            await context.send(f'Sorry {author.mention}, there is currently nothing paused.')

    async def searchYouTube(self, searchString):
        # A-23: extract_info is a blocking network + parse call, so on the event loop it stalled
        # the whole bot — gateway and API included — for the duration of every /play.
        return await asyncio.to_thread(self.extractSongInfo, searchString)

    def extractSongInfo(self, searchString):
        # runs on a worker thread
        try:
            if self.isUrl(searchString):
                # C-11: every input used to be prefixed ytsearch:, so a pasted link was used as
                # a search *query* — usually lucky, occasionally the wrong video, and never a
                # canonical webpage_url worth showing anyone. A fetched result is the video
                # dict itself, not a search wrapper carrying entries.
                #
                # extract_flat lists a playlist's entries without resolving each one, which is what
                # keeps a 200-song paste from becoming 200 network round trips. It does nothing to
                # a single video URL — there is no playlist to flatten — and is deliberately NOT
                # set on the search path below, where the ytsearch: result is itself a playlist and
                # flattening it would strip the very duration that path has to check.
                # playlistend is one past the cap so "there were more" is knowable without ever
                # listing thousands of entries.
                options = {
                    **self.YT_DLP_OPTIONS,
                    'extract_flat': 'in_playlist',
                    'playlistend': GBotPropertiesManager.MUSIC_MAX_PLAYLIST_SONGS + 1
                }
                with YoutubeDL(options) as ydl:
                    return ydl.extract_info(searchString, download = False)
            with YoutubeDL(self.YT_DLP_OPTIONS) as ydl:
                return ydl.extract_info(f'ytsearch:{searchString}', download = False)['entries'][0]
        except Exception:
            return None

    def songFromInfo(self, info):
        # One queue entry. Deliberately carries NO stream URL: C-14 — commonPlay used to resolve
        # info['url'] at queue time and playMusic replayed it whenever the song reached the head,
        # which is the same expiring, IP-bound CDN link C-6 was about, just with the delay set by
        # how long the queue is. Harmless at three songs; a 50-song playlist is hours. The URL is
        # now resolved at play time from searchString, exactly as elevator mode already does.
        isLive = bool(info.get('is_live'))
        duration = info.get('duration')
        if not isLive and duration is None:
            # yt-dlp omits duration for premieres and some post-live states; without a length there
            # is nothing to check the limit against
            return None
        # a flat playlist entry's 'url' is the video's watch URL, which is what we want to re-fetch;
        # a fully extracted video carries webpage_url and its 'url' is the CDN stream (never this)
        webpageUrl = info.get('webpage_url') or (info.get('url') if info.get('_type') == 'url' else '') or ''
        return {
            'title': info.get('title') or 'Unknown',
            'webpageUrl': webpageUrl,
            'duration': duration,
            'isLive': isLive,
            'searchString': webpageUrl or info.get('title') or ''
        }

    def songsFromPlaylist(self, playlistInfo):
        # -> (songs, truncated). Entries are flat, so this costs no per-video requests.
        rawEntries = playlistInfo.get('entries') or []
        limit = GBotPropertiesManager.MUSIC_MAX_PLAYLIST_SONGS
        # judged on the RAW count, before dropping falsy entries: extractSongInfo fetched limit + 1,
        # so limit + 1 raw entries is exactly what "there were more" means. Filtering first would
        # let a single None — yt-dlp's placeholder for a deleted or unavailable video — inside that
        # window pull the count back down to limit and silently swallow the truncation notice.
        truncated = len(rawEntries) > limit
        examined = rawEntries[:limit]
        songs = []
        for entry in examined:
            if not entry:
                continue
            song = self.songFromInfo(entry)
            # filtered on webpageUrl, not searchString: songFromInfo falls back to re-searching by
            # title, which is right for a single result we just found by searching anyway, but
            # wrong here — a playlist entry we cannot identify by URL would silently queue whatever
            # that title happens to match, which is the C-11 fuzziness this workstream removed.
            if song is None or not song['webpageUrl']:
                continue
            # a flat entry usually carries a duration; skip anything already over the limit rather
            # than discovering it at play time, where there is no one to tell
            if not song['isLive'] and (song['duration'] / 60) >= GBotPropertiesManager.MUSIC_MAX_DURATION_MINUTES:
                continue
            songs.append(song)
        # how many of the entries we actually looked at were rejected — a different fact from
        # truncation, which is about entries never fetched at all. A podcast playlist reports both:
        # episodes over the length cap are skipped, and the playlist is longer than the cap.
        skipped = len(examined) - len(songs)
        return songs, truncated, skipped

    def isUrl(self, searchString):
        # an http(s) scheme is the whole test: a bare domain cannot be told apart from a song title
        # ("R.E.M. - Losing My Religion"). No domain allowlist either — yt-dlp already fails cleanly
        # on anything it does not support, and a malformed URL raises out of urlparse; both land on
        # extractSongInfo's existing None path, which the user sees as the search-failed message.
        return urlparse(searchString).scheme in ('http', 'https')

    def formatDuration(self, seconds):
        hours, remainder = divmod(int(seconds), 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours > 0:
            return f'{hours}:{minutes:02}:{seconds:02}'
        return f'{minutes}:{seconds:02}'

    def escapeLinkText(self, text):
        # a title carrying brackets ("Song [Official Video]") would terminate a masked link early
        return text.replace('[', '\\[').replace(']', '\\]')

    def describeLength(self, song):
        # a livestream has no length to state, so it is labelled instead of measured
        if song['isLive']:
            return '🔴 LIVE'
        if song['duration'] is None:
            return None
        return f"({self.formatDuration(song['duration'])})"

    def describeSongText(self, song, suppressEmbed = False):
        # plain-text sends: title + length, then the video link on its own line. Angle brackets ask
        # Discord to skip its link preview; without them it renders the playable card.
        line = song['title']
        length = self.describeLength(song)
        if length is not None:
            line += f' {length}'
        if song['webpageUrl']:
            line += f"\n<{song['webpageUrl']}>" if suppressEmbed else f"\n{song['webpageUrl']}"
        return line

    def describeSongEmbed(self, song):
        # /queue is already an embed, and an embed never expands a bare URL — so a masked link is
        # both tidier and free of the second-audio-source trap the playing card carries.
        text = f"[{self.escapeLinkText(song['title'])}]({song['webpageUrl']})" if song['webpageUrl'] else f"`{song['title']}`"
        length = self.describeLength(song)
        if length is not None:
            text += f' `{length}`'
        return text

    async def channelSync(self, serverId):
        musicState = self.musicStates[serverId]
        queue = musicState['queue']
        if len(queue) == 0 and not musicState['isElevatorMode']:
            return

        # the channel to be in is the one whose audio playMusic is about to play: the elevator's
        # own channel while it is repeating, otherwise the channel the queue head was asked from.
        # A-18: both branches used to index queue[0] unconditionally, so elevator mode with an
        # empty queue — the state a dropped voice connection leaves behind — raised IndexError.
        if musicState['isElevatorMode'] and musicState['lastPlayed']['song'] is not None:
            channel = musicState['lastPlayed']['channel']
        elif len(queue) > 0:
            channel = queue[0][1]
        else:
            self.logger.warning(f'GBot Music has no channel to sync to in guild {serverId}.')
            return

        voiceClient = musicState['voiceClient']
        if voiceClient is not None and not voiceClient.is_connected():
            # a failed handshake leaves a client behind that never connected (C-1); discard it or
            # channel.connect() below is refused because the guild still has a voice client
            self.logger.info(f'GBot Music discarding a disconnected voice client in guild {serverId}.')
            try:
                await voiceClient.disconnect(force = True)
            except Exception as e:
                self.logger.error(f'GBot Music could not discard the disconnected voice client in guild {serverId}: {e}')
            voiceClient = None
            musicState['voiceClient'] = None

        if voiceClient is None:
            self.logger.info(f'GBot Music connecting to channel {channel.id} in guild {serverId}.')
            musicState['voiceClient'] = await channel.connect()
        else:
            self.logger.info(f'GBot Music moving to channel {channel.id} in guild {serverId}.')
            await voiceClient.move_to(channel)

    async def playMusic(self, serverId):
        # callers hold musicState['playLock']: resolving the source now awaits a codec probe (C-4),
        # which puts a suspension point between the is_playing() guard below and voiceClient.play().
        # Acquiring it in here instead would deadlock — commonPlay already holds it when it calls.
        musicState = self.musicStates.get(serverId)
        if musicState is None:
            # the guild was removed while a song was playing; onSongFinished still fires
            return
        voiceClient = musicState['voiceClient']
        if voiceClient is None or not voiceClient.is_connected():
            # the connection is gone (a /stop, an idle timeout, a kick, or a failed handshake):
            # go idle and keep the queue rather than consuming it into a dead client
            self.logger.info(f'GBot Music is not connected to voice in guild {serverId}; nothing will be played.')
            musicState['isPlaying'] = False
            return
        if voiceClient.is_playing():
            # another caller already started a song (two /skips racing in elevator mode, say);
            # the running song's after callback picks the queue up from here
            return

        # A-18 again, one function over: the old outer "queue or elevator mode" test let the
        # queue branch run with an empty queue whenever elevator mode was on but nothing had
        # played yet, indexing queue[0]. Elevator replay, then the queue, then idle.
        if musicState['isElevatorMode'] and musicState['lastPlayed']['song'] is not None:
            song = musicState['lastPlayed']['song']
            channel = musicState['lastPlayed']['channel']
            url = await self.resolveStreamUrl(song)
            if url is None:
                # go idle rather than retry: music_timeout disconnects after MUSIC_TIMEOUT_SECONDS,
                # and commonSkip's elevator branch restarts playback on demand
                self.logger.error(f"GBot Music could not resolve the elevator song '{song['searchString']}' in guild {serverId}; going idle.")
                musicState['isPlaying'] = False
                return
        else:
            # Walk the queue until something resolves. One unplayable entry — deleted, private,
            # region-locked, or a livestream whose manifest host is unreachable — must not strand
            # everything queued behind it. Before C-PR8 the queue path never resolved here at all,
            # so this failure could not happen; queueing a 50-song playlist makes it likely.
            url = None
            while musicState['queue']:
                song, channel = musicState['queue'].pop(0)
                url = await self.resolveStreamUrl(song)
                if url is not None:
                    break
                self.logger.error(f"GBot Music could not resolve '{song['searchString']}' in guild {serverId}; skipping to the next song.")
            if url is None:
                musicState['isPlaying'] = False
                return

        source = await self.buildAudioSource(url, **self.FFMPEG_OPTIONS)

        # Re-read the client instead of trusting the reference captured before the resolve and
        # probe awaits above. disconnectAndClearQueue — reached from /stop, the idle timeout, or a
        # kick — takes no playLock, so it can null the client out from under us while we walk the
        # queue, which a playlist full of dead entries can stretch over several seconds. Without
        # this the guild is left isPlaying = True holding a dead client: play() raises
        # ClientException, music_timeout's no-client branch never clears isPlaying, and every later
        # /play just queues forever without starting.
        voiceClient = musicState['voiceClient']
        if voiceClient is None or not voiceClient.is_connected():
            self.logger.info(f'GBot Music lost its voice connection while resolving in guild {serverId}; going idle.')
            musicState['isPlaying'] = False
            return

        # set only once there is really something to play, and nothing left to await before it
        musicState['isPlaying'] = True
        self.logger.info(f"GBot Music playing next sound '{song['title']}' in channel {channel} in guild {serverId}.")

        # A-20: after runs on ffmpeg's audio thread. Returning a coroutine hands it back to the
        # event loop (nextcord submits it with run_coroutine_threadsafe), so musicStates is only
        # ever mutated there.
        voiceClient.play(source, after = lambda error: self.onSongFinished(serverId, error))

        # replaced wholesale rather than field by field, so the shape can't drift from newLastPlayed
        musicState['lastPlayed'] = {'song': song, 'channel': channel}

    async def resolveStreamUrl(self, song):
        # C-6 and C-14: the stream URL is a time-limited, IP-bound CDN link, so it is resolved at
        # the moment the song starts and never stored anywhere. That covers both the elevator
        # repeat (C-6) and a song that waited in a long queue (C-14); replaying a stored URL 403s
        # once it expires, which ffmpeg's reconnect flags cannot recover from and A-20's handler
        # can only log. A flat playlist entry has never carried a URL at all, so this is also what
        # makes queueing a playlist cheap.
        songInfo = await self.searchYouTube(song['searchString'])
        return songInfo.get('url') if songInfo is not None else None

    async def onSongFinished(self, serverId, error):
        if error is not None:
            # A-20: the callback's error argument was discarded, so an ffmpeg failure was
            # indistinguishable from a song ending and silently advanced the queue
            self.logger.error(f'GBot Music playback error in guild {serverId}: {error}')
        musicState = self.musicStates.get(serverId)
        if musicState is None:
            # the guild was removed while a song was playing; there is no lock left to take
            return
        async with musicState['playLock']:
            await self.playMusic(serverId)

    async def buildAudioSource(self, source, **ffmpegOptions):
        # C-4: FFmpegPCMAudio had ffmpeg decode to 48 kHz stereo PCM and nextcord Opus-encode every
        # 20 ms frame in-process. YouTube's bestaudio is already Opus (itag 251), so probing the
        # codec lets ffmpeg pass those packets straight through (-c:a copy); anything else is
        # encoded by ffmpeg itself. Either way FFmpegOpusAudio reports is_opus(), so nextcord skips
        # its in-process encoder entirely.
        #
        # Only the codec is taken from the probe, which is why this is not from_probe: nextcord
        # computes the bitrate as max(round(kbps), 512), so its native probe never reports below
        # 512 kbps, and from_probe feeds that straight to -b:a. It also forwards bitrate = None
        # when a probe fails, which makes ffmpeg reject "-b:a Nonek" and kills playback. The
        # constructor's own 128k default is the right value for the encoded path, and -b:a is
        # ignored on a copy. probe() runs the subprocess in an executor and swallows its own
        # failures, returning (None, None), so there is nothing to catch here.
        codec, _ = await nextcord.FFmpegOpusAudio.probe(source)
        return nextcord.FFmpegOpusAudio(source, codec = codec, **ffmpegOptions)

    def isAnyoneListening(self, voiceClient):
        return any(not member.bot for member in voiceClient.channel.members)

    async def disconnectAndClearQueue(self, serverId):
        if self.musicStates[serverId]['voiceClient'] != None:
            self.logger.info(f'GBot Music disconnecting and clearing queue for guild {serverId}.')
            await self.musicStates[serverId]['voiceClient'].disconnect()
            self.musicStates[serverId]['voiceClient'] = None
            self.musicStates[serverId]['queue'] = []
            self.musicStates[serverId]['isPlaying'] = False
            self.musicStates[serverId]['isElevatorMode'] = False
            self.musicStates[serverId]['lastPlayed'] = self.newLastPlayed()
        if serverId in self.spotifySyncSessions:
            self.spotifySyncSessions.pop(serverId)

    class YTDLPLogger:
        def __init__(self, outer):
            self.logger = outer.logger
        def debug(self, msg):
            # For compatibility with youtube-dl, both debug and info are passed into debug
            # You can distinguish them by the prefix '[debug] '
            if msg.startswith('[debug] '):
                self.logger.debug(msg)
            else:
                self.info(msg)
        def info(self, msg):
            self.logger.info(msg)
        def warning(self, msg):
            self.logger.warning(msg)
        def error(self, msg):
            self.logger.error(msg)

def setup(client: commands.Bot):
    client.add_cog(Music(client))