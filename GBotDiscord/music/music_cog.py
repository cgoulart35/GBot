#region IMPORTS
import pathlib
import os
import logging
import nextcord
from nextcord.ext import commands, tasks
from nextcord.ext.commands.context import Context
from yt_dlp import YoutubeDL, utils as ytUtils
from threading import Thread

from GBotDiscord import pagination
from GBotDiscord import predicates
from GBotDiscord.config import config_queries
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
        self.MUSIC_TIMEOUT_SECONDS = int(os.getenv("MUSIC_TIMEOUT_SECONDS"))
        self.MUSIC_CACHE_DELETION_TIMEOUT_MINUTES = int(os.getenv("MUSIC_CACHE_DELETION_TIMEOUT_MINUTES"))

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
            'outtmpl': f'{self.DOWNLOADED_VIDEOS_PATH}/%(title)s'+'.mp3',
            'logger': self.ytdlLogger
        }

        self.cachedYouTubeFiles = {}
        self.musicStates = {}
        servers = config_queries.getAllServers()
        for serverId in servers.keys():
            serverMusicState = {
                'isPlaying': False,
                'isElevatorMode': False,
                'voiceClient': None,
                'queue': [],
                'lastPlayed': {'url': '', 'name': '', 'channel': None, 'searchString': ''},
                'inactiveSeconds': 0
            }
            self.musicStates[serverId] = serverMusicState

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
            'inactiveSeconds': 0
        }
        self.musicStates[str(guild.id)] = serverMusicState

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: nextcord.Guild):
        self.logger.info(f'Removing server music state for guild {guild.id} ({guild.name}).')
        self.musicStates.pop(str(guild.id))

    @commands.Cog.listener()
    async def on_ready(self):
        try:
            self.music_timeout.start()
        except RuntimeError:
            self.logger.info('music_timeout task is already launched and is not completed.')
        try:
            self.cached_youtube_files.start()
        except RuntimeError:
            self.logger.info('cached_youtube_files task is already launched and is not completed.')

    # Tasks
    @tasks.loop(seconds=1)
    async def music_timeout(self):
        for serverId, musicState in self.musicStates.items():
            if musicState['voiceClient'] != None:
                if not musicState['voiceClient'].is_playing():
                    musicState['inactiveSeconds'] += 1
                    if musicState['inactiveSeconds'] >= self.MUSIC_TIMEOUT_SECONDS:
                        self.logger.info(f'GBot Music timed out for guild {serverId} due to inactivity.')
                        await self.disconnectAndClearQueue(serverId)
                        musicState['inactiveSeconds'] = 0
                else:
                    musicState['inactiveSeconds'] = 0
            else:
                musicState['inactiveSeconds'] = 0

    @tasks.loop(minutes=1)
    async def cached_youtube_files(self):
        if any(self.cachedYouTubeFiles):
            self.logger.info(f'GBot Music - CACHED YOUTUBE FILES: {self.cachedYouTubeFiles}')
        cachedYouTubeFilesCopy = self.cachedYouTubeFiles.copy()
        for fileKey, fileInfo in cachedYouTubeFilesCopy.items():
            filepath = fileInfo['filepath']
            cachedFileExists = os.path.exists(filepath)
            if cachedFileExists:
                if fileInfo['inactiveMinutes'] >= self.MUSIC_CACHE_DELETION_TIMEOUT_MINUTES:
                    self.logger.info(f'GBot Music removing sound file from music cache: {filepath}')
                    os.remove(filepath)
                    self.cachedYouTubeFiles.pop(fileKey)
                else:
                    self.cachedYouTubeFiles[fileKey]['inactiveMinutes'] += 1
                    self.cachedYouTubeFiles[fileKey]['lifetimeMinutes'] += 1
            elif fileInfo['inactiveMinutes'] >= self.MUSIC_CACHE_DELETION_TIMEOUT_MINUTES:
                self.logger.info(f'GBot Music removing sound file that was not found from music cache: {filepath}')
                self.cachedYouTubeFiles.pop(fileKey)

    # Commands
    @commands.command(aliases=['p', 'pl'], brief = "- Play videos/music downloaded from YouTube.", description = "Play videos/music downloaded from YouTube. No playlists or livestreams.")
    @predicates.isFeatureEnabledForServer('toggle_music')
    @predicates.isMessageSentInGuild()
    @predicates.isGuildOrUserSubscribed()
    async def play(self, ctx: Context, *args):
        if ctx.author.voice is None:
            await ctx.send('Please connect to a voice channel.')
        else:
            searchString = ' '.join(args)
            voiceChannel = ctx.author.voice.channel
            serverId = str(ctx.guild.id)
            songInfo = self.searchYouTubeAndCacheDownload(searchString, self.musicStates[serverId]['isElevatorMode'])
            if songInfo != None:
                song = {'source': songInfo['url'], 'title': songInfo['title']}
                title = song['title']
                if (songInfo['duration'] / 60) >= self.MUSIC_CACHE_DELETION_TIMEOUT_MINUTES:
                    await ctx.send(f'Please play sounds less than {self.MUSIC_CACHE_DELETION_TIMEOUT_MINUTES} minutes.')
                elif self.musicStates[serverId]['isPlaying'] == False:
                    self.musicStates[serverId]['queue'].append([song, voiceChannel, searchString])
                    await ctx.send(f'Playing sound:\n{title}')
                    await self.channelSync(serverId)
                    self.playMusic(serverId)
                else:
                    if not self.musicStates[serverId]['isElevatorMode']:
                        self.musicStates[serverId]['queue'].append([song, voiceChannel, searchString])
                        queueSize = len(self.musicStates[serverId]['queue'])
                        await ctx.send(f'Sound added to the queue ({queueSize}):\n{title}')
                    else:
                        await ctx.send("Please disable elevator mode to add songs to the queue.")
            else:
                await ctx.send('Could not get the video sound. Try using share button to get video URL.')

    @commands.command(aliases=['q'], brief = "- Displays the current sounds in queue.", description = "Displays the current sounds in queue.")
    @predicates.isFeatureEnabledForServer('toggle_music')
    @predicates.isMessageSentInGuild()
    @predicates.isGuildOrUserSubscribed()
    async def queue(self, ctx: Context):
        serverId = str(ctx.guild.id)
        data = []
        data.append('**Elevator Mode**')
        if self.musicStates[serverId]['isElevatorMode']:
            elevatorStr = '`Enabled`'
            if self.musicStates[serverId]['lastPlayed']['url'] != '':
                soundName = self.musicStates[serverId]['lastPlayed']['name']
                elevatorStr += f" : `{soundName}`"
            data.append(elevatorStr)
        else:
            data.append('`Disabled`')

        data.append('**Queue**')
        for i in range(0, len(self.musicStates[serverId]['queue'])):
            data.append(f'`{i + 1}.) ' + self.musicStates[serverId]['queue'][i][0]['title'] + '`')
        if len(data) <= 3:
            data.append('`No sounds in the queue.`')
        
        pages = pagination.CustomButtonMenuPages(source = pagination.DescriptionPageSource(data, "GBot Music", nextcord.Color.red(), None, 10))
        await pages.start(ctx)

    @commands.command(aliases=['e'], brief = "- Toggle elevator mode to keep the last played sound on repeat.", description = "Toggle elevator mode to keep the last played sound on repeat.")
    @predicates.isFeatureEnabledForServer('toggle_music')
    @predicates.isMessageSentInGuild()
    @predicates.isGuildOrUserSubscribed()
    async def elevator(self, ctx: Context):
        serverId = str(ctx.guild.id)
        currentElevatorMode = self.musicStates[serverId]['isElevatorMode']
        newElevatorMode = not currentElevatorMode
        self.musicStates[serverId]['isElevatorMode'] = newElevatorMode
        if newElevatorMode:
            elevatorStr = 'Elevator mode enabled.'
            # if we are already playing a song when turning elevator mode on, download and cache that song
            searchString = self.musicStates[serverId]['lastPlayed']['searchString']
            if searchString != '':
                self.searchYouTubeAndCacheDownload(searchString, True)
        else:
            elevatorStr = 'Elevator mode disabled.'
        await ctx.send(elevatorStr)

    @commands.command(aliases=['s', 'sk'], brief = "- Skips the current sound being played.", description = "Skips the current sound being played.")
    @predicates.isFeatureEnabledForServer('toggle_music')
    @predicates.isMessageSentInGuild()
    @predicates.isGuildOrUserSubscribed()
    async def skip(self, ctx: Context):
        serverId = str(ctx.guild.id)
        if self.musicStates[serverId]['voiceClient'] != None:
            if self.musicStates[serverId]['isElevatorMode'] and not self.musicStates[serverId]['isPlaying']:
                await self.channelSync(serverId)
                self.playMusic(serverId)
            else:
                self.musicStates[serverId]['voiceClient'].stop()

    @commands.command(aliases=['st'], brief = "- Stops the bot from playing sounds and clears the queue.", description = "Stops the bot from playing sounds and clears the queue.")
    @predicates.isFeatureEnabledForServer('toggle_music')
    @predicates.isMessageSentInGuild()
    @predicates.isGuildOrUserSubscribed()
    async def stop(self, ctx: Context):
        serverId = str(ctx.guild.id)
        if self.musicStates[serverId]['voiceClient'] != None:
            await self.disconnectAndClearQueue(serverId)

    @commands.command(aliases=['pa', 'ps'], brief = "- Pauses the current sound being played.", description = "Pauses the current sound being played.")
    @predicates.isFeatureEnabledForServer('toggle_music')
    @predicates.isMessageSentInGuild()
    @predicates.isGuildOrUserSubscribed()
    async def pause(self, ctx: Context):
        serverId = str(ctx.guild.id)
        if self.musicStates[serverId]['voiceClient'] != None and self.musicStates[serverId]['voiceClient'].is_playing():
            self.musicStates[serverId]['voiceClient'].pause()

    @commands.command(aliases=['r'], brief = "- Resumes the current sound being played.", description = "Resumes the current sound being played.")
    @predicates.isFeatureEnabledForServer('toggle_music')
    @predicates.isMessageSentInGuild()
    @predicates.isGuildOrUserSubscribed()
    async def resume(self, ctx: Context):
        serverId = str(ctx.guild.id)
        if self.musicStates[serverId]['voiceClient'] != None and self.musicStates[serverId]['voiceClient'].is_paused():
            self.musicStates[serverId]['voiceClient'].resume()

    def searchYouTubeAndCacheDownload(self, searchString, isElevatorMode):
        with YoutubeDL(self.YT_DLP_OPTIONS) as ydl:
            try:
                item = "ytsearch:" + searchString
                info = ydl.extract_info(item, download = False)['entries'][0]
                title = info['title']
                url = info['url']
                if isElevatorMode and title not in self.cachedYouTubeFiles:
                    filepath = f'{self.DOWNLOADED_VIDEOS_PATH}/{ytUtils.sanitize_filename(title)}.mp3'
                    self.logger.info(f'GBot Music adding sound file to music cache: {filepath}')
                    downloadThread = Thread(target = ydl.download, args=[[item]])
                    downloadThread.start()
                    self.cachedYouTubeFiles[title] = {'filepath': filepath, 'searchString': searchString, 'url': url, 'inactiveMinutes': 0, 'lifetimeMinutes': 0}
            except Exception:
                return None

        return info

    async def channelSync(self, serverId):
        if len(self.musicStates[serverId]['queue']) > 0 or self.musicStates[serverId]['isElevatorMode']:           
            if self.musicStates[serverId]['isElevatorMode'] and self.musicStates[serverId]['lastPlayed']['url'] != '':
                channel = self.musicStates[serverId]['lastPlayed']['channel']
            else:
                channel = self.musicStates[serverId]['queue'][0][1] 
            if self.musicStates[serverId]['voiceClient'] == None or not self.musicStates[serverId]['voiceClient'].is_connected():
                channel = self.musicStates[serverId]['queue'][0][1] 
                self.logger.info(f'GBot Music connecting to channel {channel.id} in guild {serverId}.')
                self.musicStates[serverId]['voiceClient'] = await channel.connect()  
            else:
                self.logger.info(f'GBot Music moving to channel {channel.id} in guild {serverId}.')
                await self.musicStates[serverId]['voiceClient'].move_to(channel)

    def playMusic(self, serverId):
        if len(self.musicStates[serverId]['queue']) > 0 or self.musicStates[serverId]['isElevatorMode']:
            self.musicStates[serverId]['isPlaying'] = True
            
            if self.musicStates[serverId]['isElevatorMode'] and self.musicStates[serverId]['lastPlayed']['url'] != '':
                url = self.musicStates[serverId]['lastPlayed']['url']
                title = self.musicStates[serverId]['lastPlayed']['name']
                channel = self.musicStates[serverId]['lastPlayed']['channel']
                searchString = self.musicStates[serverId]['lastPlayed']['searchString']
            else:
                url = self.musicStates[serverId]['queue'][0][0]['source']
                title = self.musicStates[serverId]['queue'][0][0]['title']
                channel = self.musicStates[serverId]['queue'][0][1] 
                searchString = self.musicStates[serverId]['queue'][0][2] 

            if not self.musicStates[serverId]['isElevatorMode'] or self.musicStates[serverId]['lastPlayed']['url'] == '':
                self.musicStates[serverId]['queue'].pop(0)

            self.logger.info(f"GBot Music playing next sound '{title}' ({url}) in channel {channel} in guild {serverId}.")

            cachedSoundFile = self.cachedYouTubeFiles.get(title, None)
            if cachedSoundFile and os.path.exists(cachedSoundFile['filepath']):
                self.cachedYouTubeFiles[title]['inactiveMinutes'] = 0
                self.musicStates[serverId]['voiceClient'].play(nextcord.FFmpegPCMAudio(cachedSoundFile['filepath']), after=lambda e: self.playMusic(serverId))
                self.musicStates[serverId]['lastPlayed']['url'] = cachedSoundFile['url']
            else:
                self.musicStates[serverId]['voiceClient'].play(nextcord.FFmpegPCMAudio(url, **self.FFMPEG_OPTIONS), after=lambda e: self.playMusic(serverId))
                self.musicStates[serverId]['lastPlayed']['url'] = url

            self.musicStates[serverId]['lastPlayed']['name'] = title
            self.musicStates[serverId]['lastPlayed']['channel'] = channel
            self.musicStates[serverId]['lastPlayed']['searchString'] = searchString
        else:
            self.musicStates[serverId]['isPlaying'] = False

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