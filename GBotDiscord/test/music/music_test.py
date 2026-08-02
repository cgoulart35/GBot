#region IMPORTS
import asyncio
import threading
import unittest
from unittest.mock import MagicMock, Mock, AsyncMock, patch
import nextcord
from nextcord import Spotify
from nextcord.ext import commands
from nextcord.ext.commands.context import Context

from GBotDiscord.src import utils
from GBotDiscord.src.config import config_queries
from GBotDiscord.src.music.music_cog import Music
from GBotDiscord.src.properties import GBotPropertiesManager
#endregion

# to run this test suite:
#   - execute the following command from the GBot directory: python -m unittest GBotDiscord/test/music/music_test.py
#   - or use the "Python: Current File" run configuration to run music_test.py
#   - or use the "Python: Current File" run configuration to run tests.py to run all test suites
class TestMusic(unittest.IsolatedAsyncioTestCase):

    @classmethod
    def setUpClass(self):
        print('\nExecuting music unit tests...\n')

    @classmethod
    def tearDownClass(self):
        print('\n\nCompleted music unit tests.\n')

    def setUp(self):
        GBotPropertiesManager.MUSIC_TIMEOUT_SECONDS = 5
        GBotPropertiesManager.MUSIC_MAX_DURATION_MINUTES = 3
        GBotPropertiesManager.MUSIC_MAX_PLAYLIST_SONGS = 3

        self.serverId = '99999'

        self.author = Mock()
        self.author.id = 54321
        self.author.name = "author name"
        self.author.mention = "<@!54321>"
        self.author.bot = False
        self.author.send = AsyncMock()
        self.author.activities = []
        self.author.voice = None

        self.voiceChannel = Mock()
        self.voiceChannel.id = 11111
        self.voiceChannel.connect = AsyncMock()
        # someone is listening by default; the empty-room tests override this
        self.voiceChannel.members = [self.author]

        self.textChannel = Mock()
        self.textChannel.id = 88888
        self.textChannel.send = AsyncMock()

        self.guild: nextcord.Guild = Mock()
        self.guild.id = int(self.serverId)
        self.guild.name = "guild name"
        self.guild.get_member = MagicMock(return_value = self.author)

        self.ctx: Context = Mock(spec = Context)
        self.ctx.guild = self.guild
        self.ctx.author = self.author
        self.ctx.channel = self.textChannel
        self.ctx.send = AsyncMock()

        self.interaction: nextcord.Interaction = Mock(spec = nextcord.Interaction)
        self.interaction.guild = self.guild
        self.interaction.user = self.author
        self.interaction.channel = self.textChannel
        self.interaction.send = AsyncMock()
        self.interaction.response = Mock()
        self.interaction.response.defer = AsyncMock()

        self.client: nextcord.Client = commands.Bot()

        self.music: Music = Music(self.client)

    def _make_voice_client(self, is_playing = False, is_paused = False, is_connected = True, channel = None):
        vc = Mock()
        vc.channel = channel if channel is not None else self.voiceChannel
        vc.is_playing = MagicMock(return_value = is_playing)
        vc.is_paused = MagicMock(return_value = is_paused)
        vc.is_connected = MagicMock(return_value = is_connected)
        vc.disconnect = AsyncMock()
        vc.move_to = AsyncMock()
        vc.stop = MagicMock()
        vc.pause = MagicMock()
        vc.resume = MagicMock()
        vc.play = MagicMock()
        return vc

    def _patch_audio_source(self, codec = 'opus', bitrate = 512):
        # FFmpegOpusAudio.probe is a coroutine; the constructor is not. 512 is what nextcord's
        # native probe always reports (it computes max(round(kbps), 512)) — see buildAudioSource.
        mockAudio = MagicMock()
        mockAudio.probe = AsyncMock(return_value = (codec, bitrate))
        return patch('GBotDiscord.src.music.music_cog.nextcord.FFmpegOpusAudio', mockAudio)

    def _song(self, title = 'T', webpageUrl = 'https://youtu.be/abc', duration = 60, isLive = False, searchString = None):
        # the exact shape songFromInfo produces: no stream URL, ever (C-6/C-14) — playMusic
        # resolves one from searchString at the moment the song starts
        return {
            'title': title,
            'webpageUrl': webpageUrl,
            'duration': duration,
            'isLive': isLive,
            'searchString': searchString if searchString is not None else webpageUrl
        }

    def _seed_state(self, serverId = None, isPlaying = False, isElevatorMode = False, voiceClient = None, queue = None, lastPlayed = None, inactiveSeconds = 0, emptySeconds = 0):
        serverId = serverId if serverId is not None else self.serverId
        self.music.musicStates[serverId] = {
            'isPlaying': isPlaying,
            'isElevatorMode': isElevatorMode,
            'voiceClient': voiceClient,
            'queue': queue if queue is not None else [],
            'lastPlayed': lastPlayed if lastPlayed is not None else {'song': None, 'channel': None},
            'inactiveSeconds': inactiveSeconds,
            'emptySeconds': emptySeconds,
            'playLock': asyncio.Lock()
        }

    #region on_guild_join / on_guild_remove
    async def test_on_guild_join_adds_state(self):
        otherGuild = Mock()
        otherGuild.id = 12121
        otherGuild.name = "other"
        await self.music.on_guild_join(otherGuild)
        state = self.music.musicStates[str(otherGuild.id)]
        self.assertFalse(state['isPlaying'])
        self.assertFalse(state['isElevatorMode'])
        self.assertIsNone(state['voiceClient'])
        self.assertEqual(state['queue'], [])
        self.assertEqual(state['inactiveSeconds'], 0)

    async def test_on_guild_remove_pops_state(self):
        self._seed_state()
        await self.music.on_guild_remove(self.guild)
        self.assertNotIn(self.serverId, self.music.musicStates)

    # A-11: on_guild_remove cleared musicStates but left the spotify sync session behind, so
    # spotify_sync kept polling a guild the bot had left — an AttributeError every second forever.
    async def test_on_guild_remove_pops_spotify_sync_session(self):
        self._seed_state()
        self.music.spotifySyncSessions[self.serverId] = {
            'userId': self.author.id,
            'userMention': self.author.mention,
            'lastActivity': "Song by Artist",
            'context': self.ctx,
            'author': self.author
        }
        await self.music.on_guild_remove(self.guild)
        self.assertNotIn(self.serverId, self.music.spotifySyncSessions)

    # A-14: pop() had no default, so leaving a guild that filterGuildsForInstance never
    # initialized raised KeyError inside the listener.
    async def test_on_guild_remove_uninitialized_guild_does_not_raise(self):
        await self.music.on_guild_remove(self.guild)
        self.assertNotIn(self.serverId, self.music.musicStates)
    #endregion

    #region on_ready
    async def test_on_ready_initializes_state_when_empty(self):
        utils.filterGuildsForInstance = MagicMock(return_value = {self.serverId: {}})
        config_queries.getAllServers = MagicMock(return_value = {self.serverId: {}})
        self.music.music_timeout.start = MagicMock()
        self.music.spotify_sync.start = MagicMock()
        await self.music.on_ready()
        self.assertIn(self.serverId, self.music.musicStates)
        self.music.music_timeout.start.assert_called_once()
        self.music.spotify_sync.start.assert_called_once()

    async def test_on_ready_skips_init_when_state_exists(self):
        self._seed_state(isPlaying = True)
        utils.filterGuildsForInstance = MagicMock()
        self.music.music_timeout.start = MagicMock()
        self.music.spotify_sync.start = MagicMock()
        await self.music.on_ready()
        utils.filterGuildsForInstance.assert_not_called()
        self.assertTrue(self.music.musicStates[self.serverId]['isPlaying'])

    async def test_on_ready_tasks_already_running(self):
        self._seed_state()
        self.music.music_timeout.start = MagicMock(side_effect = RuntimeError("running"))
        self.music.spotify_sync.start = MagicMock(side_effect = RuntimeError("running"))
        # both RuntimeErrors must be swallowed by the cog
        await self.music.on_ready()
        self.music.music_timeout.start.assert_called_once()
        self.music.spotify_sync.start.assert_called_once()
    #endregion

    #region on_voice_state_update
    # C-12: the cog had no voice state listener at all, so it never learned it had been
    # disconnected, moved, or left alone — recovery depended entirely on the 1 s music_timeout
    # poll, which is why A-18's stale voiceClient state persisted instead of self-healing.
    def _make_member(self, memberId, isBot = False):
        member = Mock()
        member.id = memberId
        member.bot = isBot
        member.guild = self.guild
        return member

    def _make_voice_state(self, channel = None):
        state = Mock()
        state.channel = channel
        return state

    def _make_bot_client(self, botId = 77777):
        self.music.client = Mock()
        self.music.client.user.id = botId
        return self._make_member(botId, isBot = True)

    async def test_on_voice_state_update_ignores_guilds_without_music_state(self):
        member = self._make_bot_client()
        self.music.disconnectAndClearQueue = AsyncMock()
        await self.music.on_voice_state_update(member, self._make_voice_state(self.voiceChannel), self._make_voice_state())
        self.music.disconnectAndClearQueue.assert_not_called()

    async def test_on_voice_state_update_ignores_guilds_without_a_voice_client(self):
        member = self._make_bot_client()
        self._seed_state(voiceClient = None)
        self.music.disconnectAndClearQueue = AsyncMock()
        await self.music.on_voice_state_update(member, self._make_voice_state(self.voiceChannel), self._make_voice_state())
        self.music.disconnectAndClearQueue.assert_not_called()

    async def test_on_voice_state_update_bot_disconnected_clears_state(self):
        member = self._make_bot_client()
        vc = self._make_voice_client()
        self._seed_state(voiceClient = vc, isPlaying = True, queue = [[{'source': 'u', 'title': 'T'}, self.voiceChannel, 'q']])
        await self.music.on_voice_state_update(member, self._make_voice_state(self.voiceChannel), self._make_voice_state())
        state = self.music.musicStates[self.serverId]
        self.assertIsNone(state['voiceClient'])
        self.assertEqual(state['queue'], [])
        self.assertFalse(state['isPlaying'])

    async def test_on_voice_state_update_bot_moved_follows_the_new_channel(self):
        member = self._make_bot_client()
        newChannel = Mock()
        newChannel.id = 33333
        vc = self._make_voice_client()
        self._seed_state(voiceClient = vc, lastPlayed = {'song': self._song('T', searchString = 's'), 'channel': self.voiceChannel})
        await self.music.on_voice_state_update(member, self._make_voice_state(self.voiceChannel), self._make_voice_state(newChannel))
        self.assertEqual(self.music.musicStates[self.serverId]['lastPlayed']['channel'], newChannel)

    async def test_on_voice_state_update_bot_connecting_is_not_treated_as_a_move(self):
        member = self._make_bot_client()
        vc = self._make_voice_client()
        self._seed_state(voiceClient = vc, lastPlayed = {'song': self._song('T', searchString = 's'), 'channel': None})
        # before.channel is None on a fresh connect; playMusic owns lastPlayed from there
        await self.music.on_voice_state_update(member, self._make_voice_state(), self._make_voice_state(self.voiceChannel))
        self.assertIsNone(self.music.musicStates[self.serverId]['lastPlayed']['channel'])

    # a listener leaving is NOT actionable here: an empty channel is handled by music_timeout on
    # a grace period, so that elevator mode keeps playing 24/7 and a network blip cannot end a
    # session. See test_music_timeout_empty_channel_* below.
    async def test_on_voice_state_update_ignores_other_members(self):
        self._make_bot_client()
        listener = self._make_member(54321)
        botMember = self._make_member(77777, isBot = True)
        self.voiceChannel.members = [botMember]
        vc = self._make_voice_client(channel = self.voiceChannel)
        self._seed_state(voiceClient = vc, isPlaying = True)
        await self.music.on_voice_state_update(listener, self._make_voice_state(self.voiceChannel), self._make_voice_state())
        vc.disconnect.assert_not_called()
        self.assertIsNotNone(self.music.musicStates[self.serverId]['voiceClient'])
    #endregion

    #region music_timeout
    async def test_music_timeout_no_voice_client_resets_seconds(self):
        self._seed_state(inactiveSeconds = 99)
        await self.music.music_timeout.coro(self.music)
        self.assertEqual(self.music.musicStates[self.serverId]['inactiveSeconds'], 0)

    async def test_music_timeout_voice_client_playing_resets(self):
        vc = self._make_voice_client(is_playing = True)
        self._seed_state(voiceClient = vc, inactiveSeconds = 4)
        await self.music.music_timeout.coro(self.music)
        self.assertEqual(self.music.musicStates[self.serverId]['inactiveSeconds'], 0)

    async def test_music_timeout_voice_client_idle_increments(self):
        vc = self._make_voice_client(is_playing = False)
        self._seed_state(voiceClient = vc, inactiveSeconds = 1)
        await self.music.music_timeout.coro(self.music)
        self.assertEqual(self.music.musicStates[self.serverId]['inactiveSeconds'], 2)

    async def test_music_timeout_voice_client_idle_disconnects_at_timeout(self):
        vc = self._make_voice_client(is_playing = False)
        self._seed_state(voiceClient = vc, inactiveSeconds = GBotPropertiesManager.MUSIC_TIMEOUT_SECONDS - 1)
        await self.music.music_timeout.coro(self.music)
        # disconnect was called and counter reset
        vc.disconnect.assert_called_once()
        self.assertIsNone(self.music.musicStates[self.serverId]['voiceClient'])
        self.assertEqual(self.music.musicStates[self.serverId]['inactiveSeconds'], 0)

    def _emptyChannel(self):
        # only the bot is left in the channel
        botMember = Mock()
        botMember.bot = True
        self.voiceChannel.members = [botMember]
        return self.voiceChannel

    async def test_music_timeout_empty_channel_increments(self):
        vc = self._make_voice_client(is_playing = True, channel = self._emptyChannel())
        self._seed_state(voiceClient = vc, emptySeconds = 1)
        await self.music.music_timeout.coro(self.music)
        self.assertEqual(self.music.musicStates[self.serverId]['emptySeconds'], 2)

    async def test_music_timeout_empty_channel_disconnects_at_timeout(self):
        vc = self._make_voice_client(is_playing = True, channel = self._emptyChannel())
        self._seed_state(voiceClient = vc, emptySeconds = GBotPropertiesManager.MUSIC_TIMEOUT_SECONDS - 1)
        await self.music.music_timeout.coro(self.music)
        vc.disconnect.assert_called_once()
        self.assertIsNone(self.music.musicStates[self.serverId]['voiceClient'])
        self.assertEqual(self.music.musicStates[self.serverId]['emptySeconds'], 0)

    # elevator mode is deliberately 24/7 — it plays to an empty channel so that whoever joins
    # next hears it. It must never accrue empty seconds, no matter how long the room stays empty.
    async def test_music_timeout_elevator_mode_never_leaves_an_empty_channel(self):
        vc = self._make_voice_client(is_playing = True, channel = self._emptyChannel())
        self._seed_state(voiceClient = vc, isElevatorMode = True, emptySeconds = GBotPropertiesManager.MUSIC_TIMEOUT_SECONDS - 1)
        await self.music.music_timeout.coro(self.music)
        vc.disconnect.assert_not_called()
        self.assertEqual(self.music.musicStates[self.serverId]['emptySeconds'], 0)
        self.assertIsNotNone(self.music.musicStates[self.serverId]['voiceClient'])

    # a listener rejoining resets the count, so a network blip or a phone-to-desktop switch
    # cannot end the session
    async def test_music_timeout_listener_present_resets_empty_seconds(self):
        vc = self._make_voice_client(is_playing = True)
        self._seed_state(voiceClient = vc, emptySeconds = GBotPropertiesManager.MUSIC_TIMEOUT_SECONDS - 1)
        await self.music.music_timeout.coro(self.music)
        vc.disconnect.assert_not_called()
        self.assertEqual(self.music.musicStates[self.serverId]['emptySeconds'], 0)

    async def test_music_timeout_no_voice_client_resets_empty_seconds(self):
        self._seed_state(emptySeconds = 42)
        await self.music.music_timeout.coro(self.music)
        self.assertEqual(self.music.musicStates[self.serverId]['emptySeconds'], 0)

    async def test_music_timeout_handles_exception(self):
        # poison the state so the body raises; outer try/except must swallow
        self.music.musicStates[self.serverId] = {}
        await self.music.music_timeout.coro(self.music)

    # A-13: the loop iterated musicStates.items() directly while awaiting, so a guild removed
    # mid-tick raised "dictionary changed size during iteration" and silently lost the tick.
    async def test_music_timeout_survives_state_removed_mid_iteration(self):
        otherServerId = '11111'
        vc = self._make_voice_client(is_playing = False)
        self._seed_state(voiceClient = vc, inactiveSeconds = GBotPropertiesManager.MUSIC_TIMEOUT_SECONDS - 1)
        self._seed_state(serverId = otherServerId, inactiveSeconds = 7)

        # disconnecting the first guild removes the second guild's state, as on_guild_remove would
        async def disconnectAndRemoveOther(serverId):
            self.music.musicStates.pop(otherServerId)
            self.music.musicStates[serverId]['voiceClient'] = None
        self.music.disconnectAndClearQueue = AsyncMock(side_effect = disconnectAndRemoveOther)
        self.music.logger = MagicMock()

        await self.music.music_timeout.coro(self.music)
        self.music.logger.error.assert_not_called()
        self.assertNotIn(otherServerId, self.music.musicStates)
        self.assertEqual(self.music.musicStates[self.serverId]['inactiveSeconds'], 0)
    #endregion

    #region spotify_sync
    async def test_spotify_sync_no_sessions_noop(self):
        await self.music.spotify_sync.coro(self.music)

    async def test_spotify_sync_activity_unchanged(self):
        spotifyActivity = Mock(spec = Spotify)
        spotifyActivity.title = "Song"
        spotifyActivity.artist = "Artist"
        self.author.activities = [spotifyActivity]
        self.music.spotifySyncSessions[self.serverId] = {
            'userId': self.author.id,
            'userMention': self.author.mention,
            'lastActivity': "Song by Artist",
            'context': self.ctx,
            'author': self.author
        }
        self.music.commonPlay = AsyncMock()
        await self.music.spotify_sync.coro(self.music)
        # activity hasn't changed -> no new play triggered
        self.music.commonPlay.assert_not_called()

    async def test_spotify_sync_activity_changed_triggers_play(self):
        spotifyActivity = Mock(spec = Spotify)
        spotifyActivity.title = "NewSong"
        spotifyActivity.artist = "NewArtist"
        self.author.activities = [spotifyActivity]
        self.music.spotifySyncSessions[self.serverId] = {
            'userId': self.author.id,
            'userMention': self.author.mention,
            'lastActivity': "OldSong by OldArtist",
            'context': self.ctx,
            'author': self.author
        }
        self.music.commonPlay = AsyncMock()
        await self.music.spotify_sync.coro(self.music)
        # new activity recorded and play kicked off with the new title
        self.assertEqual(self.music.spotifySyncSessions[self.serverId]['lastActivity'], "NewSong by NewArtist")
        self.music.commonPlay.assert_called_once_with(self.ctx, self.author, ["NewSong by NewArtist"], False)

    async def test_spotify_sync_user_has_no_spotify_activity(self):
        # user.activities contains a non-Spotify activity (e.g., a Game)
        nonSpotifyActivity = Mock()
        self.author.activities = [nonSpotifyActivity]
        self.music.spotifySyncSessions[self.serverId] = {
            'userId': self.author.id,
            'userMention': self.author.mention,
            'lastActivity': "Old",
            'context': self.ctx,
            'author': self.author
        }
        self.music.commonPlay = AsyncMock()
        await self.music.spotify_sync.coro(self.music)
        self.music.commonPlay.assert_not_called()

    async def test_spotify_sync_handles_exception(self):
        # missing required keys causes a KeyError; outer try/except swallows
        self.music.spotifySyncSessions[self.serverId] = {}
        await self.music.spotify_sync.coro(self.music)

    # A-11: once the followed user was no longer resolvable, get_member returned None and the
    # next line raised AttributeError — every second, forever, logging on each tick.
    async def test_spotify_sync_ends_session_when_followed_user_is_gone(self):
        self.guild.get_member = MagicMock(return_value = None)
        self.music.spotifySyncSessions[self.serverId] = {
            'userId': self.author.id,
            'userMention': self.author.mention,
            'lastActivity': "Song by Artist",
            'context': self.ctx,
            'author': self.author
        }
        self.music.commonPlay = AsyncMock()
        self.music.logger = MagicMock()
        await self.music.spotify_sync.coro(self.music)
        self.assertNotIn(self.serverId, self.music.spotifySyncSessions)
        self.music.logger.error.assert_not_called()
        self.music.logger.info.assert_called_once()
        self.music.commonPlay.assert_not_called()

    # A-13: the loop iterated spotifySyncSessions.items() directly while awaiting commonPlay,
    # which can end another guild's session (disconnectAndClearQueue pops it).
    async def test_spotify_sync_survives_session_removed_mid_iteration(self):
        otherServerId = '11111'
        spotifyActivity = Mock(spec = Spotify)
        spotifyActivity.title = "NewSong"
        spotifyActivity.artist = "NewArtist"
        self.author.activities = [spotifyActivity]
        for serverId in (self.serverId, otherServerId):
            self.music.spotifySyncSessions[serverId] = {
                'userId': self.author.id,
                'userMention': self.author.mention,
                'lastActivity': "OldSong by OldArtist",
                'context': self.ctx,
                'author': self.author
            }

        async def playAndEndOtherSession(context, author, args, sendMessages):
            self.music.spotifySyncSessions.pop(otherServerId)
        self.music.commonPlay = AsyncMock(side_effect = playAndEndOtherSession)
        self.music.logger = MagicMock()

        await self.music.spotify_sync.coro(self.music)
        self.music.logger.error.assert_not_called()
        self.assertNotIn(otherServerId, self.music.spotifySyncSessions)
        self.music.commonPlay.assert_called_once()
    #endregion

    #region commonSpotify
    async def test_commonSpotify_user_not_in_guild(self):
        utils.isUserInThisGuildAndNotABot = AsyncMock(return_value = False)
        await self.music.commonSpotify(self.ctx, self.author, None)
        self.ctx.send.assert_called_once_with(f'Sorry {self.author.mention}, please specify a user in this guild.')

    async def test_commonSpotify_active_sync_for_same_user_stops(self):
        utils.isUserInThisGuildAndNotABot = AsyncMock(return_value = True)
        self.music.spotifySyncSessions[self.serverId] = {
            'userId': self.author.id,
            'userMention': self.author.mention,
            'lastActivity': "Song by Artist",
            'context': self.ctx,
            'author': self.author
        }
        await self.music.commonSpotify(self.ctx, self.author, None)
        self.assertNotIn(self.serverId, self.music.spotifySyncSessions)
        self.ctx.send.assert_called_with(f'Spotify activity sync deactivated for {self.author.mention}.')

    async def test_commonSpotify_no_spotify_activity(self):
        utils.isUserInThisGuildAndNotABot = AsyncMock(return_value = True)
        self.author.activities = []
        await self.music.commonSpotify(self.ctx, self.author, None)
        self.ctx.send.assert_called_with(f'Sorry {self.author.mention}, there is currently no Spotify activity to sync with.')

    async def test_commonSpotify_starts_sync_when_activity_found(self):
        utils.isUserInThisGuildAndNotABot = AsyncMock(return_value = True)
        spotifyActivity = Mock(spec = Spotify)
        spotifyActivity.title = "Song"
        spotifyActivity.artist = "Artist"
        self.author.activities = [spotifyActivity]
        self.music.commonPlay = AsyncMock()
        await self.music.commonSpotify(self.ctx, self.author, None)
        self.assertIn(self.serverId, self.music.spotifySyncSessions)
        self.assertEqual(self.music.spotifySyncSessions[self.serverId]['lastActivity'], "Song by Artist")
        self.music.commonPlay.assert_called_once()
        self.ctx.send.assert_any_call(f'Spotify activity sync activated for {self.author.mention}.')

    async def test_commonSpotify_uses_author_when_user_none(self):
        # explicit user None -> falls back to author
        utils.isUserInThisGuildAndNotABot = AsyncMock(return_value = True)
        self.author.activities = []
        await self.music.commonSpotify(self.ctx, self.author, None)
        # message should reference the author (since author is the user)
        self.ctx.send.assert_called_with(f'Sorry {self.author.mention}, there is currently no Spotify activity to sync with.')
    #endregion

    #region commonPlay
    async def test_commonPlay_not_in_voice_channel(self):
        self._seed_state()
        self.author.voice = None
        await self.music.commonPlay(self.ctx, self.author, ['test'])
        self.ctx.send.assert_called_once_with('Please connect to a voice channel.')

    async def test_commonPlay_interaction_defers_when_no_reply_yet(self):
        self._seed_state()
        voiceState = Mock()
        voiceState.channel = self.voiceChannel
        self.author.voice = voiceState
        self.music.searchYouTube = AsyncMock(return_value = None)
        await self.music.commonPlay(self.interaction, self.author, ['test'], True)
        self.interaction.response.defer.assert_called_once()

    async def test_commonPlay_no_search_results(self):
        self._seed_state()
        voiceState = Mock()
        voiceState.channel = self.voiceChannel
        self.author.voice = voiceState
        self.music.searchYouTube = AsyncMock(return_value = None)
        await self.music.commonPlay(self.ctx, self.author, ['test'])
        self.ctx.send.assert_called_with('Could not get the video sound. Try using share button to get video URL.')

    # "use the share button to get a URL" is nonsense advice when a link was already pasted and
    # that link is what failed. Both QA failures landed here: a private playlist (403) and a
    # livestream whose manifest host the network blocks.
    async def test_commonPlay_failed_url_does_not_advise_using_the_share_button(self):
        self._seed_state()
        voiceState = Mock()
        voiceState.channel = self.voiceChannel
        self.author.voice = voiceState
        self.music.searchYouTube = AsyncMock(return_value = None)
        await self.music.commonPlay(self.ctx, self.author, ['https://www.youtube.com/playlist?list=x'])
        self.ctx.send.assert_called_with('Could not load that link. It may be private, age-restricted, region-locked, or unavailable.')

    async def test_commonPlay_duration_too_long(self):
        self._seed_state()
        voiceState = Mock()
        voiceState.channel = self.voiceChannel
        self.author.voice = voiceState
        # 4 min duration vs 3 min cache timeout -> rejected
        self.music.searchYouTube = AsyncMock(return_value = {'title': 'T', 'url': 'http://u', 'duration': 240})
        await self.music.commonPlay(self.ctx, self.author, ['test'])
        self.ctx.send.assert_called_with(f'Please play sounds less than {GBotPropertiesManager.MUSIC_MAX_DURATION_MINUTES} minutes.')

    async def test_commonPlay_not_playing_starts(self):
        self._seed_state(isPlaying = False)
        voiceState = Mock()
        voiceState.channel = self.voiceChannel
        self.author.voice = voiceState
        self.music.searchYouTube = AsyncMock(return_value = {'title': 'T', 'url': 'http://u', 'duration': 60, 'webpage_url': 'https://youtu.be/abc'})
        self.music.channelSync = AsyncMock()
        self.music.playMusic = AsyncMock()
        await self.music.commonPlay(self.ctx, self.author, ['test'])
        self.assertEqual(len(self.music.musicStates[self.serverId]['queue']), 1)
        # the link is bare on purpose: that is what makes Discord render its own playable card
        self.ctx.send.assert_called_with('Playing sound:\nT (1:00)\nhttps://youtu.be/abc')
        self.music.channelSync.assert_called_once()
        self.music.playMusic.assert_awaited_once_with(self.serverId)

    async def test_commonPlay_already_playing_adds_to_queue(self):
        self._seed_state(isPlaying = True, isElevatorMode = False)
        voiceState = Mock()
        voiceState.channel = self.voiceChannel
        self.author.voice = voiceState
        self.music.searchYouTube = AsyncMock(return_value = {'title': 'T', 'url': 'http://u', 'duration': 60, 'webpage_url': 'https://youtu.be/abc'})
        await self.music.commonPlay(self.ctx, self.author, ['test'])
        self.assertEqual(len(self.music.musicStates[self.serverId]['queue']), 1)
        # <> suppresses the card here: queueing five songs should not post five full-size cards
        self.ctx.send.assert_called_with('Sound added to the queue (1):\nT (1:00)\n<https://youtu.be/abc>')

    # A-23's fix put an await (the threaded search) between reading isPlaying and acting on it,
    # so two /play commands in one guild can interleave. Without the per-guild lock both see
    # "not playing", both start playback, and the second raises "Already playing audio".
    async def test_commonPlay_concurrent_plays_start_playback_once(self):
        self._seed_state(isPlaying = False)
        voiceState = Mock()
        voiceState.channel = self.voiceChannel
        self.author.voice = voiceState

        async def searchOffTheLoop(searchString):
            await asyncio.sleep(0)
            return {'title': searchString, 'url': f'http://{searchString}', 'duration': 60, 'webpage_url': f'https://youtu.be/{searchString}'}
        self.music.searchYouTube = AsyncMock(side_effect = searchOffTheLoop)

        # connecting to voice yields too, which is where the second command used to slip in
        async def connectToVoice(serverId):
            await asyncio.sleep(0)
        self.music.channelSync = AsyncMock(side_effect = connectToVoice)

        async def startPlaying(serverId):
            self.music.musicStates[serverId]['isPlaying'] = True
        self.music.playMusic = AsyncMock(side_effect = startPlaying)

        await asyncio.gather(
            self.music.commonPlay(self.ctx, self.author, ['first']),
            self.music.commonPlay(self.ctx, self.author, ['second'])
        )
        self.music.playMusic.assert_awaited_once_with(self.serverId)
        self.ctx.send.assert_any_call('Playing sound:\nfirst (1:00)\nhttps://youtu.be/first')
        self.ctx.send.assert_any_call('Sound added to the queue (2):\nsecond (1:00)\n<https://youtu.be/second>')

    async def test_commonPlay_already_playing_in_elevator_rejects(self):
        self._seed_state(isPlaying = True, isElevatorMode = True)
        voiceState = Mock()
        voiceState.channel = self.voiceChannel
        self.author.voice = voiceState
        self.music.searchYouTube = AsyncMock(return_value = {'title': 'T', 'url': 'http://u', 'duration': 60})
        await self.music.commonPlay(self.ctx, self.author, ['test'])
        self.ctx.send.assert_called_with("Please disable elevator mode to add songs to the queue.")

    # C-10 originally refused playlists; C-PR8 queues them. Entries arrive flat (id/title/url,
    # no stream URL), which is what keeps a 200-song paste from being 200 network round trips.
    def _flat_entry(self, title, videoId, duration = 60):
        return {'_type': 'url', 'url': f'https://youtu.be/{videoId}', 'id': videoId, 'title': title, 'duration': duration}

    async def test_commonPlay_queues_a_playlist(self):
        self._seed_state(isPlaying = False)
        voiceState = Mock()
        voiceState.channel = self.voiceChannel
        self.author.voice = voiceState
        self.music.searchYouTube = AsyncMock(return_value = {
            '_type': 'playlist',
            'title': 'A list',
            'entries': [self._flat_entry('A', 'aaa'), self._flat_entry('B', 'bbb')]
        })
        self.music.channelSync = AsyncMock()
        self.music.playMusic = AsyncMock()
        await self.music.commonPlay(self.ctx, self.author, ['https://youtube.com/playlist?list=x'])
        self.ctx.send.assert_called_with('Added 2 songs to the queue.')
        queue = self.music.musicStates[self.serverId]['queue']
        self.assertEqual([entry[0]['title'] for entry in queue], ['A', 'B'])
        # each entry re-fetches its OWN video, not the playlist URL that was pasted
        self.assertEqual(queue[0][0]['searchString'], 'https://youtu.be/aaa')
        # idle when the playlist arrived, so playback starts
        self.music.playMusic.assert_awaited_once_with(self.serverId)

    async def test_commonPlay_truncates_a_playlist_over_the_cap(self):
        # setUp caps MUSIC_MAX_PLAYLIST_SONGS at 3; extractSongInfo lists one extra so "there were
        # more" is knowable without paging through thousands
        self._seed_state(isPlaying = True, isElevatorMode = False)
        voiceState = Mock()
        voiceState.channel = self.voiceChannel
        self.author.voice = voiceState
        self.music.searchYouTube = AsyncMock(return_value = {
            '_type': 'playlist',
            'entries': [self._flat_entry(f'S{i}', f'id{i}') for i in range(4)]
        })
        await self.music.commonPlay(self.ctx, self.author, ['https://youtube.com/playlist?list=x'])
        self.ctx.send.assert_called_with('Added 3 songs to the queue. Playlist truncated to the first 3.')
        self.assertEqual(len(self.music.musicStates[self.serverId]['queue']), 3)

    async def test_commonPlay_playlist_with_nothing_playable(self):
        self._seed_state()
        voiceState = Mock()
        voiceState.channel = self.voiceChannel
        self.author.voice = voiceState
        # 4 minutes vs the 3-minute cap, and one entry with no duration at all
        self.music.searchYouTube = AsyncMock(return_value = {
            '_type': 'playlist',
            'entries': [self._flat_entry('Long', 'aaa', 240), self._flat_entry('NoLength', 'bbb', None)]
        })
        await self.music.commonPlay(self.ctx, self.author, ['https://youtube.com/playlist?list=x'])
        self.ctx.send.assert_called_once_with('That playlist has nothing playable in it.')
        self.assertEqual(len(self.music.musicStates[self.serverId]['queue']), 0)

    async def test_songsFromPlaylist_skips_unusable_entries(self):
        info = {'entries': [
            None,                                             # yt-dlp yields None for a deleted video
            self._flat_entry('Fine', 'aaa'),
            self._flat_entry('TooLong', 'bbb', 240),
            {'_type': 'url', 'title': 'NoUrl', 'duration': 60} # nothing to re-fetch it by
        ]}
        songs, _truncated = self.music.songsFromPlaylist(info)
        # truncation is covered separately; this is purely about which entries survive filtering
        self.assertEqual([song['title'] for song in songs], ['Fine'])

    # a deleted video (yt-dlp yields None) inside the fetched window must not mask a real
    # truncation: extractSongInfo fetches cap + 1, so it is the RAW count that says "there were
    # more". Filtering first pulled it back to exactly cap and swallowed the notice.
    async def test_songsFromPlaylist_truncation_survives_a_deleted_entry(self):
        # setUp caps at 3, so 4 raw entries means the playlist had more than the cap
        info = {'entries': [self._flat_entry('A', 'a'), None, self._flat_entry('B', 'b'), self._flat_entry('C', 'c')]}
        songs, truncated = self.music.songsFromPlaylist(info)
        self.assertTrue(truncated)
        self.assertEqual([song['title'] for song in songs], ['A', 'B', 'C'])

    # a livestream inside a playlist has no duration but is still playable
    async def test_songsFromPlaylist_keeps_livestream_entries(self):
        info = {'entries': [{'_type': 'url', 'url': 'https://youtu.be/live', 'title': 'Live', 'duration': None, 'is_live': True}]}
        songs, _truncated = self.music.songsFromPlaylist(info)
        self.assertEqual(len(songs), 1)
        self.assertTrue(songs[0]['isLive'])

    # C-10 originally refused these; C-PR8 plays them. A livestream has no duration, so the
    # length cap is skipped rather than dividing None by 60 (the original TypeError).
    async def test_commonPlay_plays_a_livestream(self):
        self._seed_state(isPlaying = False)
        voiceState = Mock()
        voiceState.channel = self.voiceChannel
        self.author.voice = voiceState
        self.music.searchYouTube = AsyncMock(return_value = {'title': 'lofi 24/7', 'url': 'http://u', 'duration': None, 'is_live': True, 'webpage_url': 'https://youtu.be/live'})
        self.music.channelSync = AsyncMock()
        self.music.playMusic = AsyncMock()
        await self.music.commonPlay(self.ctx, self.author, ['test'])
        self.ctx.send.assert_called_with('Playing sound:\nlofi 24/7 \U0001f534 LIVE\nhttps://youtu.be/live')
        queued = self.music.musicStates[self.serverId]['queue'][0][0]
        self.assertTrue(queued['isLive'])
        self.assertIsNone(queued['duration'])

    # yt-dlp also omits duration for premieres and some post-live states — not livestreams, but
    # the same TypeError
    async def test_commonPlay_refuses_a_sound_without_a_duration(self):
        self._seed_state()
        voiceState = Mock()
        voiceState.channel = self.voiceChannel
        self.author.voice = voiceState
        self.music.searchYouTube = AsyncMock(return_value = {'title': 'Premiere', 'url': 'http://u', 'duration': None})
        await self.music.commonPlay(self.ctx, self.author, ['test'])
        self.ctx.send.assert_called_once_with('Could not determine the length of that sound.')
        self.assertEqual(len(self.music.musicStates[self.serverId]['queue']), 0)

    # yt-dlp does not guarantee a webpage_url; the title and length still render without one
    async def test_commonPlay_without_a_webpage_url_still_announces_the_song(self):
        self._seed_state(isPlaying = False)
        voiceState = Mock()
        voiceState.channel = self.voiceChannel
        self.author.voice = voiceState
        self.music.searchYouTube = AsyncMock(return_value = {'title': 'T', 'url': 'http://u', 'duration': 155})
        self.music.channelSync = AsyncMock()
        self.music.playMusic = AsyncMock()
        await self.music.commonPlay(self.ctx, self.author, ['test'])
        self.ctx.send.assert_called_with('Playing sound:\nT (2:35)')

    # the metadata the maintainer asked for is carried on the queued song, not re-fetched later
    async def test_commonPlay_stores_the_page_url_and_duration_on_the_queued_song(self):
        self._seed_state(isPlaying = True, isElevatorMode = False)
        voiceState = Mock()
        voiceState.channel = self.voiceChannel
        self.author.voice = voiceState
        self.music.searchYouTube = AsyncMock(return_value = {'title': 'T', 'url': 'http://cdn', 'duration': 155, 'webpage_url': 'https://youtu.be/abc'})
        await self.music.commonPlay(self.ctx, self.author, ['test'])
        song = self.music.musicStates[self.serverId]['queue'][0][0]
        self.assertEqual(song['webpageUrl'], 'https://youtu.be/abc')
        self.assertEqual(song['duration'], 155)
        # C-14: no stream url is stored — the CDN link expires while the song waits in the queue,
        # so playMusic resolves a fresh one from searchString instead
        self.assertNotIn('source', song)
        self.assertEqual(song['searchString'], 'https://youtu.be/abc')
    #endregion

    #region commonQueue
    async def test_commonQueue_idle_no_elevator_no_spotify_no_queue(self):
        self._seed_state(isPlaying = False, isElevatorMode = False)
        with patch('GBotDiscord.src.music.music_cog.pagination.startPages', new = AsyncMock()) as mockStart, \
             patch('GBotDiscord.src.music.music_cog.pagination.CustomButtonMenuPages') as mockPages, \
             patch('GBotDiscord.src.music.music_cog.pagination.DescriptionPageSource') as mockSrc:
            await self.music.commonQueue(self.ctx)
        mockStart.assert_called_once()
        # inspect fields built for the embed (positional arg 5 on DescriptionPageSource: data, title, color, thumb, perPage, fields)
        fields = mockSrc.call_args.kwargs.get('fields') or mockSrc.call_args.args[5]
        self.assertEqual(fields[0]['value'], '`Idle`')
        self.assertEqual(fields[1]['value'], '`Disabled`')
        self.assertEqual(fields[2]['value'], '`Disabled`')

    async def test_commonQueue_playing_with_elevator_and_spotify(self):
        self._seed_state(isPlaying = True, isElevatorMode = True, lastPlayed = {'song': self._song('NowPlaying', 'https://youtu.be/abc', 222, searchString = 's'), 'channel': None})
        self.music.spotifySyncSessions[self.serverId] = {
            'userId': self.author.id,
            'userMention': self.author.mention,
            'lastActivity': "x",
            'context': self.ctx,
            'author': self.author
        }
        with patch('GBotDiscord.src.music.music_cog.pagination.startPages', new = AsyncMock()), \
             patch('GBotDiscord.src.music.music_cog.pagination.CustomButtonMenuPages'), \
             patch('GBotDiscord.src.music.music_cog.pagination.DescriptionPageSource') as mockSrc:
            await self.music.commonQueue(self.ctx)
        fields = mockSrc.call_args.kwargs.get('fields') or mockSrc.call_args.args[5]
        # a masked link, not a bare one: /queue is already an embed and an embed never expands a URL
        self.assertEqual(fields[0]['value'], '[NowPlaying](https://youtu.be/abc) `(3:42)`')
        self.assertEqual(fields[1]['value'], '`Enabled`')
        self.assertEqual(fields[2]['value'], self.author.mention)

    async def test_commonQueue_with_queued_songs(self):
        song = self._song('Track1', '', None)
        self._seed_state(isPlaying = False, queue = [[song, self.voiceChannel]])
        with patch('GBotDiscord.src.music.music_cog.pagination.startPages', new = AsyncMock()), \
             patch('GBotDiscord.src.music.music_cog.pagination.CustomButtonMenuPages'), \
             patch('GBotDiscord.src.music.music_cog.pagination.DescriptionPageSource') as mockSrc:
            await self.music.commonQueue(self.ctx)
        data = mockSrc.call_args.args[0]
        # no metadata on the song: the row falls back to the plain backticked title it always was
        self.assertIn('`1.)` `Track1`', data)

    async def test_commonQueue_queued_songs_carry_masked_links_and_lengths(self):
        # brackets in the title are escaped, or they would terminate the masked link early
        song = self._song('Track [Official]', 'https://youtu.be/abc', 222)
        self._seed_state(isPlaying = False, queue = [[song, self.voiceChannel]])
        with patch('GBotDiscord.src.music.music_cog.pagination.startPages', new = AsyncMock()), \
             patch('GBotDiscord.src.music.music_cog.pagination.CustomButtonMenuPages'), \
             patch('GBotDiscord.src.music.music_cog.pagination.DescriptionPageSource') as mockSrc:
            await self.music.commonQueue(self.ctx)
        data = mockSrc.call_args.args[0]
        self.assertIn('`1.)` [Track \\[Official\\]](https://youtu.be/abc) `(3:42)`', data)

    async def test_commonQueue_now_playing_without_metadata_falls_back_to_the_title(self):
        self._seed_state(isPlaying = True, lastPlayed = {'song': self._song('NowPlaying', '', None), 'channel': None})
        with patch('GBotDiscord.src.music.music_cog.pagination.startPages', new = AsyncMock()), \
             patch('GBotDiscord.src.music.music_cog.pagination.CustomButtonMenuPages'), \
             patch('GBotDiscord.src.music.music_cog.pagination.DescriptionPageSource') as mockSrc:
            await self.music.commonQueue(self.ctx)
        fields = mockSrc.call_args.kwargs.get('fields') or mockSrc.call_args.args[5]
        self.assertEqual(fields[0]['value'], '`NowPlaying`')

    async def test_commonQueue_empty_renders_empty_marker(self):
        self._seed_state(isPlaying = False)
        with patch('GBotDiscord.src.music.music_cog.pagination.startPages', new = AsyncMock()), \
             patch('GBotDiscord.src.music.music_cog.pagination.CustomButtonMenuPages'), \
             patch('GBotDiscord.src.music.music_cog.pagination.DescriptionPageSource') as mockSrc:
            await self.music.commonQueue(self.ctx)
        data = mockSrc.call_args.args[0]
        self.assertIn('`Empty`', data)
    #endregion

    #region commonElevator
    async def test_commonElevator_enable_no_current_song(self):
        self._seed_state(isElevatorMode = False)
        await self.music.commonElevator(self.ctx)
        self.assertTrue(self.music.musicStates[self.serverId]['isElevatorMode'])
        self.ctx.send.assert_called_once_with('Elevator mode enabled.')

    async def test_commonElevator_enable_stops_spotify_sync(self):
        self._seed_state(isElevatorMode = False)
        self.music.spotifySyncSessions[self.serverId] = {
            'userId': self.author.id,
            'userMention': self.author.mention,
            'lastActivity': "x",
            'context': self.ctx,
            'author': self.author
        }
        await self.music.commonElevator(self.ctx)
        self.assertNotIn(self.serverId, self.music.spotifySyncSessions)
        self.ctx.send.assert_any_call(f'Spotify activity sync deactivated for {self.author.mention}.')

    # enabling elevator mode used to kick off a background download of the current song to warm
    # the cache; with the cache gone there is nothing to pre-fetch, and playMusic re-resolves the
    # stream URL on each repeat instead (C-6)
    async def test_commonElevator_enable_with_current_song_does_not_search(self):
        self._seed_state(isElevatorMode = False, lastPlayed = {'song': self._song('T', searchString = 'current'), 'channel': self.voiceChannel})
        self.music.searchYouTube = AsyncMock()
        await self.music.commonElevator(self.ctx)
        self.music.searchYouTube.assert_not_called()
        self.assertTrue(self.music.musicStates[self.serverId]['isElevatorMode'])

    # repeating something with no end is meaningless: a livestream never finishes, so the repeat
    # would only ever fire if the stream itself died
    async def test_commonElevator_refuses_to_repeat_a_livestream(self):
        self._seed_state(isElevatorMode = False, lastPlayed = {'song': self._song('lofi', 'https://youtu.be/live', None, isLive = True), 'channel': self.voiceChannel})
        await self.music.commonElevator(self.ctx)
        self.ctx.send.assert_called_once_with('Elevator mode cannot repeat a livestream.')
        self.assertFalse(self.music.musicStates[self.serverId]['isElevatorMode'])

    async def test_commonElevator_disable(self):
        self._seed_state(isElevatorMode = True)
        await self.music.commonElevator(self.ctx)
        self.assertFalse(self.music.musicStates[self.serverId]['isElevatorMode'])
        self.ctx.send.assert_called_once_with('Elevator mode disabled.')
    #endregion

    #region commonSkip
    async def test_commonSkip_no_voice_client(self):
        self._seed_state(voiceClient = None)
        await self.music.commonSkip(self.ctx, self.author)
        # cog uses the spotify-no-sync message verbatim in the else branch
        self.ctx.send.assert_called_once_with(f'Sorry {self.author.mention}, there is currently nothing playing.')

    async def test_commonSkip_elevator_not_playing_routes_to_play_next(self):
        vc = self._make_voice_client()
        self._seed_state(voiceClient = vc, isElevatorMode = True, isPlaying = False)
        self.music.channelSync = AsyncMock()
        self.music.playMusic = AsyncMock()
        await self.music.commonSkip(self.ctx, self.author)
        self.music.channelSync.assert_called_once_with(self.serverId)
        self.music.playMusic.assert_awaited_once_with(self.serverId)
        self.ctx.send.assert_called_with('Skipped.')

    # C-4 made playMusic await a codec probe, which reopens the window the playLock was added for:
    # this restart has to be serialized with commonPlay's and onSongFinished's like they are with
    # each other. Dropping the `async with` in commonSkip makes this fail.
    async def test_commonSkip_elevator_restart_is_serialized_by_the_play_lock(self):
        vc = self._make_voice_client()
        self._seed_state(voiceClient = vc, isElevatorMode = True, isPlaying = False)
        self.music.channelSync = AsyncMock()

        async def assertLockIsHeld(serverId):
            self.assertTrue(self.music.musicStates[serverId]['playLock'].locked())
        self.music.playMusic = AsyncMock(side_effect = assertLockIsHeld)

        await self.music.commonSkip(self.ctx, self.author)
        self.music.playMusic.assert_awaited_once_with(self.serverId)

    async def test_commonSkip_regular_stop(self):
        vc = self._make_voice_client(is_playing = True)
        self._seed_state(voiceClient = vc, isElevatorMode = False, isPlaying = True)
        await self.music.commonSkip(self.ctx, self.author)
        vc.stop.assert_called_once()
        self.ctx.send.assert_called_with('Skipped.')
    #endregion

    #region commonStop
    async def test_commonStop_no_voice_client(self):
        self._seed_state(voiceClient = None)
        await self.music.commonStop(self.ctx, self.author)
        self.ctx.send.assert_called_once_with(f'Sorry {self.author.mention}, there is currently nothing playing.')

    async def test_commonStop_disconnects(self):
        vc = self._make_voice_client()
        self._seed_state(voiceClient = vc)
        await self.music.commonStop(self.ctx, self.author)
        vc.disconnect.assert_called_once()
        self.assertIsNone(self.music.musicStates[self.serverId]['voiceClient'])
        self.ctx.send.assert_called_with('Stopped.')
    #endregion

    #region commonPause
    async def test_commonPause_no_voice_client(self):
        self._seed_state(voiceClient = None)
        await self.music.commonPause(self.ctx, self.author)
        self.ctx.send.assert_called_once_with(f'Sorry {self.author.mention}, there is currently nothing playing.')

    async def test_commonPause_not_playing(self):
        vc = self._make_voice_client(is_playing = False)
        self._seed_state(voiceClient = vc)
        await self.music.commonPause(self.ctx, self.author)
        vc.pause.assert_not_called()
        self.ctx.send.assert_called_once_with(f'Sorry {self.author.mention}, there is currently nothing playing.')

    async def test_commonPause_playing(self):
        vc = self._make_voice_client(is_playing = True)
        self._seed_state(voiceClient = vc)
        await self.music.commonPause(self.ctx, self.author)
        vc.pause.assert_called_once()
        self.ctx.send.assert_called_once_with('Paused.')
    #endregion

    #region commonResume
    async def test_commonResume_no_voice_client(self):
        self._seed_state(voiceClient = None)
        await self.music.commonResume(self.ctx, self.author)
        self.ctx.send.assert_called_once_with(f'Sorry {self.author.mention}, there is currently nothing paused.')

    async def test_commonResume_not_paused(self):
        vc = self._make_voice_client(is_paused = False)
        self._seed_state(voiceClient = vc)
        await self.music.commonResume(self.ctx, self.author)
        vc.resume.assert_not_called()
        self.ctx.send.assert_called_once_with(f'Sorry {self.author.mention}, there is currently nothing paused.')

    async def test_commonResume_paused(self):
        vc = self._make_voice_client(is_paused = True)
        self._seed_state(voiceClient = vc)
        await self.music.commonResume(self.ctx, self.author)
        vc.resume.assert_called_once()
        self.ctx.send.assert_called_once_with('Resumed.')
    #endregion

    #region searchYouTube
    def _patch_ytdl(self, info = None, raises = False):
        ydl = MagicMock()
        if raises:
            ydl.extract_info = MagicMock(side_effect = Exception("yt-dlp error"))
        else:
            ydl.extract_info = MagicMock(return_value = {'entries': [info]})
        ydlCtx = MagicMock()
        ydlCtx.__enter__.return_value = ydl
        ydlCtx.__exit__.return_value = False
        return patch('GBotDiscord.src.music.music_cog.YoutubeDL', return_value = ydlCtx), ydl

    async def test_searchYouTube_returns_first_entry(self):
        info = {'title': 'Track', 'url': 'http://u', 'duration': 60}
        patcher, ydl = self._patch_ytdl(info = info)
        with patcher:
            result = await self.music.searchYouTube('Track')
        self.assertEqual(result, info)
        ydl.extract_info.assert_called_once_with('ytsearch:Track', download = False)

    # C-8: nothing is downloaded any more, so the yt-dlp options must not carry the
    # download-only keys that wrote mp3s into the container's writable layer.
    async def test_searchYouTube_options_never_write_to_disk(self):
        self.assertNotIn('outtmpl', self.music.YT_DLP_OPTIONS)
        self.assertNotIn('postprocessors', self.music.YT_DLP_OPTIONS)
        self.assertFalse(hasattr(self.music, 'cachedYouTubeFiles'))
        self.assertFalse(hasattr(self.music, 'DOWNLOADED_VIDEOS_PATH'))

    async def test_searchYouTube_returns_none_on_exception(self):
        patcher, _ydl = self._patch_ytdl(raises = True)
        with patcher:
            result = await self.music.searchYouTube('Track')
        self.assertIsNone(result)

    # A-23: extract_info is a blocking network call and ran directly on the event loop, so the
    # whole bot — gateway and API — stalled for the duration of every /play.
    async def test_searchYouTube_runs_the_search_off_the_event_loop(self):
        info = {'title': 'Track', 'url': 'http://u', 'duration': 60}
        patcher, _ydl = self._patch_ytdl(info = info)
        loopThreadId = threading.get_ident()
        searchThreadIds = []
        realExtract = self.music.extractSongInfo

        def recordThread(searchString):
            searchThreadIds.append(threading.get_ident())
            return realExtract(searchString)
        self.music.extractSongInfo = recordThread

        with patcher:
            result = await self.music.searchYouTube('Track')
        self.assertEqual(result, info)
        self.assertEqual(len(searchThreadIds), 1)
        self.assertNotEqual(searchThreadIds[0], loopThreadId)

    # C-11: every input was prefixed ytsearch:, so a pasted link was used as a search *query* —
    # usually lucky, occasionally the wrong video, and never a canonical webpage_url worth showing.
    # Fails against the old code twice over: it called extract_info with the ytsearch: prefix, and
    # then indexed ['entries'][0] on a dict that has no entries.
    async def test_extractSongInfo_fetches_a_url_instead_of_searching_it(self):
        videoUrl = 'https://www.youtube.com/watch?v=abc'
        info = {'title': 'Track', 'url': 'http://cdn', 'duration': 60, 'webpage_url': videoUrl}
        ydl = MagicMock()
        # a fetched result is the video dict itself, not a search wrapper carrying entries
        ydl.extract_info = MagicMock(return_value = info)
        ydlCtx = MagicMock()
        ydlCtx.__enter__.return_value = ydl
        ydlCtx.__exit__.return_value = False
        with patch('GBotDiscord.src.music.music_cog.YoutubeDL', return_value = ydlCtx):
            result = await self.music.searchYouTube(videoUrl)
        self.assertEqual(result, info)
        ydl.extract_info.assert_called_once_with(videoUrl, download = False)

    # extract_flat keeps a 200-song playlist from becoming 200 network round trips, but it must
    # NOT reach the search path: a ytsearch: result is itself a playlist, and flattening it would
    # strip the duration commonPlay has to check and the stream URL playback needs.
    async def test_extractSongInfo_flattens_a_playlist_but_never_the_search_path(self):
        captured = []
        outer = self
        class FakeYdl:
            def __init__(self, options):
                captured.append(options)
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def extract_info(self, target, download):
                return {'entries': [{'title': 'T', 'url': 'u', 'duration': 1}]}
        with patch('GBotDiscord.src.music.music_cog.YoutubeDL', FakeYdl):
            await self.music.searchYouTube('https://www.youtube.com/playlist?list=x')
            await self.music.searchYouTube('some song')
        self.assertEqual(captured[0]['extract_flat'], 'in_playlist')
        # one past the cap, so "there were more" is knowable without listing thousands
        self.assertEqual(captured[0]['playlistend'], GBotPropertiesManager.MUSIC_MAX_PLAYLIST_SONGS + 1)
        self.assertNotIn('extract_flat', captured[1])
        self.assertNotIn('playlistend', captured[1])

    # a malformed link raises out of urlparse, which lands on extractSongInfo's existing None path
    # — the user sees the same message as a search that found nothing
    async def test_extractSongInfo_malformed_url_is_treated_as_a_failed_lookup(self):
        patcher, _ydl = self._patch_ytdl(info = {'title': 'T'})
        with patcher:
            result = await self.music.searchYouTube('http://[')
        self.assertIsNone(result)

    async def test_isUrl_distinguishes_links_from_search_terms(self):
        cases = [
            ('https://www.youtube.com/watch?v=abc', True),
            ('http://youtu.be/abc', True),
            ('HTTPS://music.youtube.com/watch?v=abc', True),   # urlparse lowercases the scheme
            ('halo theme song', False),
            ('R.E.M. - Losing My Religion', False),            # dots are not a domain
            ('Song: The Remix', False),                        # parses a scheme, just not an http one
            ('youtube.com/watch?v=abc', False),                # no scheme: indistinguishable from a title
            ('', False)
        ]
        for candidate, expected in cases:
            with self.subTest(candidate = candidate):
                self.assertEqual(self.music.isUrl(candidate), expected)
    #endregion

    #region song rendering helpers
    async def test_formatDuration_renders_minutes_and_hours(self):
        cases = [(0, '0:00'), (7, '0:07'), (60, '1:00'), (222, '3:42'), (222.9, '3:42'), (3600, '1:00:00'), (3723, '1:02:03'), (36000, '10:00:00')]
        for seconds, expected in cases:
            with self.subTest(seconds = seconds):
                self.assertEqual(self.music.formatDuration(seconds), expected)

    # "[Official Video]" is everywhere in YouTube titles and would terminate a masked link early
    async def test_escapeLinkText_escapes_brackets(self):
        self.assertEqual(self.music.escapeLinkText('Song [Official Video]'), 'Song \\[Official Video\\]')

    async def test_describeLength_labels_a_livestream_instead_of_measuring_it(self):
        self.assertEqual(self.music.describeLength(self._song('L', 'u', None, isLive = True)), '\U0001f534 LIVE')
        self.assertEqual(self.music.describeLength(self._song('T', 'u', 222)), '(3:42)')
        self.assertIsNone(self.music.describeLength(self._song('T', 'u', None)))

    async def test_describeSongText_bare_link_lets_discord_render_its_card(self):
        self.assertEqual(self.music.describeSongText(self._song('T', 'https://youtu.be/abc', 222)), 'T (3:42)\nhttps://youtu.be/abc')

    async def test_describeSongText_suppressed_link_hides_the_card(self):
        self.assertEqual(self.music.describeSongText(self._song('T', 'https://youtu.be/abc', 222), suppressEmbed = True), 'T (3:42)\n<https://youtu.be/abc>')

    async def test_describeSongText_without_metadata_is_just_the_title(self):
        self.assertEqual(self.music.describeSongText(self._song('T', '', None)), 'T')

    async def test_describeSongEmbed_uses_a_masked_link(self):
        self.assertEqual(self.music.describeSongEmbed(self._song('T', 'https://youtu.be/abc', 222)), '[T](https://youtu.be/abc) `(3:42)`')

    async def test_describeSongEmbed_without_a_url_falls_back_to_the_plain_title(self):
        self.assertEqual(self.music.describeSongEmbed(self._song('T', '', None)), '`T`')
    #endregion

    #region channelSync
    async def test_channelSync_empty_queue_not_elevator_noop(self):
        self._seed_state(isElevatorMode = False, queue = [])
        # nothing crashes and nothing connects
        await self.music.channelSync(self.serverId)
        self.voiceChannel.connect.assert_not_called()

    async def test_channelSync_connects_when_no_voice_client(self):
        song = {'source': 'u', 'title': 'T'}
        self._seed_state(queue = [[song, self.voiceChannel, 't']])
        vc = self._make_voice_client()
        self.voiceChannel.connect = AsyncMock(return_value = vc)
        await self.music.channelSync(self.serverId)
        self.voiceChannel.connect.assert_called_once()
        self.assertEqual(self.music.musicStates[self.serverId]['voiceClient'], vc)

    async def test_channelSync_moves_to_when_connected(self):
        song = {'source': 'u', 'title': 'T'}
        vc = self._make_voice_client(is_connected = True)
        self._seed_state(queue = [[song, self.voiceChannel, 't']], voiceClient = vc)
        await self.music.channelSync(self.serverId)
        vc.move_to.assert_called_once_with(self.voiceChannel)

    async def test_channelSync_elevator_uses_lastPlayed_channel(self):
        elevatorChannel = Mock()
        elevatorChannel.id = 22222
        vc = self._make_voice_client(is_connected = True)
        self._seed_state(
            isElevatorMode = True,
            voiceClient = vc,
            lastPlayed = {'song': self._song('T', searchString = 's'), 'channel': elevatorChannel}
        )
        await self.music.channelSync(self.serverId)
        vc.move_to.assert_called_once_with(elevatorChannel)

    async def test_channelSync_disconnected_voice_client_reconnects_to_queue(self):
        song = {'source': 'u', 'title': 'T'}
        vc = self._make_voice_client(is_connected = False)
        newVc = self._make_voice_client()
        self.voiceChannel.connect = AsyncMock(return_value = newVc)
        self._seed_state(queue = [[song, self.voiceChannel, 't']], voiceClient = vc)
        await self.music.channelSync(self.serverId)
        self.voiceChannel.connect.assert_called_once()
        self.assertEqual(self.music.musicStates[self.serverId]['voiceClient'], newVc)

    # A-18: with elevator mode on and an empty queue — exactly the state a dropped voice
    # connection leaves behind — both branches fell through to queue[0][1] and raised IndexError.
    async def test_channelSync_elevator_empty_queue_reconnects_to_the_elevator_channel(self):
        elevatorChannel = Mock()
        elevatorChannel.id = 22222
        newVc = self._make_voice_client()
        elevatorChannel.connect = AsyncMock(return_value = newVc)
        vc = self._make_voice_client(is_connected = False)
        self._seed_state(
            isElevatorMode = True,
            voiceClient = vc,
            queue = [],
            lastPlayed = {'song': self._song('T', searchString = 's'), 'channel': elevatorChannel}
        )
        await self.music.channelSync(self.serverId)
        elevatorChannel.connect.assert_called_once()
        self.assertEqual(self.music.musicStates[self.serverId]['voiceClient'], newVc)

    # A-18: elevator mode on, empty queue, and nothing played yet — there is no channel to sync
    # to at all, which used to be the same IndexError.
    async def test_channelSync_elevator_empty_queue_without_lastPlayed_is_a_noop(self):
        self.music.logger = MagicMock()
        self._seed_state(isElevatorMode = True, queue = [])
        await self.music.channelSync(self.serverId)
        self.voiceChannel.connect.assert_not_called()
        self.music.logger.warning.assert_called_once()

    async def test_channelSync_discards_a_disconnected_voice_client_before_connecting(self):
        song = {'source': 'u', 'title': 'T'}
        vc = self._make_voice_client(is_connected = False)
        newVc = self._make_voice_client()
        self.voiceChannel.connect = AsyncMock(return_value = newVc)
        self._seed_state(queue = [[song, self.voiceChannel, 't']], voiceClient = vc)
        await self.music.channelSync(self.serverId)
        # a client left behind by a failed handshake still owns the guild's voice slot
        vc.disconnect.assert_awaited_once_with(force = True)

    async def test_channelSync_connects_even_if_discarding_the_stale_client_fails(self):
        song = {'source': 'u', 'title': 'T'}
        vc = self._make_voice_client(is_connected = False)
        vc.disconnect = AsyncMock(side_effect = Exception("already gone"))
        newVc = self._make_voice_client()
        self.voiceChannel.connect = AsyncMock(return_value = newVc)
        self._seed_state(queue = [[song, self.voiceChannel, 't']], voiceClient = vc)
        self.music.logger = MagicMock()
        await self.music.channelSync(self.serverId)
        self.music.logger.error.assert_called_once()
        self.voiceChannel.connect.assert_called_once()
        self.assertEqual(self.music.musicStates[self.serverId]['voiceClient'], newVc)
    #endregion

    #region playMusic
    async def test_playMusic_empty_queue_no_elevator_marks_idle(self):
        vc = self._make_voice_client()
        self._seed_state(isPlaying = True, voiceClient = vc, queue = [])
        await self.music.playMusic(self.serverId)
        self.assertFalse(self.music.musicStates[self.serverId]['isPlaying'])
        vc.play.assert_not_called()

    async def test_playMusic_no_voice_client_marks_idle_and_keeps_the_queue(self):
        song = self._song()
        self._seed_state(isPlaying = True, voiceClient = None, queue = [[song, self.voiceChannel]])
        await self.music.playMusic(self.serverId)
        self.assertFalse(self.music.musicStates[self.serverId]['isPlaying'])
        self.assertEqual(len(self.music.musicStates[self.serverId]['queue']), 1)

    # C-1 leaves a voiceClient that is non-None but was never connected, and the after callback
    # keeps firing after a kick or a /stop; playing into that client raised ClientException and
    # ate the queue entry.
    async def test_playMusic_disconnected_voice_client_marks_idle_and_keeps_the_queue(self):
        vc = self._make_voice_client(is_connected = False)
        song = self._song()
        self._seed_state(isPlaying = True, voiceClient = vc, queue = [[song, self.voiceChannel]])
        await self.music.playMusic(self.serverId)
        vc.play.assert_not_called()
        self.assertFalse(self.music.musicStates[self.serverId]['isPlaying'])
        self.assertEqual(len(self.music.musicStates[self.serverId]['queue']), 1)

    async def test_playMusic_already_playing_leaves_the_running_song_alone(self):
        # nextcord raises ClientException on a second play(); the running song's after callback
        # is what advances the queue
        vc = self._make_voice_client(is_playing = True)
        song = self._song()
        self._seed_state(isPlaying = True, voiceClient = vc, queue = [[song, self.voiceChannel]])
        await self.music.playMusic(self.serverId)
        vc.play.assert_not_called()
        self.assertEqual(len(self.music.musicStates[self.serverId]['queue']), 1)

    async def test_playMusic_after_guild_removed_is_a_noop(self):
        # on_guild_remove popped the state while a song was playing; the after callback still fires
        await self.music.playMusic(self.serverId)
        self.assertNotIn(self.serverId, self.music.musicStates)

    # A-18's sibling in playMusic: elevator mode on with an empty queue and nothing played yet
    # reached the queue branch and indexed queue[0].
    async def test_playMusic_elevator_without_lastPlayed_and_empty_queue_marks_idle(self):
        vc = self._make_voice_client()
        self._seed_state(isPlaying = True, isElevatorMode = True, voiceClient = vc, queue = [])
        await self.music.playMusic(self.serverId)
        vc.play.assert_not_called()
        self.assertFalse(self.music.musicStates[self.serverId]['isPlaying'])

    async def test_playMusic_queue_item_plays_and_pops(self):
        song = self._song()
        vc = self._make_voice_client()
        self._seed_state(voiceClient = vc, queue = [[song, self.voiceChannel]])
        self.music.searchYouTube = AsyncMock(return_value = {'url': 'http://cdn'})
        with self._patch_audio_source() as mockAudio:
            await self.music.playMusic(self.serverId)
        vc.play.assert_called_once()
        mockAudio.assert_called_once()
        # queue popped
        self.assertEqual(len(self.music.musicStates[self.serverId]['queue']), 0)
        # lastPlayed holds the song itself, and that song still carries no stream url (C-6/C-14)
        self.assertEqual(self.music.musicStates[self.serverId]['lastPlayed']['song'], song)
        self.assertNotIn('source', self.music.musicStates[self.serverId]['lastPlayed']['song'])
        self.assertNotIn('url', self.music.musicStates[self.serverId]['lastPlayed']['song'])
        self.assertTrue(self.music.musicStates[self.serverId]['isPlaying'])

    # C-14: the stream URL used to be resolved at QUEUE time and replayed whenever the song
    # reached the head — the same expiring, IP-bound CDN link as C-6, with the delay set by how
    # long the queue is. It is now resolved here, at play time, from the song's searchString.
    # Fails against the old code, which never called searchYouTube on the queue path at all.
    async def test_playMusic_elevator_replays_lastPlayed_without_popping(self):
        vc = self._make_voice_client()
        lastPlayed = {'song': self._song('Prev', 'https://youtu.be/prev'), 'channel': self.voiceChannel}
        self._seed_state(voiceClient = vc, isElevatorMode = True, queue = [[self._song('Other', 'https://youtu.be/other'), self.voiceChannel]], lastPlayed = lastPlayed)
        self.music.searchYouTube = AsyncMock(return_value = {'url': 'http://fresh'})
        with self._patch_audio_source():
            await self.music.playMusic(self.serverId)
        # queue not popped — elevator replays lastPlayed
        self.assertEqual(len(self.music.musicStates[self.serverId]['queue']), 1)
        self.assertEqual(self.music.musicStates[self.serverId]['lastPlayed']['song']['title'], 'Prev')

    # C-6: info['url'] is a time-limited, IP-bound CDN URL, but elevator mode replayed the stored
    # one forever — so once it expired every repeat 403'd, and ffmpeg's reconnect flags cannot
    # recover from that. This fails against pre-C-PR5 code, which never re-searched.
    async def test_playMusic_elevator_reresolves_the_stream_url_on_every_repeat(self):
        vc = self._make_voice_client()
        lastPlayed = {'song': self._song('Prev', 'https://youtu.be/prev'), 'channel': self.voiceChannel}
        self._seed_state(voiceClient = vc, isElevatorMode = True, queue = [], lastPlayed = lastPlayed)
        self.music.searchYouTube = AsyncMock(return_value = {'url': 'http://fresh'})
        with self._patch_audio_source() as mockAudio:
            await self.music.playMusic(self.serverId)
        self.music.searchYouTube.assert_awaited_once_with('https://youtu.be/prev')
        # the freshly resolved url is what gets played
        mockAudio.probe.assert_awaited_once_with('http://fresh')
        mockAudio.assert_called_once_with('http://fresh', codec = 'opus', **self.music.FFMPEG_OPTIONS)
        vc.play.assert_called_once()

    # a failed re-resolve goes idle rather than retrying: music_timeout disconnects after
    # MUSIC_TIMEOUT_SECONDS and commonSkip's elevator branch restarts playback on demand
    async def test_playMusic_elevator_failed_reresolve_logs_and_goes_idle(self):
        vc = self._make_voice_client()
        lastPlayed = {'song': self._song('Prev', 'https://youtu.be/prev'), 'channel': self.voiceChannel}
        self._seed_state(isPlaying = True, voiceClient = vc, isElevatorMode = True, queue = [], lastPlayed = lastPlayed)
        self.music.searchYouTube = AsyncMock(return_value = None)
        self.music.logger = MagicMock()
        await self.music.playMusic(self.serverId)
        self.music.logger.error.assert_called_once()
        self.assertFalse(self.music.musicStates[self.serverId]['isPlaying'])
        vc.play.assert_not_called()

    async def test_playMusic_resolves_the_stream_url_at_play_time_not_queue_time(self):
        song = self._song('T', 'https://youtu.be/abc', 222)
        vc = self._make_voice_client()
        self._seed_state(voiceClient = vc, queue = [[song, self.voiceChannel]])
        self.music.searchYouTube = AsyncMock(return_value = {'url': 'http://fresh-cdn'})
        with self._patch_audio_source() as mockAudio:
            await self.music.playMusic(self.serverId)
        self.music.searchYouTube.assert_awaited_once_with('https://youtu.be/abc')
        mockAudio.probe.assert_awaited_once_with('http://fresh-cdn')
        self.assertEqual(self.music.musicStates[self.serverId]['lastPlayed']['song'], song)

    # a failed resolve on the queue path goes idle exactly like the elevator one
    async def test_playMusic_queue_failed_resolve_logs_and_goes_idle(self):
        vc = self._make_voice_client()
        self._seed_state(isPlaying = True, voiceClient = vc, queue = [[self._song(), self.voiceChannel]])
        self.music.searchYouTube = AsyncMock(return_value = None)
        self.music.logger = MagicMock()
        await self.music.playMusic(self.serverId)
        self.music.logger.error.assert_called_once()
        self.assertFalse(self.music.musicStates[self.serverId]['isPlaying'])
        vc.play.assert_not_called()

    # yt-dlp can return info with no playable url (the live URL probed during QA did exactly this)
    async def test_playMusic_resolve_without_a_url_goes_idle(self):
        vc = self._make_voice_client()
        self._seed_state(isPlaying = True, voiceClient = vc, queue = [[self._song(), self.voiceChannel]])
        self.music.searchYouTube = AsyncMock(return_value = {'title': 'T'})
        self.music.logger = MagicMock()
        await self.music.playMusic(self.serverId)
        self.music.logger.error.assert_called_once()
        self.assertFalse(self.music.musicStates[self.serverId]['isPlaying'])
        vc.play.assert_not_called()

    # C-4: FFmpegPCMAudio made ffmpeg decode to PCM and nextcord Opus-encode every 20 ms frame
    # in-process. YouTube's bestaudio is already Opus, so the probed codec is handed to
    # FFmpegOpusAudio, which turns it into -c:a copy.
    async def test_playMusic_streams_with_the_probed_codec_and_reconnect_options(self):
        vc = self._make_voice_client()
        song = self._song()
        self._seed_state(voiceClient = vc, queue = [[song, self.voiceChannel]])
        self.music.searchYouTube = AsyncMock(return_value = {'url': 'http://cdn'})
        with self._patch_audio_source(codec = 'opus') as mockAudio:
            await self.music.playMusic(self.serverId)
        mockAudio.probe.assert_awaited_once_with('http://cdn')
        mockAudio.assert_called_once_with('http://cdn', codec = 'opus', **self.music.FFMPEG_OPTIONS)

    # nextcord's native probe computes bitrate as max(round(kbps), 512), so it never reports below
    # 512 kbps; from_probe would pass that straight to -b:a (and None through on a probe failure,
    # which ffmpeg rejects outright). Only the codec is taken from the probe.
    async def test_playMusic_does_not_forward_the_probed_bitrate(self):
        vc = self._make_voice_client()
        song = self._song()
        self._seed_state(voiceClient = vc, queue = [[song, self.voiceChannel]])
        self.music.searchYouTube = AsyncMock(return_value = {'url': 'http://cdn'})
        with self._patch_audio_source(codec = None, bitrate = None) as mockAudio:
            await self.music.playMusic(self.serverId)
        self.assertNotIn('bitrate', mockAudio.call_args.kwargs)
        # an unprobeable source still plays: ffmpeg encodes opus at the constructor's own default
        self.assertIsNone(mockAudio.call_args.kwargs['codec'])
        vc.play.assert_called_once()

    # A-20: after=lambda e: self.playMusic(serverId) ran on ffmpeg's audio thread, mutating
    # musicStates off the event loop. Returning a coroutine is what makes nextcord submit the
    # work to the loop (run_coroutine_threadsafe) instead of running it there.
    async def test_playMusic_after_callback_returns_a_coroutine_for_the_event_loop(self):
        vc = self._make_voice_client()
        song = self._song()
        self._seed_state(voiceClient = vc, queue = [[song, self.voiceChannel]])
        self.music.searchYouTube = AsyncMock(return_value = {'url': 'http://cdn'})
        with self._patch_audio_source():
            await self.music.playMusic(self.serverId)
        after = vc.play.call_args.kwargs['after']
        self.music.playMusic = AsyncMock()
        advance = after(None)
        self.assertTrue(asyncio.iscoroutine(advance))
        # nothing has touched the state yet — it only runs once the loop awaits it
        self.music.playMusic.assert_not_awaited()
        await advance
        self.music.playMusic.assert_awaited_once_with(self.serverId)
    #endregion

    #region onSongFinished
    # A-20: the callback's error argument was discarded, so an ffmpeg failure was
    # indistinguishable from a song ending and silently advanced the queue.
    async def test_onSongFinished_logs_the_playback_error(self):
        self._seed_state()
        self.music.logger = MagicMock()
        self.music.playMusic = AsyncMock()
        await self.music.onSongFinished(self.serverId, Exception("ffmpeg exited"))
        self.music.logger.error.assert_called_once()
        self.music.playMusic.assert_awaited_once_with(self.serverId)

    async def test_onSongFinished_without_error_advances_quietly(self):
        self._seed_state()
        self.music.logger = MagicMock()
        self.music.playMusic = AsyncMock()
        await self.music.onSongFinished(self.serverId, None)
        self.music.logger.error.assert_not_called()
        self.music.playMusic.assert_awaited_once_with(self.serverId)

    async def test_onSongFinished_after_guild_removed_is_a_noop(self):
        # on_guild_remove popped the state while a song was playing: there is no lock left to take
        self.music.playMusic = AsyncMock()
        await self.music.onSongFinished(self.serverId, None)
        self.music.playMusic.assert_not_awaited()

    # C-4 made playMusic await a codec probe, so the advance the after callback triggers has to be
    # serialized with commonPlay and commonSkip. Dropping the `async with` here makes this fail.
    async def test_onSongFinished_advance_is_serialized_by_the_play_lock(self):
        self._seed_state()

        async def assertLockIsHeld(serverId):
            self.assertTrue(self.music.musicStates[serverId]['playLock'].locked())
        self.music.playMusic = AsyncMock(side_effect = assertLockIsHeld)

        await self.music.onSongFinished(self.serverId, None)
        self.music.playMusic.assert_awaited_once_with(self.serverId)
    #endregion

    #region disconnectAndClearQueue
    async def test_disconnectAndClearQueue_no_voice_client_no_spotify(self):
        self._seed_state(voiceClient = None)
        await self.music.disconnectAndClearQueue(self.serverId)
        # state untouched (no voiceClient to clear)
        self.assertIsNone(self.music.musicStates[self.serverId]['voiceClient'])

    async def test_disconnectAndClearQueue_with_voice_client_resets_state(self):
        vc = self._make_voice_client()
        song = {'source': 'u', 'title': 'T'}
        self._seed_state(
            voiceClient = vc,
            isPlaying = True,
            isElevatorMode = True,
            queue = [[song, self.voiceChannel]],
            lastPlayed = {'song': self._song('T', 'https://youtu.be/abc', 222, searchString = 'q'), 'channel': self.voiceChannel}
        )
        await self.music.disconnectAndClearQueue(self.serverId)
        vc.disconnect.assert_called_once()
        state = self.music.musicStates[self.serverId]
        self.assertIsNone(state['voiceClient'])
        self.assertEqual(state['queue'], [])
        self.assertFalse(state['isPlaying'])
        self.assertFalse(state['isElevatorMode'])
        self.assertEqual(state['lastPlayed'], self.music.newLastPlayed())

    async def test_disconnectAndClearQueue_pops_spotify_session(self):
        self._seed_state(voiceClient = None)
        self.music.spotifySyncSessions[self.serverId] = {
            'userId': self.author.id,
            'userMention': self.author.mention,
            'lastActivity': "x",
            'context': self.ctx,
            'author': self.author
        }
        await self.music.disconnectAndClearQueue(self.serverId)
        self.assertNotIn(self.serverId, self.music.spotifySyncSessions)
    #endregion

    #region YTDLPLogger
    def test_ytdlp_logger_debug_prefix(self):
        logger = self.music.ytdlLogger
        with patch.object(logger.logger, 'debug') as mockDebug:
            logger.debug('[debug] some line')
            mockDebug.assert_called_once_with('[debug] some line')

    def test_ytdlp_logger_debug_no_prefix_routes_to_info(self):
        logger = self.music.ytdlLogger
        with patch.object(logger.logger, 'info') as mockInfo:
            logger.debug('some line')
            mockInfo.assert_called_once_with('some line')

    def test_ytdlp_logger_info(self):
        logger = self.music.ytdlLogger
        with patch.object(logger.logger, 'info') as mockInfo:
            logger.info('hello')
            mockInfo.assert_called_once_with('hello')

    def test_ytdlp_logger_warning(self):
        logger = self.music.ytdlLogger
        with patch.object(logger.logger, 'warning') as mockWarn:
            logger.warning('warn!')
            mockWarn.assert_called_once_with('warn!')

    def test_ytdlp_logger_error(self):
        logger = self.music.ytdlLogger
        with patch.object(logger.logger, 'error') as mockErr:
            logger.error('boom')
            mockErr.assert_called_once_with('boom')
    #endregion

    #region prefix command wrappers (delegate to commonX)
    # Slash wrappers route through SlashApplicationCommand.__call__ which auto-binds parent_cog
    # and can't be invoked the same way; commonX paths are covered by direct calls above.
    async def test_spotify_prefix_delegates(self):
        utils.isUserInThisGuildAndNotABot = AsyncMock(return_value = True)
        self.author.activities = []
        await self.music.spotify(self.music, self.ctx, None)
        self.ctx.send.assert_called_with(f'Sorry {self.author.mention}, there is currently no Spotify activity to sync with.')

    async def test_play_prefix_delegates(self):
        self._seed_state()
        self.author.voice = None
        await self.music.play(self.music, self.ctx, 'test')
        self.ctx.send.assert_called_once_with('Please connect to a voice channel.')

    async def test_queue_prefix_delegates(self):
        self._seed_state()
        with patch('GBotDiscord.src.music.music_cog.pagination.startPages', new = AsyncMock()) as mockStart, \
             patch('GBotDiscord.src.music.music_cog.pagination.CustomButtonMenuPages'), \
             patch('GBotDiscord.src.music.music_cog.pagination.DescriptionPageSource'):
            await self.music.queue(self.music, self.ctx)
        mockStart.assert_called_once()

    async def test_elevator_prefix_delegates(self):
        self._seed_state(isElevatorMode = False)
        await self.music.elevator(self.music, self.ctx)
        self.assertTrue(self.music.musicStates[self.serverId]['isElevatorMode'])

    async def test_skip_prefix_delegates(self):
        self._seed_state(voiceClient = None)
        await self.music.skip(self.music, self.ctx)
        self.ctx.send.assert_called_once_with(f'Sorry {self.author.mention}, there is currently nothing playing.')

    async def test_stop_prefix_delegates(self):
        self._seed_state(voiceClient = None)
        await self.music.stop(self.music, self.ctx)
        self.ctx.send.assert_called_once_with(f'Sorry {self.author.mention}, there is currently nothing playing.')

    async def test_pause_prefix_delegates(self):
        self._seed_state(voiceClient = None)
        await self.music.pause(self.music, self.ctx)
        self.ctx.send.assert_called_once_with(f'Sorry {self.author.mention}, there is currently nothing playing.')

    async def test_resume_prefix_delegates(self):
        self._seed_state(voiceClient = None)
        await self.music.resume(self.music, self.ctx)
        self.ctx.send.assert_called_once_with(f'Sorry {self.author.mention}, there is currently nothing paused.')
    #endregion

    #region slash command wrappers (delegate to commonX)
    async def test_spotifySlash_delegates(self):
        self.music.commonSpotify = AsyncMock()
        await self.music.spotifySlash(self.interaction, self.author)
        self.music.commonSpotify.assert_awaited_once_with(self.interaction, self.interaction.user, self.author)

    async def test_playSlash_delegates(self):
        self.music.commonPlay = AsyncMock()
        await self.music.playSlash(self.interaction, '"a" "b"')
        self.music.commonPlay.assert_awaited_once()
        callArgs = self.music.commonPlay.await_args.args
        self.assertIs(callArgs[0], self.interaction)
        self.assertIs(callArgs[1], self.interaction.user)
        self.assertEqual(list(callArgs[2]), ['a', 'b'])

    async def test_queueSlash_delegates(self):
        self.music.commonQueue = AsyncMock()
        await self.music.queueSlash(self.interaction)
        self.music.commonQueue.assert_awaited_once_with(self.interaction)

    async def test_elevatorSlash_delegates(self):
        self.music.commonElevator = AsyncMock()
        await self.music.elevatorSlash(self.interaction)
        self.music.commonElevator.assert_awaited_once_with(self.interaction)

    async def test_skipSlash_delegates(self):
        self.music.commonSkip = AsyncMock()
        await self.music.skipSlash(self.interaction)
        self.music.commonSkip.assert_awaited_once_with(self.interaction, self.interaction.user)

    async def test_stopSlash_delegates(self):
        self.music.commonStop = AsyncMock()
        await self.music.stopSlash(self.interaction)
        self.music.commonStop.assert_awaited_once_with(self.interaction, self.interaction.user)

    async def test_pauseSlash_delegates(self):
        self.music.commonPause = AsyncMock()
        await self.music.pauseSlash(self.interaction)
        self.music.commonPause.assert_awaited_once_with(self.interaction, self.interaction.user)

    async def test_resumeSlash_delegates(self):
        self.music.commonResume = AsyncMock()
        await self.music.resumeSlash(self.interaction)
        self.music.commonResume.assert_awaited_once_with(self.interaction, self.interaction.user)
    #endregion

    async def test_commonSpotify_user_without_activities_attr(self):
        # hasattr(user, 'activities') False branch — user lacks the attribute entirely
        utils.isUserInThisGuildAndNotABot = AsyncMock(return_value = True)
        slimUser = Mock(spec = ['id', 'mention'])
        slimUser.id = 99
        slimUser.mention = '<@!99>'
        await self.music.commonSpotify(self.ctx, self.author, slimUser)
        self.ctx.send.assert_called_with(f'Sorry {self.author.mention}, there is currently no Spotify activity to sync with.')

    async def test_commonSpotify_non_spotify_activity_continues_loop(self):
        # an activity that isn't a Spotify instance — the inner if is False, loop continues to exit
        utils.isUserInThisGuildAndNotABot = AsyncMock(return_value = True)
        nonSpotifyActivity = Mock()  # not a Spotify instance
        self.author.activities = [nonSpotifyActivity]
        await self.music.commonSpotify(self.ctx, self.author, None)
        self.ctx.send.assert_called_with(f'Sorry {self.author.mention}, there is currently no Spotify activity to sync with.')

    def test_setup_adds_cog(self):
        from GBotDiscord.src.music import music_cog
        client = MagicMock()
        music_cog.setup(client)
        client.add_cog.assert_called_once()
        addedCog = client.add_cog.call_args[0][0]
        self.assertIsInstance(addedCog, Music)


if __name__ == '__main__':
    unittest.main()
