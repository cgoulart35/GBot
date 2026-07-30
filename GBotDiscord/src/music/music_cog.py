#region IMPORTS
import asyncio
import pathlib
import os
import logging
import nextcord
from nextcord import Spotify
from nextcord.ext import commands, tasks
from nextcord.ext.commands.context import Context
from yt_dlp import YoutubeDL, utils as ytUtils

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
        self.parentDir = str(pathlib.Path(__file__).parent.parent.absolute()).replace("\\",'/')
        self.DOWNLOADED_VIDEOS_PATH = f'{self.parentDir}/sounds'
        if not os.path.exists(self.DOWNLOADED_VIDEOS_PATH):
            os.makedirs(self.DOWNLOADED_VIDEOS_PATH)

        self.FFMPEG_OPTIONS = {
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            'options': '-vn'}
        self.YT_DLP_OPTIONS = {
            'format': 'bestaudio/best',
            'noplaylist': True,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'outtmpl': f'{self.DOWNLOADED_VIDEOS_PATH}/%(title)s',
            'logger': self.ytdlLogger
        }

        self.spotifySyncSessions = {}
        self.cachedYouTubeFiles = {}
        self.musicStates = {}
        # in-flight elevator cache downloads; a task with no strong reference can be
        # garbage collected mid-download
        self.cacheDownloadTasks = set()

    # Events
    @commands.Cog.listener()
    async def on_guild_join(self, guild: nextcord.Guild):
        self.logger.info(f'Adding server music state for guild {guild.id} ({guild.name}).')
        serverMusicState = {
            'isPlaying': False,
            'isElevatorMode': False,
            'voiceClient': None,
            'queue': [],
            'lastPlayed': {'url': '', 'name': '', 'channel': None, 'searchString': ''},
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
                    'lastPlayed': {'url': '', 'name': '', 'channel': None, 'searchString': ''},
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
        try:
            self.cached_youtube_files.start()
        except RuntimeError:
            self.logger.info('cached_youtube_files task is already launched and is not completed.')

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

    @tasks.loop(minutes=1)
    async def cached_youtube_files(self):
        try:
            if any(self.cachedYouTubeFiles):
                self.logger.info(f'GBot Music - CACHED YOUTUBE FILES: {self.cachedYouTubeFiles}')
            cachedYouTubeFilesCopy = self.cachedYouTubeFiles.copy()
            for fileKey, fileInfo in cachedYouTubeFilesCopy.items():
                filepath = fileInfo['filepath']
                cachedFileExists = os.path.exists(filepath)
                if cachedFileExists:
                    if fileInfo['inactiveMinutes'] >= GBotPropertiesManager.MUSIC_CACHE_DELETION_TIMEOUT_MINUTES:
                        self.logger.info(f'GBot Music removing sound file from music cache: {filepath}')
                        os.remove(filepath)
                        self.cachedYouTubeFiles.pop(fileKey)
                    else:
                        self.cachedYouTubeFiles[fileKey]['inactiveMinutes'] += 1
                        self.cachedYouTubeFiles[fileKey]['lifetimeMinutes'] += 1
                elif fileInfo['inactiveMinutes'] >= GBotPropertiesManager.MUSIC_CACHE_DELETION_TIMEOUT_MINUTES:
                    self.logger.info(f'GBot Music removing sound file that was not found from music cache: {filepath}')
                    self.cachedYouTubeFiles.pop(fileKey)
        except Exception as e:
            self.logger.error(f'Error in Music.cached_youtube_files(): {e}')

    # Commands
    @nextcord.slash_command(name = strings.SPOTIFY_NAME, description = strings.SPOTIFY_BRIEF, guild_ids = GBotPropertiesManager.SLASH_COMMAND_TEST_GUILDS)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isMessageSentInGuild(True)
    @predicates.isFeatureEnabledForServer('toggle_music', False, True)
    async def spotifySlash(self,
                        interaction: nextcord.Interaction,
                        user: nextcord.User = nextcord.SlashOption(
                            name = 'user',
                            required = False,
                            description = strings.SPOTIFY_USER_DESCRIPTION
                        )):
        await self.commonSpotify(interaction, interaction.user, user)
    
    @commands.command(aliases = strings.SPOTIFY_ALIASES, brief = "- " + strings.SPOTIFY_BRIEF, description = strings.SPOTIFY_DESCRIPTION)
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

    @nextcord.slash_command(name = strings.PLAY_NAME, description = strings.PLAY_BRIEF, guild_ids = GBotPropertiesManager.SLASH_COMMAND_TEST_GUILDS)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isMessageSentInGuild(True)
    @predicates.isFeatureEnabledForServer('toggle_music', False, True)
    async def playSlash(self,
                        interaction: nextcord.Interaction,
                        input = nextcord.SlashOption(
                            name = 'input',
                            description = strings.PLAY_INPUT_DESCRIPTION
                        )):
        await self.commonPlay(interaction, interaction.user, utils.strParamToArgs(input))

    @commands.command(aliases = strings.PLAY_ALIASES, brief = "- " + strings.PLAY_BRIEF, description = strings.PLAY_DESCRIPTION)
    @predicates.isFeatureEnabledForServer('toggle_music', False)
    @predicates.isFeatureEnabledForServer('toggle_legacy_prefix_commands', False)
    @predicates.isMessageSentInGuild()
    @predicates.isGuildOrUserSubscribed()
    async def play(self, ctx: Context, *args):
        await self.commonPlay(ctx, ctx.author, args)
    
    async def commonPlay(self, context, author, args, noReplyYet = True):
        if author.voice is None:
            await context.send('Please connect to a voice channel.')
        else:
            if isinstance(context, nextcord.Interaction) and noReplyYet:
                await context.response.defer()
            searchString = ' '.join(list(args))
            voiceChannel = author.voice.channel
            serverId = str(context.guild.id)
            songInfo = await self.searchYouTubeAndCacheDownload(searchString, self.musicStates[serverId]['isElevatorMode'])
            if songInfo != None:
                song = {'source': songInfo['url'], 'title': songInfo['title']}
                title = song['title']
                if (songInfo['duration'] / 60) >= GBotPropertiesManager.MUSIC_CACHE_DELETION_TIMEOUT_MINUTES:
                    await context.send(f'Please play sounds less than {GBotPropertiesManager.MUSIC_CACHE_DELETION_TIMEOUT_MINUTES} minutes.')
                # searching off the event loop (A-23) put an await between reading isPlaying and
                # acting on it, so two /play commands in one guild could both see "not playing",
                # both start playback, and the second raise "Already playing audio"
                else:
                    async with self.musicStates[serverId]['playLock']:
                        if self.musicStates[serverId]['isPlaying'] == False:
                            self.musicStates[serverId]['queue'].append([song, voiceChannel, searchString])
                            await context.send(f'Playing sound:\n{title}')
                            await self.channelSync(serverId)
                            self.playMusic(serverId)
                        elif not self.musicStates[serverId]['isElevatorMode']:
                            self.musicStates[serverId]['queue'].append([song, voiceChannel, searchString])
                            queueSize = len(self.musicStates[serverId]['queue'])
                            await context.send(f'Sound added to the queue ({queueSize}):\n{title}')
                        else:
                            await context.send("Please disable elevator mode to add songs to the queue.")
            else:
                await context.send('Could not get the video sound. Try using share button to get video URL.')

    @nextcord.slash_command(name = strings.QUEUE_NAME, description = strings.QUEUE_BRIEF, guild_ids = GBotPropertiesManager.SLASH_COMMAND_TEST_GUILDS)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isMessageSentInGuild(True)
    @predicates.isFeatureEnabledForServer('toggle_music', False, True)
    async def queueSlash(self, interaction: nextcord.Interaction):
        await self.commonQueue(interaction)

    @commands.command(aliases = strings.QUEUE_ALIASES, brief = "- " + strings.QUEUE_BRIEF, description = strings.QUEUE_DESCRIPTION)
    @predicates.isFeatureEnabledForServer('toggle_music', False)
    @predicates.isFeatureEnabledForServer('toggle_legacy_prefix_commands', False)
    @predicates.isMessageSentInGuild()
    @predicates.isGuildOrUserSubscribed()
    async def queue(self, ctx: Context):
        await self.commonQueue(ctx)

    async def commonQueue(self, context):
        serverId = str(context.guild.id)

        fields = []
        if self.musicStates[serverId]['isPlaying']:
            fields.append({
                'name': 'Now Playing',
                'value': '`' + self.musicStates[serverId]['lastPlayed']['name'] + '`'
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
            data.append(f'`{i + 1}.) ' + self.musicStates[serverId]['queue'][i][0]['title'] + '`')
            isQueuedSongs = True
        if not isQueuedSongs:
            data.append('`Empty`')
        
        pages = pagination.CustomButtonMenuPages(source = pagination.DescriptionPageSource(data, "GBot Music", nextcord.Color.red(), None, 11, fields))
        await pagination.startPages(context, pages)

    @nextcord.slash_command(name = strings.ELEVATOR_NAME, description = strings.ELEVATOR_BRIEF, guild_ids = GBotPropertiesManager.SLASH_COMMAND_TEST_GUILDS)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isMessageSentInGuild(True)
    @predicates.isFeatureEnabledForServer('toggle_music', False, True)
    async def elevatorSlash(self, interaction: nextcord.Interaction):
        await self.commonElevator(interaction)

    @commands.command(aliases = strings.ELEVATOR_ALIASES, brief = "- " + strings.ELEVATOR_BRIEF, description = strings.ELEVATOR_DESCRIPTION)
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
            # if we are already playing a song when turning elevator mode on, download and cache that song
            searchString = self.musicStates[serverId]['lastPlayed']['searchString']
            if searchString != '':
                await self.searchYouTubeAndCacheDownload(searchString, True)
        else:
            elevatorStr = 'Elevator mode disabled.'
        await context.send(elevatorStr)

    @nextcord.slash_command(name = strings.SKIP_NAME, description = strings.SKIP_BRIEF, guild_ids = GBotPropertiesManager.SLASH_COMMAND_TEST_GUILDS)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isMessageSentInGuild(True)
    @predicates.isFeatureEnabledForServer('toggle_music', False, True)
    async def skipSlash(self, interaction: nextcord.Interaction):
        await self.commonSkip(interaction, interaction.user)

    @commands.command(aliases = strings.SKIP_ALIASES, brief = "- " + strings.SKIP_BRIEF, description = strings.SKIP_DESCRIPTION)
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
                await self.channelSync(serverId)
                self.playMusic(serverId)
            else:
                self.musicStates[serverId]['voiceClient'].stop()
            await context.send(f'Skipped.')
        else:
            await context.send(f'Sorry {author.mention}, there is currently nothing playing.')

    @nextcord.slash_command(name = strings.STOP_NAME, description = strings.STOP_BRIEF, guild_ids = GBotPropertiesManager.SLASH_COMMAND_TEST_GUILDS)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isMessageSentInGuild(True)
    @predicates.isFeatureEnabledForServer('toggle_music', False, True)
    async def stopSlash(self, interaction: nextcord.Interaction):
        await self.commonStop(interaction, interaction.user)

    @commands.command(aliases = strings.STOP_ALIASES, brief = "- " + strings.STOP_BRIEF, description = strings.STOP_DESCRIPTION)
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

    @nextcord.slash_command(name = strings.PAUSE_NAME, description = strings.PAUSE_BRIEF, guild_ids = GBotPropertiesManager.SLASH_COMMAND_TEST_GUILDS)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isMessageSentInGuild(True)
    @predicates.isFeatureEnabledForServer('toggle_music', False, True)
    async def pauseSlash(self, interaction: nextcord.Interaction):
        await self.commonPause(interaction, interaction.user)

    @commands.command(aliases = strings.PAUSE_ALIASES, brief = "- " + strings.PAUSE_BRIEF, description = strings.PAUSE_DESCRIPTION)
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

    @nextcord.slash_command(name = strings.RESUME_NAME, description = strings.RESUME_BRIEF, guild_ids = GBotPropertiesManager.SLASH_COMMAND_TEST_GUILDS)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isMessageSentInGuild(True)
    @predicates.isFeatureEnabledForServer('toggle_music', False, True)
    async def resumeSlash(self, interaction: nextcord.Interaction):
        await self.commonResume(interaction, interaction.user)

    @commands.command(aliases = strings.RESUME_ALIASES, brief = "- " + strings.RESUME_BRIEF, description = strings.RESUME_DESCRIPTION)
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

    async def searchYouTubeAndCacheDownload(self, searchString, isElevatorMode):
        # A-23: extract_info is a blocking network + parse call, so on the event loop it stalled
        # the whole bot — gateway and API included — for the duration of every /play.
        info = await asyncio.to_thread(self.extractSongInfo, searchString)
        if info is None:
            return None
        title = info['title']
        if isElevatorMode and title not in self.cachedYouTubeFiles:
            filepath = f'{self.DOWNLOADED_VIDEOS_PATH}/{ytUtils.sanitize_filename(title)}.mp3'
            self.logger.info(f'GBot Music adding sound file to music cache: {filepath}')
            self.cachedYouTubeFiles[title] = {'filepath': filepath, 'searchString': searchString, 'url': info['url'], 'inactiveMinutes': 0, 'lifetimeMinutes': 0}
            # A-19: the download used to run on a bare Thread against the YoutubeDL instance the
            # enclosing `with` block was already closing, with no join and no error path.
            downloadTask = asyncio.create_task(self.cacheDownload(searchString, title))
            self.cacheDownloadTasks.add(downloadTask)
            downloadTask.add_done_callback(self.cacheDownloadTasks.discard)
        return info

    def extractSongInfo(self, searchString):
        # runs on a worker thread
        try:
            with YoutubeDL(self.YT_DLP_OPTIONS) as ydl:
                return ydl.extract_info(f'ytsearch:{searchString}', download = False)['entries'][0]
        except Exception:
            return None

    async def cacheDownload(self, searchString, title):
        try:
            await asyncio.to_thread(self.downloadSong, searchString)
        except Exception as e:
            # drop the cache entry we optimistically registered; playMusic streams instead, and a
            # later request can retry the download
            self.logger.error(f"GBot Music failed to add sound file to music cache for '{title}': {e}")
            self.cachedYouTubeFiles.pop(title, None)

    def downloadSong(self, searchString):
        # runs on a worker thread, with a YoutubeDL instance of its own
        with YoutubeDL(self.YT_DLP_OPTIONS) as ydl:
            ydl.download([f'ytsearch:{searchString}'])

    async def channelSync(self, serverId):
        musicState = self.musicStates[serverId]
        queue = musicState['queue']
        if len(queue) == 0 and not musicState['isElevatorMode']:
            return

        # the channel to be in is the one whose audio playMusic is about to play: the elevator's
        # own channel while it is repeating, otherwise the channel the queue head was asked from.
        # A-18: both branches used to index queue[0] unconditionally, so elevator mode with an
        # empty queue — the state a dropped voice connection leaves behind — raised IndexError.
        if musicState['isElevatorMode'] and musicState['lastPlayed']['url'] != '':
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

    def playMusic(self, serverId):
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
        if musicState['isElevatorMode'] and musicState['lastPlayed']['url'] != '':
            url = musicState['lastPlayed']['url']
            title = musicState['lastPlayed']['name']
            channel = musicState['lastPlayed']['channel']
            searchString = musicState['lastPlayed']['searchString']
        elif len(musicState['queue']) > 0:
            song, channel, searchString = musicState['queue'].pop(0)
            url = song['source']
            title = song['title']
        else:
            musicState['isPlaying'] = False
            return

        musicState['isPlaying'] = True
        self.logger.info(f"GBot Music playing next sound '{title}' ({url}) in channel {channel} in guild {serverId}.")

        cachedSoundFile = self.cachedYouTubeFiles.get(title, None)
        if cachedSoundFile and os.path.exists(cachedSoundFile['filepath']):
            self.cachedYouTubeFiles[title]['inactiveMinutes'] = 0
            source = nextcord.FFmpegPCMAudio(cachedSoundFile['filepath'])
            musicState['lastPlayed']['url'] = cachedSoundFile['url']
        else:
            source = nextcord.FFmpegPCMAudio(url, **self.FFMPEG_OPTIONS)
            musicState['lastPlayed']['url'] = url

        # A-20: after runs on ffmpeg's audio thread. Returning a coroutine hands it back to the
        # event loop (nextcord submits it with run_coroutine_threadsafe), so musicStates is only
        # ever mutated there.
        voiceClient.play(source, after = lambda error: self.onSongFinished(serverId, error))

        musicState['lastPlayed']['name'] = title
        musicState['lastPlayed']['channel'] = channel
        musicState['lastPlayed']['searchString'] = searchString

    async def onSongFinished(self, serverId, error):
        if error is not None:
            # A-20: the callback's error argument was discarded, so an ffmpeg failure was
            # indistinguishable from a song ending and silently advanced the queue
            self.logger.error(f'GBot Music playback error in guild {serverId}: {error}')
        self.playMusic(serverId)

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
            self.musicStates[serverId]['lastPlayed']['url'] = ''
            self.musicStates[serverId]['lastPlayed']['name'] = ''
            self.musicStates[serverId]['lastPlayed']['channel'] = None
            self.musicStates[serverId]['lastPlayed']['searchString'] = ''
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