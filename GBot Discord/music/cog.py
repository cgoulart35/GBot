#region IMPORTS
import pathlib
import os
import logging
import nextcord
from nextcord.ext import commands, tasks
from nextcord.ext.commands.context import Context
from youtube_dl import YoutubeDL
from threading import Thread

import predicates
import utils
import config.queries
#endregion

class Music(commands.Cog):

    def __init__(self, client: nextcord.Client):
        self.client = client
        self.logger = logging.getLogger()
        self.parentDir = str(pathlib.Path(__file__).parent.parent.absolute()).replace("\\",'/')
        self.DOWNLOADED_VIDEOS_PATH = f'{self.parentDir}/sounds'
        self.REDOWNLOADED_VIDEOS_PATH = f'{self.parentDir}/sounds/redownloads'
        if not os.path.exists(self.REDOWNLOADED_VIDEOS_PATH):
            os.makedirs(self.REDOWNLOADED_VIDEOS_PATH)
        self.FFMPEG_OPTIONS = {'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5', 'options': '-vn'}
        self.MUSIC_TIMEOUT_SECONDS = int(os.getenv("MUSIC_TIMEOUT_SECONDS"))
        self.MUSIC_CACHE_DELETION_TIMEOUT_MINUTES = int(os.getenv("MUSIC_CACHE_DELETION_TIMEOUT_MINUTES"))
        self.MUSIC_CACHE_REDOWNLOAD_AFTER_MINUTES = int(os.getenv("MUSIC_CACHE_REDOWNLOAD_AFTER_MINUTES"))
        
        self.cachedYouTubeFiles = {}
        self.redownloadedYouTubeFiles = {}
        self.musicStates = {}
        servers = config.queries.getAllServers()
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
        self.music_timeout.start()
        self.cached_youtube_files.start()

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
        self.logger.info(f'GBot Music - CACHED YOUTUBE FILES: {self.cachedYouTubeFiles}')
        cachedYouTubeFilesCopy = self.cachedYouTubeFiles.copy()
        for fileKey, fileInfo in cachedYouTubeFilesCopy.items():
            filepath = fileInfo['filepath']
            cachedFileExists = os.path.exists(filepath)
            if cachedFileExists:
                cachedFileDeleted = False
                if fileInfo['inactiveMinutes'] >= self.MUSIC_CACHE_DELETION_TIMEOUT_MINUTES:
                    self.logger.info(f'GBot Music removing sound file from music cache: {filepath}')
                    os.remove(filepath)
                    self.cachedYouTubeFiles.pop(fileKey)
                    cachedFileDeleted = True
                else:
                    self.cachedYouTubeFiles[fileKey]['inactiveMinutes'] += 1
                    self.cachedYouTubeFiles[fileKey]['lifetimeMinutes'] += 1
                if fileInfo['lifetimeMinutes'] >= self.MUSIC_CACHE_REDOWNLOAD_AFTER_MINUTES and not cachedFileDeleted:
                    self.searchYouTubeAndCacheDownload(fileInfo['searchString'], isElevatorMode = True, isRedownload = True)
                    self.cachedYouTubeFiles[fileKey]['lifetimeMinutes'] = 0
            elif fileInfo['inactiveMinutes'] >= self.MUSIC_CACHE_DELETION_TIMEOUT_MINUTES:
                self.logger.info(f'GBot Music removing sound file that was not found from music cache: {filepath}')
                self.cachedYouTubeFiles.pop(fileKey)
        self.logger.info(f'GBot Music - REDOWNLOAD YOUTUBE FILES: {self.redownloadedYouTubeFiles}')
        redownloadedYouTubeFilesCopy = self.redownloadedYouTubeFiles.copy()
        for fileKey, fileInfo in redownloadedYouTubeFilesCopy.items():
            filepath = fileInfo['filepath']
            redownloadFileExists = os.path.exists(filepath)
            if redownloadFileExists:
                targetFilePath = self.cachedYouTubeFiles[fileKey]['filepath']
                targetPathExists = os.path.exists(targetFilePath)
                if targetPathExists:
                    self.logger.info(f'GBot Music replacing cached sound file with re-downloaded file: {targetFilePath}')
                    os.remove(targetFilePath)
                    os.replace(filepath, targetFilePath)
                    self.cachedYouTubeFiles[fileKey] = self.redownloadedYouTubeFiles[fileKey]
                    self.cachedYouTubeFiles[fileKey]['filepath'] = targetFilePath
                    self.cachedYouTubeFiles[fileKey]['lifetimeMinutes'] = 0
                else:
                    self.logger.info(f'GBot Music could not find the cached sound file to replace with the re-downloaded file: {targetFilePath}')
                    os.remove(filepath)
                self.redownloadedYouTubeFiles.pop(fileKey)
            elif fileInfo['lifetimeMinutes'] >= self.MUSIC_CACHE_DELETION_TIMEOUT_MINUTES:
                self.logger.info(f'GBot Music removing re-downloaded file that was not found from music cache: {filepath}')
                self.redownloadedYouTubeFiles.pop(fileKey)
            else:
                self.redownloadedYouTubeFiles[fileKey]['lifetimeMinutes'] += 1

    # Commands
    @commands.command(aliases=['p', 'pl'], brief = "- Play videos/music downloaded from YouTube.", description = "Play videos/music downloaded from YouTube. No playlists or livestreams.")
    @predicates.isFeatureEnabledForServer('toggle_music')
    @predicates.isMessageSentInGuild()
    async def play(self, ctx: Context, *args):
        if ctx.author.voice is None:
            await ctx.send('Please connect to a voice channel.')
        else:
            searchString = ' '.join(args)
            voiceChannel = ctx.author.voice.channel
            serverId = str(ctx.guild.id)
            songInfo = self.searchYouTubeAndCacheDownload(searchString, self.musicStates[serverId]['isElevatorMode'])
            song = {'source': songInfo['formats'][0]['url'], 'title': songInfo['title']}
            if song != None:
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
    async def queue(self, ctx: Context):
        queueStr = ''
        serverId = str(ctx.guild.id)
        embed = nextcord.Embed(color = nextcord.Color.red(), title = 'GBot Music')
        for i in range(0, len(self.musicStates[serverId]['queue'])):
            queueStr += f'`{i + 1}.) ' + self.musicStates[serverId]['queue'][i][0]['title'] + '`\n'
        if queueStr == '':
            queueStr = 'No sounds in the queue.'
        if self.musicStates[serverId]['isElevatorMode']:
            elevatorStr = '`Enabled`'
            if self.musicStates[serverId]['lastPlayed']['url'] != '':
                soundName = self.musicStates[serverId]['lastPlayed']['name']
                elevatorStr += f" : `{soundName}`"
        else:
            elevatorStr = '`Disabled`'
        embed.add_field(name = 'Elevator Mode', value = f"{elevatorStr}", inline = False)
        embed.add_field(name = 'Queue', value = f"{queueStr}", inline = False)
        await ctx.send(embed = embed)

    @commands.command(aliases=['e'], brief = "- Toggle elevator mode to keep the last played sound on repeat.", description = "Toggle elevator mode to keep the last played sound on repeat.")
    @predicates.isFeatureEnabledForServer('toggle_music')
    @predicates.isMessageSentInGuild()
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
    async def stop(self, ctx: Context):
        serverId = str(ctx.guild.id)
        if self.musicStates[serverId]['voiceClient'] != None:
            await self.disconnectAndClearQueue(serverId)

    @commands.command(aliases=['pa', 'ps'], brief = "- Pauses the current sound being played.", description = "Pauses the current sound being played.")
    @predicates.isFeatureEnabledForServer('toggle_music')
    @predicates.isMessageSentInGuild()
    async def pause(self, ctx: Context):
        serverId = str(ctx.guild.id)
        if self.musicStates[serverId]['voiceClient'] != None and self.musicStates[serverId]['voiceClient'].is_playing():
            self.musicStates[serverId]['voiceClient'].pause()

    @commands.command(aliases=['r'], brief = "- Resumes the current sound being played.", description = "Resumes the current sound being played.")
    @predicates.isFeatureEnabledForServer('toggle_music')
    @predicates.isMessageSentInGuild()
    async def resume(self, ctx: Context):
        serverId = str(ctx.guild.id)
        if self.musicStates[serverId]['voiceClient'] != None and self.musicStates[serverId]['voiceClient'].is_paused():
            self.musicStates[serverId]['voiceClient'].resume()

    def searchYouTubeAndCacheDownload(self, searchString, isElevatorMode, isRedownload = False):
        if isRedownload:
            downloadPath = self.REDOWNLOADED_VIDEOS_PATH
        else:
            downloadPath = self.DOWNLOADED_VIDEOS_PATH
        options = {'format': 'bestaudio', 'noplaylist':'True', 'outtmpl': f'{downloadPath}/%(title)s'+'.mp4'}
        with YoutubeDL(options) as ydl:
            try:
                ydl.cache.remove()
                item = "ytsearch:" + searchString
                info = ydl.extract_info(item, download = False)['entries'][0]
                title = info['title']
                url = info['formats'][0]['url']
                if isElevatorMode:
                    filepath = f'{downloadPath}/{utils.sanitizeFileName(title)}.mp4'
                    if isRedownload:
                        self.logger.info(f'GBot Music re-downloading sound file: {filepath}')
                        downloadThread = Thread(target = ydl.download, args=[[item]])
                        downloadThread.start()
                        inactiveMinutes = self.cachedYouTubeFiles[title]['inactiveMinutes']
                        self.redownloadedYouTubeFiles[title] = {'filepath': filepath, 'searchString': searchString, 'url': url, 'inactiveMinutes': inactiveMinutes, 'lifetimeMinutes': 0}
                    elif title not in self.cachedYouTubeFiles:
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

def setup(client: commands.Bot):
    client.add_cog(Music(client))