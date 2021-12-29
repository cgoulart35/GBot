#region IMPORTS
import os
import logging
import asyncio
import nextcord
from nextcord.ext import commands, tasks
from nextcord.ext.commands.context import Context
from youtube_dl import YoutubeDL

import predicates
import config.queries
#endregion

class Music(commands.Cog):

    def __init__(self, client: nextcord.Client):
        self.client = client
        self.logger = logging.getLogger()
        self.MUSIC_TIMEOUT_SECONDS = int(os.getenv("MUSIC_TIMEOUT_SECONDS"))
        self.YDL_OPTIONS = {'format': 'bestaudio', 'noplaylist':'True'}
        self.FFMPEG_OPTIONS = {'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5', 'options': '-vn'}
        
        self.musicStates = {}
        servers = config.queries.getAllServers()
        for serverId in servers.keys():
            serverMusicState = {
                'isPlaying': False,
                'isElevatorMode': False,
                'voiceClient': None,
                'queue': [],
                'lastPlayed': {'url': '', 'name': '', 'channel': None},
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
            'lastPlayed': {'url': '', 'name': '', 'channel': None},
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

    # Tasks
    @tasks.loop(seconds=1)
    async def music_timeout(self):
        for serverId, musicState in self.musicStates.items():
            if musicState['voiceClient'] != None:
                if not musicState['voiceClient'].is_playing():
                    musicState['inactiveSeconds'] += 1
                    if musicState['inactiveSeconds'] >= self.MUSIC_TIMEOUT_SECONDS:
                        await self.disconnectAndClearQueue(serverId)
                        musicState['inactiveSeconds'] = 0
                else:
                    musicState['inactiveSeconds'] = 0
            else:
                musicState['inactiveSeconds'] = 0

    # Commands
    @commands.command(brief = "- Play videos/music downloaded from YouTube.", description = "Play videos/music downloaded from YouTube. No playlists or livestreams.")
    @predicates.isFeatureEnabledForServer('toggle_music')
    @predicates.isMessageSentInGuild()
    async def play(self, ctx: Context, searchString):
        if ctx.author.voice is None:
            await ctx.send('Please connect to a voice channel.')
        else:
            voiceChannel = ctx.author.voice.channel
            song = self.searchYouTube(searchString)
            if song != None:
                serverId = str(ctx.guild.id)
                self.musicStates[serverId]['queue'].append([song, voiceChannel])
                title = song['title']
                if self.musicStates[serverId]['isPlaying'] == False:
                    await ctx.send(f'Playing sound:\n{title}')
                    await self.playMusic(serverId)
                else:
                    queueSize = len(self.musicStates[serverId]['queue'])
                    await ctx.send(f'Sound added to the queue ({queueSize}):\n{title}')
            else:
                await ctx.send('Could not get the video sound. Try using share button to get video URL.')

    @commands.command(brief = "- Displays the current sounds in queue.", description = "Displays the current sounds in queue.")
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

    @commands.command(brief = "- Toggle elevator mode to keep the last played sound on repeat.", description = "Toggle elevator mode to keep the last played sound on repeat.")
    @predicates.isFeatureEnabledForServer('toggle_music')
    @predicates.isMessageSentInGuild()
    async def elevator(self, ctx: Context):
        serverId = str(ctx.guild.id)
        currentElevatorMode = self.musicStates[serverId]['isElevatorMode']
        newElevatorMode = not currentElevatorMode
        self.musicStates[serverId]['isElevatorMode'] = newElevatorMode
        if newElevatorMode:
            elevatorStr = 'Elevator mode enabled.'
        else:
            elevatorStr = 'Elevator mode disabled.'
        await ctx.send(elevatorStr)

    @commands.command(brief = "- Skips the current sound being played.", description = "Skips the current sound being played.")
    @predicates.isFeatureEnabledForServer('toggle_music')
    @predicates.isMessageSentInGuild()
    async def skip(self, ctx: Context):
        serverId = str(ctx.guild.id)
        if self.musicStates[serverId]['voiceClient'] != None:
            if self.musicStates[serverId]['isElevatorMode'] and not self.musicStates[serverId]['isPlaying']:
                await self.playMusic(serverId)
            else:
                self.musicStates[serverId]['voiceClient'].stop()

    @commands.command(brief = "- Stops the bot from playing sounds and clears the queue.", description = "Stops the bot from playing sounds and clears the queue.")
    @predicates.isFeatureEnabledForServer('toggle_music')
    @predicates.isMessageSentInGuild()
    async def stop(self, ctx: Context):
        serverId = str(ctx.guild.id)
        if self.musicStates[serverId]['voiceClient'] != None:
            await self.disconnectAndClearQueue(serverId)

    @commands.command(brief = "- Pauses the current sound being played.", description = "Pauses the current sound being played.")
    @predicates.isFeatureEnabledForServer('toggle_music')
    @predicates.isMessageSentInGuild()
    async def pause(self, ctx: Context):
        serverId = str(ctx.guild.id)
        if self.musicStates[serverId]['voiceClient'] != None and self.musicStates[serverId]['voiceClient'].is_playing():
            self.musicStates[serverId]['voiceClient'].pause()

    @commands.command(brief = "- Resumes the current sound being played.", description = "Resumes the current sound being played.")
    @predicates.isFeatureEnabledForServer('toggle_music')
    @predicates.isMessageSentInGuild()
    async def resume(self, ctx: Context):
        serverId = str(ctx.guild.id)
        if self.musicStates[serverId]['voiceClient'] != None and self.musicStates[serverId]['voiceClient'].is_paused():
            self.musicStates[serverId]['voiceClient'].resume()

    def searchYouTube(self, item):
        with YoutubeDL(self.YDL_OPTIONS) as ydl:
            try: 
                info = ydl.extract_info("ytsearch:%s" % item, download=False)['entries'][0]
            except Exception: 
                return None

        return {'source': info['formats'][0]['url'], 'title': info['title']}

    async def playMusic(self, serverId):
        if len(self.musicStates[serverId]['queue']) > 0 or self.musicStates[serverId]['isElevatorMode']:
            self.musicStates[serverId]['isPlaying'] = True
            
            if self.musicStates[serverId]['isElevatorMode'] and self.musicStates[serverId]['lastPlayed']['url'] != '':
                url = self.musicStates[serverId]['lastPlayed']['url']
                title = self.musicStates[serverId]['lastPlayed']['name']
                channel = self.musicStates[serverId]['lastPlayed']['channel']
            else:
                url = self.musicStates[serverId]['queue'][0][0]['source']
                title = self.musicStates[serverId]['queue'][0][0]['title']
                channel = self.musicStates[serverId]['queue'][0][1] 

            if self.musicStates[serverId]['voiceClient'] == None or not self.musicStates[serverId]['voiceClient'].is_connected():
                self.musicStates[serverId]['voiceClient'] = await self.musicStates[serverId]['queue'][0][1].connect()  
            else:
                await self.musicStates[serverId]['voiceClient'].move_to(channel)

            if not self.musicStates[serverId]['isElevatorMode'] or self.musicStates[serverId]['lastPlayed']['url'] == '':
                self.musicStates[serverId]['queue'].pop(0)

            self.musicStates[serverId]['voiceClient'].play(nextcord.FFmpegPCMAudio(url, **self.FFMPEG_OPTIONS), after=lambda e: asyncio.run(self.playMusic(serverId)))
            self.musicStates[serverId]['lastPlayed']['url'] = url
            self.musicStates[serverId]['lastPlayed']['name'] = title
            self.musicStates[serverId]['lastPlayed']['channel'] = channel
        else:
            self.musicStates[serverId]['isPlaying'] = False

    async def disconnectAndClearQueue(self, serverId):
        if self.musicStates[serverId]['voiceClient'] != None:
            await self.musicStates[serverId]['voiceClient'].disconnect()
            self.musicStates[serverId]['voiceClient'] = None
            self.musicStates[serverId]['queue'] = []
            self.musicStates[serverId]['isPlaying'] = False
            self.musicStates[serverId]['isElevatorMode'] = False
            self.musicStates[serverId]['lastPlayed']['url'] = ''
            self.musicStates[serverId]['lastPlayed']['name'] = ''
            self.musicStates[serverId]['lastPlayed']['channel'] = None

def setup(client: commands.Bot):
    client.add_cog(Music(client))