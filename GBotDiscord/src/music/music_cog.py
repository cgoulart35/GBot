#region IMPORTS
import asyncio
import logging
import random
import time
from types import SimpleNamespace
from urllib.parse import urlparse
import nextcord
from nextcord import Spotify
from nextcord.ext import commands, tasks
from nextcord.ext.commands.context import Context
from yt_dlp import YoutubeDL

from GBotDiscord.src import presentation
from GBotDiscord.src import strings
from GBotDiscord.src import utils
from GBotDiscord.src import pagination
from GBotDiscord.src import predicates
from GBotDiscord.src.config import config_queries
from GBotDiscord.src.properties import GBotPropertiesManager
#endregion

MUSIC_BUTTON_PREFIX = 'music:'
MUSIC_PAUSE = 'pause'
MUSIC_SKIP = 'skip'
MUSIC_STOP = 'stop'
MUSIC_SHUFFLE = 'shuffle'
MUSIC_ELEVATOR = 'elevator'
MUSIC_ADD = 'add'
MUSIC_QUEUE = 'queue'
MUSIC_SPOTIFY = 'spotify'
MUSIC_RESTART = 'restart'
CARD_UP_NEXT = 5
QUEUE_PER_PAGE = 10

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
            'logger': self.ytdlLogger,
            # every named site stays available. The generic extractor is the one that opens any address
            # it's given, so a pasted link could otherwise reach the machine the bot runs on or its network.
            'allowed_extractors': ['default', '-generic'],
            # yt-dlp's default order once a JS runtime is present puts tv_samsung first, and its
            # stream URLs failed ffmpeg with a 403 on every attempt on one machine while working on
            # another behind the same public IP. visionos worked on both, so it goes first and the
            # rest of yt-dlp's defaults stay as fallbacks (ledger C-15).
            'extractor_args': {'youtube': {'player_client': ['visionos', 'tv_samsung', 'web']}}
        }

        self.spotifySyncSessions = {}
        self.musicStates = {}

    def newLastPlayed(self):
        # one shape, built in two places (newMusicState and disconnectAndClearQueue).
        # 'song' is the same dict the queue holds, so everything that renders a song renders this
        # one identically — and it deliberately carries no stream URL (C-6/C-14): that link expires,
        # and is resolved fresh in playMusic every time instead.
        return {'song': None, 'channel': None}

    def newPlaybackClock(self):
        # what the now-playing card's progress bar reads. Replaced wholesale when a song starts.
        return {'startedAt': None, 'pausedAt': None, 'heldSeconds': 0}

    def newMusicState(self):
        return {
            'isPlaying': False,
            'isElevatorMode': False,
            'voiceClient': None,
            'queue': [],
            'lastPlayed': self.newLastPlayed(),
            'playback': self.newPlaybackClock(),
            'isRestarting': False,
            'inactiveSeconds': 0,
            'emptySeconds': 0,
            # the now-playing card, as a message of its channel's, and what was last done on it
            'card': None,
            'lastAction': None,
            # queueing a song is a read-modify-write of this state, and threading the yt-dlp
            # search (A-23) put an await in the middle of it. Lives in the state dict so the
            # three lifecycle listeners wire it up for free.
            'playLock': asyncio.Lock()
        }

    # Events
    @commands.Cog.listener()
    async def on_guild_join(self, guild: nextcord.Guild):
        self.logger.info(f'Adding server music state for guild {guild.id} ({guild.name}).')
        self.musicStates[str(guild.id)] = self.newMusicState()

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: nextcord.Guild):
        self.logger.info(f'Removing server music state for guild {guild.id} ({guild.name}).')
        # pop with a default; a guild filtered out by filterGuildsForInstance was never initialized
        self.musicStates.pop(str(guild.id), None)
        # tear down any spotify sync session too, otherwise spotify_sync keeps polling a guild we left
        self.spotifySyncSessions.pop(str(guild.id), None)

    @commands.Cog.listener()
    async def on_ready(self):
        # every time, not only the first: this also fires on a reconnect, and a server that added the
        # bot while it was offline only ever gets a place in client.guilds, never a join event
        for guild in self.client.guilds:
            if str(guild.id) not in self.musicStates:
                self.musicStates[str(guild.id)] = self.newMusicState()
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
        # iterate a snapshot of the keys; the awaits below can remove entries from musicStates
        for serverId in list(self.musicStates.keys()):
            # one guild's failure stays its own: this used to abort the pass, skipping every later guild
            try:
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
                self.logger.error(f'Error in Music.music_timeout() for guild {serverId}: {e}')

    @tasks.loop(seconds=1)
    async def spotify_sync(self):
        # iterate a snapshot of the keys; commonPlay below can remove entries from spotifySyncSessions
        for serverId in list(self.spotifySyncSessions.keys()):
            # one guild's failure stays its own: this used to abort the pass, skipping every later guild
            try:
                spotifySyncSession = self.spotifySyncSessions.get(serverId)
                if spotifySyncSession is None:
                    continue
                author = spotifySyncSession['author']
                target = spotifySyncSession['target']
                guild: nextcord.Guild = target.guild
                userId = spotifySyncSession['userId']
                lastActivity = spotifySyncSession['lastActivity']

                user = guild.get_member(userId)
                # the followed user left the guild (or the guild is gone); end the session rather
                # than dereferencing None on every tick from here on
                if user is None:
                    self.logger.info(f'GBot Music ended the spotify sync session in guild {serverId} because user {userId} is no longer available.')
                    self.spotifySyncSessions.pop(serverId, None)
                    await self.updateCard(serverId)
                    continue
                for activity in user.activities:
                    if isinstance(activity, Spotify):
                        activityStr = f'{activity.title} by {activity.artist}'
                        if lastActivity != activityStr:
                            self.spotifySyncSessions[serverId]['lastActivity'] = activityStr
                            await self.commonPlay(target, author, [activityStr], False)
            except Exception as e:
                self.logger.error(f'Error in Music.spotify_sync() for guild {serverId}: {e}')

    # Commands
    @nextcord.slash_command(name = strings.MUSIC_NAME, description = strings.MUSIC_BRIEF, guild_ids = GBotPropertiesManager.SLASH_COMMAND_TEST_GUILDS)
    @predicates.isGuildOrUserSubscribed(True)
    @predicates.isMessageSentInGuild(True)
    @predicates.isFeatureEnabledForServer('toggle_music', False, True)
    async def musicSlash(self,
                         interaction: nextcord.Interaction,
                         search = nextcord.SlashOption(
                            name = 'search',
                            required = False,
                            description = strings.MUSIC_SEARCH_DESCRIPTION
                         )):
        await self.commonMusic(interaction, interaction.user, utils.strParamToArgs(search) if search else [])

    @commands.command(name = strings.MUSIC_NAME, aliases = strings.MUSIC_ALIASES, brief = "- " + strings.MUSIC_BRIEF, description = strings.MUSIC_DESCRIPTION)
    @predicates.isFeatureEnabledForServer('toggle_music', False)
    @predicates.isFeatureEnabledForServer('toggle_legacy_prefix_commands', False)
    @predicates.isMessageSentInGuild()
    @predicates.isGuildOrUserSubscribed()
    async def music(self, ctx: Context, *search):
        await self.commonMusic(ctx, ctx.author, search)

    async def commonMusic(self, context, author, search):
        # a search plays it, and nothing else shows the card, or offers to start one
        if search:
            await self.commonPlay(context, author, search)
            return
        serverId = str(context.guild.id)
        if self.musicStates[serverId]['voiceClient'] is not None:
            # posted again at the bottom, as the old one may be far up the channel by now
            await presentation.deferIfSlash(context)
            await self.postCard(serverId, context, moveDown = True)
            return
        view = pagination.OwnedView()
        view.button('➕', self.addSongButton, label = 'Add song', style = nextcord.ButtonStyle.success)
        embed = presentation.brandEmbed(title = '🎵 Nothing is playing', description = 'Join a voice channel, then add a song: a search, a YouTube link or a playlist.', feature = 'Music')
        await view.send(context, True, embed = embed, view = view)

    #region the now-playing card
    def cardEmbed(self, serverId):
        musicState = self.musicStates[serverId]
        song = musicState['lastPlayed']['song']
        voiceClient = musicState['voiceClient']
        isPaused = voiceClient is not None and voiceClient.is_paused()
        if song is None or not musicState['isPlaying']:
            embed = presentation.brandEmbed(title = '🎵 Between songs', description = 'The next song is on its way.', feature = 'Music')
        else:
            where = f"\nIn 🔊 **{voiceClient.channel.name}**" if voiceClient is not None else ''
            embed = presentation.brandEmbed(title = '⏸️ Paused' if isPaused else '🎵 Now playing', description = f'{self.describeNowPlaying(musicState)}{where}', feature = 'Music')
        queue = musicState['queue']
        upNext = [f"`{number}.` {self.describeSongEmbed(entry[0])}" for number, entry in enumerate(queue[:CARD_UP_NEXT], start = 1)]
        if len(queue) > CARD_UP_NEXT:
            upNext.append(f'…and {len(queue) - CARD_UP_NEXT} more')
        # elevator mode and following Spotify show on their buttons, so the card has room for the songs
        session = self.spotifySyncSessions.get(serverId)
        if session:
            embed.description += f"\n🎧 Following {session['userMention']}'s Spotify"
        heading = f"Up next · {len(queue)} song{'' if len(queue) == 1 else 's'}" if queue else 'Up next'
        embed.add_field(name = heading, value = '\n'.join(upNext)[:1024] or 'Nothing queued', inline = False)
        if musicState['lastAction']:
            embed.add_field(name = '​', value = musicState['lastAction'][:1024], inline = False)
        return embed

    def cardButtons(self, serverId):
        # Their ids say what they do, so they keep working after a restart. Anyone in GBot's voice
        # channel can press them, as anyone there could use the commands.
        musicState = self.musicStates[serverId]
        voiceClient = musicState['voiceClient']
        isPaused = voiceClient is not None and voiceClient.is_paused()
        # green is on, as the config card's toggles are
        def toggle(isOn):
            return nextcord.ButtonStyle.success if isOn else nextcord.ButtonStyle.secondary
        # the song playing on the first row, as a player's controls are, and the queue on the second
        buttons = [
            (('Resume', '▶️') if isPaused else ('Pause', '⏸️')) + (nextcord.ButtonStyle.secondary, MUSIC_PAUSE, 0),
            ('Restart', '⏮️', nextcord.ButtonStyle.secondary, MUSIC_RESTART, 0),
            ('Skip', '⏭️', nextcord.ButtonStyle.secondary, MUSIC_SKIP, 0),
            ('Stop', '⏹️', nextcord.ButtonStyle.danger, MUSIC_STOP, 0),
            ('Add song', '➕', nextcord.ButtonStyle.success, MUSIC_ADD, 1),
            ('Queue', '📜', nextcord.ButtonStyle.primary, MUSIC_QUEUE, 1),
            ('Shuffle', '🔀', nextcord.ButtonStyle.secondary, MUSIC_SHUFFLE, 1),
            ('Elevator', '🔁', toggle(musicState['isElevatorMode']), MUSIC_ELEVATOR, 1),
            ('Follow Spotify', '🎧', toggle(serverId in self.spotifySyncSessions), MUSIC_SPOTIFY, 1)]
        view = pagination.persistentView([])
        for label, emoji, style, action, row in buttons:
            button = pagination.persistentButton(label, emoji, style, f'{MUSIC_BUTTON_PREFIX}{action}')
            button.row = row
            view.add_item(button)
        return view

    def publicTarget(self, context):
        # a card's own buttons answer privately, so the now-playing card goes to their channel
        return context.channel if isinstance(context, pagination.CardReply) else context

    async def postCard(self, serverId, context, moveDown = False):
        musicState = self.musicStates[serverId]
        if moveDown and musicState['card'] is not None:
            try:
                await musicState['card'].delete()
            except nextcord.HTTPException:
                pass
        view = self.cardButtons(serverId)
        try:
            message = await self.publicTarget(context).send(embed = self.cardEmbed(serverId), view = view)
        finally:
            pagination.stopped(view)
        # kept as a plain message of the channel's: an interaction's own copy can only be edited for
        # 15 minutes, and a session routinely runs longer
        try:
            musicState['card'] = await utils.messageIn(self.client.get_guild(int(serverId)), message.channel.id, message.id) or message
        except nextcord.HTTPException:
            musicState['card'] = message

    async def updateCard(self, serverId, action = None):
        # the same card, edited as the music changes, rather than a new message for every song
        musicState = self.musicStates.get(serverId)
        # no card means the session ended, as a Stop does, and its last line belongs to no card
        if musicState is None or musicState['card'] is None:
            return
        if action is not None:
            musicState['lastAction'] = action
        view = self.cardButtons(serverId)
        try:
            await musicState['card'].edit(embed = self.cardEmbed(serverId), view = view)
        except nextcord.HTTPException as e:
            # deleted by someone, most likely. The next /music posts a new one.
            self.logger.info(f'GBot Music could not update its card in guild {serverId}: {e}')
            musicState['card'] = None
        finally:
            pagination.stopped(view)

    async def endCard(self, serverId, card):
        try:
            await card.edit(embed = presentation.brandEmbed(title = '⏹️ Music stopped', description = 'Use `/music` to play something.', feature = 'Music'), view = None)
        except nextcord.HTTPException as e:
            self.logger.info(f'GBot Music could not close its card in guild {serverId}: {e}')

    @commands.Cog.listener()
    async def on_interaction(self, interaction: nextcord.Interaction):
        parts = pagination.persistentParts(interaction, MUSIC_BUTTON_PREFIX)
        if parts is None:
            return
        try:
            await self.answerCardButton(interaction, parts[0])
        except Exception as e:
            await presentation.sendInteractionError(interaction, e)

    def listenerProblem(self, interaction):
        # who may press the card: anyone in GBot's voice channel, as the music is theirs
        musicState = self.musicStates.get(str(interaction.guild.id))
        voiceClient = musicState['voiceClient'] if musicState else None
        if voiceClient is None:
            return 'Nothing is playing. Use `/music` to play something.'
        voice = getattr(interaction.user, 'voice', None)
        if voice is None or voice.channel is None or voice.channel.id != voiceClient.channel.id:
            return f'Join 🔊 **{voiceClient.channel.name}** to control the music.'
        return None

    async def answerCardButton(self, interaction, action):
        serverId = str(interaction.guild.id)
        if action == MUSIC_ADD:
            # a form has to be the press's first answer, so its checks wait for the submit
            await self.addSongButton(interaction)
            return
        await interaction.response.defer(ephemeral = action in (MUSIC_QUEUE, MUSIC_SPOTIFY))
        await predicates.recheck(interaction, feature = 'toggle_music')
        problem = self.listenerProblem(interaction)
        if problem:
            await presentation.sendError(interaction, problem, feature = 'Music')
            return
        if action == MUSIC_QUEUE:
            await self.openQueue(interaction)
            return
        if action == MUSIC_SPOTIFY:
            await self.openSpotify(interaction)
            return
        reply = pagination.CardReply(interaction)
        musicState = self.musicStates[serverId]
        if action == MUSIC_PAUSE:
            if musicState['voiceClient'].is_paused():
                await self.commonResume(reply, interaction.user)
            else:
                await self.commonPause(reply, interaction.user)
        elif action == MUSIC_ELEVATOR:
            await self.commonElevator(reply)
        else:
            engine = {MUSIC_SKIP: self.commonSkip, MUSIC_STOP: self.commonStop, MUSIC_SHUFFLE: self.commonShuffle, MUSIC_RESTART: self.commonRestart}.get(action)
            if engine is None:
                return
            await engine(reply, interaction.user)
        await self.reportOnCard(interaction, serverId, reply)

    async def reportOnCard(self, interaction, serverId, reply):
        # a refusal is the presser's alone. Anything done shows on the card, with who did it, so
        # everyone listening can see why the music changed.
        notice = reply.notice or ''
        if notice.startswith('❌'):
            await presentation.sendError(interaction, notice[2:], feature = 'Music')
            return
        await self.updateCard(serverId, f'{notice} · {interaction.user.display_name}' if notice else None)

    async def addSongButton(self, interaction):
        async def submit(submitted, values):
            await predicates.recheck(submitted, feature = 'toggle_music')
            await self.commonPlay(submitted, submitted.user, utils.strParamToArgs(values[0]))
        await interaction.response.send_modal(pagination.Form('Add a song', [pagination.Field('Search or link', placeholder = 'halo 3 never forget', maxLength = 500)], submit))

    async def openQueue(self, interaction):
        # 📜 Queue: pick a song, then move it or take it out, as the old commands did
        serverId = str(interaction.guild.id)
        listed = []

        def entries():
            queue = self.musicStates[serverId]['queue']
            listed[:] = [entry[0] for entry in queue]
            lines = [f"**{number}.** {self.describeSongEmbed(song)}" for number, song in enumerate(listed, start = 1)]
            choices = [{'label': song['title'], 'description': self.describeLength(song), 'emoji': '🎵'} for song in listed]
            return lines, choices

        def positionOf(index):
            # the queue moves on as songs finish, so the song picked is found again rather than trusted
            queue = self.musicStates[serverId]['queue']
            return next((position for position, entry in enumerate(queue, start = 1) if entry[0] is listed[index]), None)

        def mover(target):
            async def move(picker, pressed, index):
                await pressed.response.defer()
                await predicates.recheck(pressed, feature = 'toggle_music')
                problem = self.listenerProblem(pressed)
                position = positionOf(index)
                reply = pagination.CardReply(pressed)
                if problem:
                    reply.notices.append(f'❌ {problem}')
                elif position is None:
                    reply.notices.append('❌ That song isn\'t in the queue any more.')
                elif target is None:
                    await self.commonRemove(reply, pressed.user, position)
                else:
                    queue = self.musicStates[serverId]['queue']
                    await self.commonMove(reply, pressed.user, position, max(1, min(len(queue), target(position))))
                picker.replace(*entries())
                await picker.redraw(pressed, reply.notice)
                if not reply.notice.startswith('❌'):
                    await self.updateCard(serverId)
            return move

        lines, choices = entries()
        source = pagination.DescriptionPageSource(lines, '📜 Queue', presentation.BRAND_COLOR, None, QUEUE_PER_PAGE, empty = 'Nothing is queued. Press ➕ **Add song** on the card.')
        actions = [
            pagination.Action('Up', '⬆️', nextcord.ButtonStyle.primary, mover(lambda position: position - 1), needsSelection = True),
            pagination.Action('Down', '⬇️', nextcord.ButtonStyle.primary, mover(lambda position: position + 1), needsSelection = True),
            pagination.Action('Play next', '⏩', nextcord.ButtonStyle.primary, mover(lambda position: 1), needsSelection = True),
            pagination.Action('Remove', '🗑️', nextcord.ButtonStyle.danger, mover(None), needsSelection = True)]
        await pagination.startPages(interaction, pagination.ListPicker(source, choices, actions, 'Choose a song…'), ephemeral = True)

    async def openSpotify(self, interaction):
        # 🎧 Follow Spotify: whose listening to play along with, from YouTube
        serverId = str(interaction.guild.id)
        view = pagination.OwnedView()
        view.ownerId = interaction.user.id
        async def done(pressed, reply):
            await pressed.edit_original_message(content = reply.notice, embed = None, view = None)
            view.stop()
            await self.updateCard(serverId)
        async def follow(pressed, member):
            await pressed.response.defer()
            await predicates.recheck(pressed, feature = 'toggle_music')
            reply = pagination.CardReply(pressed)
            await self.commonSpotify(reply, pressed.user, member)
            await done(pressed, reply)
        async def unfollow(pressed):
            await pressed.response.defer()
            reply = pagination.CardReply(pressed)
            session = self.spotifySyncSessions.pop(serverId, None)
            reply.notices.append(f"⚪ Spotify activity sync deactivated for {session['userMention']}." if session else '⚪ Nobody was being followed.')
            await done(pressed, reply)
        view.picker(nextcord.ui.UserSelect, follow, 'Pick a member to follow…', row = 0)
        view.button('🛑', unfollow, label = 'Stop following', row = 1)
        embed = presentation.brandEmbed(title = '🎧 Follow Spotify', description = 'Whose Spotify should GBot play along with? It finds each song they listen to on YouTube.', feature = 'Music')
        await view.send(interaction, True, embed = embed, view = view)
    #endregion

    async def commonSpotify(self, context, author, user):
        serverId = str(context.guild.id)
        authorMention = author.mention
        user = user or author
        userId = user.id
        userMention = user.mention
        if not await utils.isUserInThisGuildAndNotABot(user, context.guild):
            await presentation.sendError(context, f'Sorry {authorMention}, please specify a user in this guild.')
            return
        if serverId in self.spotifySyncSessions and userId == self.spotifySyncSessions[serverId]['userId']:
            self.spotifySyncSessions.pop(serverId)
            self.logger.info(f'GBot Music Spotify sync ended in guild {serverId} for user {userId}.')
            await context.send(f'⚪ Spotify activity sync deactivated for {userMention}.')
            return
        # a prefix command's converter returns a User, which has no activities, even for someone
        # listening right now. The guild's Member is the one that does.
        member = context.guild.get_member(userId)
        if member is not None:
            for activity in member.activities:
                if isinstance(activity, Spotify):
                    activityStr = f'{activity.title} by {activity.artist}'
                    self.spotifySyncSessions[serverId] = {
                        'userId': userId,
                        'userMention': userMention,
                        'lastActivity': activityStr,
                        # not the context itself: a slash command's interaction token expires after
                        # 15 minutes, and a session routinely outlives that. commonPlay only needs
                        # .guild and .send. The guild is kept separately because an uncached channel
                        # resolves to a PartialMessageable, which has no .guild.
                        'target': SimpleNamespace(guild = context.guild, send = context.channel.send, channel = context.channel),
                        'author': author
                    }
                    await context.send(f'🟢 Spotify activity sync activated for {userMention}.')
                    self.logger.info(f'GBot Music Spotify sync started in guild {serverId} for user {userId}.')
                    await self.commonPlay(context, author, [activityStr], False)
                    return
        await presentation.sendError(context, f'Sorry {authorMention}, there is currently no Spotify activity to sync with.')

    async def commonPlay(self, context, author, args, noReplyYet = True):
        if author.voice is None:
            await presentation.sendError(context, 'Please connect to a voice channel.')
            return
        if isinstance(context, nextcord.Interaction) and noReplyYet:
            # with_message: a form's submit would otherwise only edit the card it came from
            await context.response.defer(with_message = True)
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
                await presentation.sendError(context, 'Could not load that link. It may be private, age-restricted, region-locked, or unavailable.')
            else:
                await presentation.sendError(context, 'Could not get that song. Try using the share button to get its URL.')
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
                await presentation.sendError(context, f'Nothing in that playlist could be played \u2014 every entry was unavailable or longer than {GBotPropertiesManager.MUSIC_MAX_DURATION_MINUTES} minutes.{note}')
                return
        else:
            song = self.songFromInfo(songInfo)
            if song is None:
                await presentation.sendError(context, 'Could not determine the length of that song.')
                return
            # livestreams have no duration to limit — the cap is meaningless for something with
            # no end, and /skip is how you leave one
            if not song['isLive'] and (song['duration'] / 60) >= GBotPropertiesManager.MUSIC_MAX_DURATION_MINUTES:
                await presentation.sendError(context, f'Please play songs shorter than {GBotPropertiesManager.MUSIC_MAX_DURATION_MINUTES} minutes.')
                return
            songs = [song]

        # searching off the event loop (A-23) put an await between reading isPlaying and
        # acting on it, so two /play commands in one guild could both see "not playing",
        # both start playback, and the second raise "Already playing audio"
        async with self.musicStates[serverId]['playLock']:
            musicState = self.musicStates[serverId]
            if musicState['isPlaying'] and musicState['isElevatorMode']:
                await presentation.sendError(context, "Please disable elevator mode to add songs to the queue.")
                return
            room = GBotPropertiesManager.MUSIC_MAX_QUEUE_SONGS - len(musicState['queue'])
            if room <= 0:
                await presentation.sendError(context, f'The queue is full, at {GBotPropertiesManager.MUSIC_MAX_QUEUE_SONGS} songs. Please wait for some to finish.')
                return
            queueFullNote = len(songs) > room
            songs = songs[:room]
            wasIdle = not musicState['isPlaying']
            for song in songs:
                # shown on the card while it plays, and kept through elevator mode's loops
                song['addedBy'] = author.mention
                musicState['queue'].append([song, voiceChannel])

            if isPlaylist:
                # Three separate facts, and they have to stay separate. "Added 42 songs... Playlist
                # truncated to the first 50" read as a contradiction, because 42 is how many
                # survived filtering while 50 is how many were looked at — a podcast playlist hits
                # both at once (episodes over the length cap, and 700 entries behind the cap).
                # Keyed off isPlaylist rather than len(songs) > 1, so a playlist yielding exactly
                # one playable song still reports what happened instead of silently rendering as an
                # ordinary single-song play.
                parts = [f'➕ Added {len(songs)} song{"" if len(songs) == 1 else "s"} to the queue.']
                if skipped:
                    parts.append(f'Skipped {skipped} that could not be played or ran over {GBotPropertiesManager.MUSIC_MAX_DURATION_MINUTES} minutes.')
                if truncated:
                    parts.append(f'Only the first {GBotPropertiesManager.MUSIC_MAX_PLAYLIST_SONGS} entries of the playlist were checked.')
                if queueFullNote:
                    parts.append(f'The queue is now full, at {GBotPropertiesManager.MUSIC_MAX_QUEUE_SONGS} songs.')
                message = ' '.join(parts)
            elif wasIdle:
                # the now-playing card is the reply, once the song has really started
                message = None
            else:
                # suppressed link: queueing five songs would otherwise post five full-size cards,
                # and a queued song is not the one anyone wants to press play on
                message = f'➕ Added to the queue (#{len(musicState["queue"])}):\n{self.describeSongText(songs[0], suppressEmbed = True)}'
            # the bot stays with whoever is listening, so a song queued from elsewhere plays over there
            currentVoiceClient = musicState['voiceClient']
            if not wasIdle and currentVoiceClient is not None and currentVoiceClient.channel.id != voiceChannel.id:
                message += f'\nIt will play in {currentVoiceClient.channel.mention}, where GBot is now.'
            if message is not None:
                await context.send(message)

            if wasIdle:
                await self.channelSync(serverId)
                await self.playMusic(serverId)
                if musicState['isPlaying']:
                    # an idle session still in voice has a card already, which goes rather than freezing
                    await self.postCard(serverId, context, moveDown = True)
                elif message is None:
                    await presentation.sendError(context, 'Could not play that song. Please try another.')
            else:
                await self.updateCard(serverId)

    async def commonElevator(self, context):
        serverId = str(context.guild.id)
        currentElevatorMode = self.musicStates[serverId]['isElevatorMode']
        newElevatorMode = not currentElevatorMode
        lastPlayedSong = self.musicStates[serverId]['lastPlayed']['song']
        if newElevatorMode and lastPlayedSong is not None and lastPlayedSong['isLive']:
            # repeating something with no end is meaningless — a livestream already never stops,
            # and the repeat would only ever fire if the stream itself died
            await presentation.sendError(context, 'Elevator mode cannot repeat a livestream.')
            return
        self.musicStates[serverId]['isElevatorMode'] = newElevatorMode
        if newElevatorMode:
            # if syncing with Spotify, stop to enable elevator mode
            if serverId in self.spotifySyncSessions:
                userId = self.spotifySyncSessions[serverId]['userId']
                userMention = self.spotifySyncSessions[serverId]['userMention']
                self.logger.info(f'GBot Music Spotify sync ended in guild {serverId} for user {userId}.')
                await context.send(f'⚪ Spotify activity sync deactivated for {userMention}.')
                self.spotifySyncSessions.pop(serverId)
            elevatorStr = '🔁 Elevator mode enabled.'
        else:
            elevatorStr = '🔁 Elevator mode disabled.'
        await context.send(elevatorStr)

    async def commonSkip(self, context, author):
        serverId = str(context.guild.id)
        if self.musicStates[serverId]['voiceClient'] != None:
            if self.musicStates[serverId]['isElevatorMode'] and not self.musicStates[serverId]['isPlaying']:
                if not self.musicStates[serverId]['queue']:
                    # the queue is the loop's only source, so there is nothing to restart from
                    await presentation.sendError(context, f'Sorry {author.mention}, there is currently nothing playing.')
                    return
                # playMusic awaits the codec probe (C-4), so this restart has to be serialized with
                # commonPlay's and onSongFinished's the same way they are with each other
                async with self.musicStates[serverId]['playLock']:
                    await self.channelSync(serverId)
                    await self.playMusic(serverId)
            else:
                self.musicStates[serverId]['voiceClient'].stop()
            await context.send(f'⏭️ Skipped.')
        else:
            await presentation.sendError(context, f'Sorry {author.mention}, there is currently nothing playing.')

    async def commonStop(self, context, author):
        serverId = str(context.guild.id)
        if self.musicStates[serverId]['voiceClient'] != None:
            await self.disconnectAndClearQueue(serverId)
            await context.send(f'⏹️ Stopped.')
        else:
            await presentation.sendError(context, f'Sorry {author.mention}, there is currently nothing playing.')

    async def commonPause(self, context, author):
        serverId = str(context.guild.id)
        if self.musicStates[serverId]['voiceClient'] != None and self.musicStates[serverId]['voiceClient'].is_playing():
            self.musicStates[serverId]['voiceClient'].pause()
            self.musicStates[serverId]['playback']['pausedAt'] = self.monotonicNow()
            await context.send(f'⏸️ Paused.')
        else:
            await presentation.sendError(context, f'Sorry {author.mention}, there is currently nothing playing.')

    async def commonResume(self, context, author):
        serverId = str(context.guild.id)
        if self.musicStates[serverId]['voiceClient'] != None and self.musicStates[serverId]['voiceClient'].is_paused():
            self.musicStates[serverId]['voiceClient'].resume()
            playback = self.musicStates[serverId]['playback']
            playback['heldSeconds'] += self.monotonicNow() - playback['pausedAt']
            playback['pausedAt'] = None
            await context.send(f'▶️ Resumed.')
        else:
            await presentation.sendError(context, f'Sorry {author.mention}, there is currently nothing paused.')

    # These three change the queue with no await between reading and writing it, so they cannot
    # interleave with playMusic's queue walk and need no playLock. Positions match the queue card.
    async def commonRemove(self, context, author, position):
        queue = self.musicStates[str(context.guild.id)]['queue']
        refusal = self.describeBadQueuePosition(author, queue, position)
        if refusal is not None:
            await presentation.sendError(context, refusal)
            return
        song, _ = queue.pop(position - 1)
        await context.send(f'🗑️ Removed from the queue:\n{self.describeSongText(song, suppressEmbed = True)}')

    async def commonMove(self, context, author, fromPosition, toPosition):
        queue = self.musicStates[str(context.guild.id)]['queue']
        refusal = self.describeBadQueuePosition(author, queue, fromPosition, toPosition)
        if refusal is not None:
            await presentation.sendError(context, refusal)
            return
        entry = queue.pop(fromPosition - 1)
        queue.insert(toPosition - 1, entry)
        await context.send(f'↕️ Moved to position {toPosition} in the queue:\n{self.describeSongText(entry[0], suppressEmbed = True)}')

    async def commonShuffle(self, context, author):
        queue = self.musicStates[str(context.guild.id)]['queue']
        if not queue:
            await presentation.sendError(context, f'Sorry {author.mention}, the queue is empty.')
            return
        random.shuffle(queue)
        await context.send('🔀 Shuffled the queue.')

    async def commonRestart(self, context, author):
        musicState = self.musicStates[str(context.guild.id)]
        voiceClient = musicState['voiceClient']
        song = musicState['lastPlayed']['song']
        if voiceClient is None or song is None or not (voiceClient.is_playing() or voiceClient.is_paused()):
            await presentation.sendError(context, f'Sorry {author.mention}, there is currently nothing playing.')
            return
        if song['isLive']:
            await presentation.sendError(context, f'Sorry {author.mention}, a livestream cannot be restarted.')
            return
        # back to the head of the queue, then end the song so the ordinary after callback plays it
        # again, with a fresh stream URL and a fresh progress clock. The flag stops that callback
        # also treating it as a finished song in elevator mode, which would loop it twice.
        musicState['queue'].insert(0, [song, musicState['lastPlayed']['channel']])
        musicState['isRestarting'] = True
        voiceClient.stop()
        await context.send('⏮️ Restarted.')


    def describeBadQueuePosition(self, author, queue, *positions):
        if not queue:
            return f'Sorry {author.mention}, the queue is empty.'
        if any(position < 1 or position > len(queue) for position in positions):
            return f'Sorry {author.mention}, please choose a position between 1 and {len(queue)}.'
        return None

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

    def monotonicNow(self):
        # the seam tests patch: patching time.monotonic itself under IsolatedAsyncioTestCase would
        # also patch the clock the event loop runs on
        return time.monotonic()

    def elapsedSeconds(self, playback):
        # while paused, time stops at the moment of the pause
        now = playback['pausedAt'] if playback['pausedAt'] is not None else self.monotonicNow()
        return max(0, now - playback['startedAt'] - playback['heldSeconds'])

    def describeProgress(self, song, elapsed):
        # a snapshot at send time: the embed does not update itself
        if song['isLive']:
            # there is no total to measure a stream against
            return f'`{self.formatDuration(elapsed)}`'
        duration = song['duration']
        # the clock can run a moment past the end while the next song resolves
        elapsed = min(elapsed, duration)
        width = 11
        filled = int(elapsed / max(duration, 1) * width)
        bar = '▬' * filled + '🔘' + '▬' * (width - filled)
        return f'`{bar}` `{self.formatDuration(elapsed)} / {self.formatDuration(duration)}`'

    def describeNowPlaying(self, musicState):
        song = musicState['lastPlayed']['song']
        addedBy = f"\nAdded by {song['addedBy']}" if song.get('addedBy') else ''
        return f"{self.describeSongEmbed(song)}\n{self.describeProgress(song, self.elapsedSeconds(musicState['playback']))}{addedBy}"

    async def channelSync(self, serverId):
        musicState = self.musicStates[serverId]
        queue = musicState['queue']
        if len(queue) == 0:
            return

        # the channel to be in is the one whose audio playMusic is about to play: the channel the
        # queue head was asked from. Elevator mode needs no case of its own, because a looping song
        # goes back into the queue carrying the channel it was playing in.
        channel = queue[0][1]

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

        # Walk the queue until something resolves. One unplayable entry — deleted, private,
        # region-locked, or a livestream whose manifest host is unreachable — must not strand
        # everything queued behind it. Before C-PR8 the queue path never resolved here at all,
        # so this failure could not happen; queueing a 50-song playlist makes it likely. The queue
        # is the only source: elevator mode loops by putting finished songs back (onSongFinished),
        # so a song that fails to resolve here leaves the loop rather than being retried forever.
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
        self.logger.info(f"GBot Music playing next song '{song['title']}' in channel {channel} in guild {serverId}.")

        musicState['playback'] = {**self.newPlaybackClock(), 'startedAt': self.monotonicNow()}

        # A-20: after runs on ffmpeg's audio thread. Returning a coroutine hands it back to the
        # event loop (nextcord submits it with run_coroutine_threadsafe), so musicStates is only
        # ever mutated there.
        voiceClient.play(source, after = lambda error: self.onSongFinished(serverId, error))

        # replaced wholesale rather than field by field, so the shape can't drift from newLastPlayed
        musicState['lastPlayed'] = {'song': song, 'channel': channel}
        await self.updateCard(serverId)

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
            # Elevator mode is a loop over the queue: a song that ends goes to the back, so one
            # queued song repeats and several cycle in order. It belongs here, because this is the
            # only place a song has actually ended: playMusic is also called with nothing finished.
            # disconnectAndClearQueue clears both of these, so the callback a ⏹️ Stop triggers
            # puts nothing back. A livestream never goes back, or it could hold the loop forever.
            lastPlayed = musicState['lastPlayed']
            if musicState['isRestarting']:
                # commonRestart already put this song back, at the head
                musicState['isRestarting'] = False
            elif musicState['isElevatorMode'] and lastPlayed['song'] is not None and not lastPlayed['song']['isLive']:
                musicState['queue'].append([lastPlayed['song'], lastPlayed['channel']])
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
            self.musicStates[serverId]['playback'] = self.newPlaybackClock()
            self.musicStates[serverId]['isRestarting'] = False
            card = self.musicStates[serverId]['card']
            self.musicStates[serverId]['card'] = None
            self.musicStates[serverId]['lastAction'] = None
            if card is not None:
                await self.endCard(serverId, card)
        if serverId in self.spotifySyncSessions:
            session = self.spotifySyncSessions.pop(serverId)
            # reached from ⏹️ Stop, the idle timeout, the empty-channel timeout and a kick, and
            # only the first has a caller watching. Sent last, because a channel that cannot be
            # posted to must not get in the way of the teardown.
            self.logger.info(f"GBot Music Spotify sync ended in guild {serverId} for user {session['userId']}.")
            try:
                await session['target'].send(f"⚪ Spotify activity sync deactivated for {session['userMention']}.")
            except Exception as e:
                self.logger.error(f'GBot Music could not announce the end of the Spotify sync in guild {serverId}: {e}')

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
            # 15-20 lines per song. Its warnings and errors are the part worth seeing, and they stay.
            self.logger.debug(msg)
        def warning(self, msg):
            self.logger.warning(msg)
        def error(self, msg):
            self.logger.error(msg)

def setup(client: commands.Bot):
    client.add_cog(Music(client))