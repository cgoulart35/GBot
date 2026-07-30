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
        GBotPropertiesManager.MUSIC_CACHE_DELETION_TIMEOUT_MINUTES = 3

        self.serverId = '99999'

        # avoid touching the real filesystem when Music.__init__ ensures the sounds/ dir
        self.exists_patcher = patch('GBotDiscord.src.music.music_cog.os.path.exists', return_value = True)
        self.exists_patcher.start()
        self.addCleanup(self.exists_patcher.stop)
        self.makedirs_patcher = patch('GBotDiscord.src.music.music_cog.os.makedirs')
        self.makedirs_patcher.start()
        self.addCleanup(self.makedirs_patcher.stop)

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

    def _seed_state(self, serverId = None, isPlaying = False, isElevatorMode = False, voiceClient = None, queue = None, lastPlayed = None, inactiveSeconds = 0):
        serverId = serverId if serverId is not None else self.serverId
        self.music.musicStates[serverId] = {
            'isPlaying': isPlaying,
            'isElevatorMode': isElevatorMode,
            'voiceClient': voiceClient,
            'queue': queue if queue is not None else [],
            'lastPlayed': lastPlayed if lastPlayed is not None else {'url': '', 'name': '', 'channel': None, 'searchString': ''},
            'inactiveSeconds': inactiveSeconds,
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
        self.music.cached_youtube_files.start = MagicMock()
        await self.music.on_ready()
        self.assertIn(self.serverId, self.music.musicStates)
        self.music.music_timeout.start.assert_called_once()
        self.music.spotify_sync.start.assert_called_once()
        self.music.cached_youtube_files.start.assert_called_once()

    async def test_on_ready_skips_init_when_state_exists(self):
        self._seed_state(isPlaying = True)
        utils.filterGuildsForInstance = MagicMock()
        self.music.music_timeout.start = MagicMock()
        self.music.spotify_sync.start = MagicMock()
        self.music.cached_youtube_files.start = MagicMock()
        await self.music.on_ready()
        utils.filterGuildsForInstance.assert_not_called()
        self.assertTrue(self.music.musicStates[self.serverId]['isPlaying'])

    async def test_on_ready_tasks_already_running(self):
        self._seed_state()
        self.music.music_timeout.start = MagicMock(side_effect = RuntimeError("running"))
        self.music.spotify_sync.start = MagicMock(side_effect = RuntimeError("running"))
        self.music.cached_youtube_files.start = MagicMock(side_effect = RuntimeError("running"))
        # all three RuntimeErrors must be swallowed by the cog
        await self.music.on_ready()
        self.music.music_timeout.start.assert_called_once()
        self.music.spotify_sync.start.assert_called_once()
        self.music.cached_youtube_files.start.assert_called_once()
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
        self._seed_state(voiceClient = vc, lastPlayed = {'url': 'u', 'name': 'T', 'channel': self.voiceChannel, 'searchString': 's'})
        await self.music.on_voice_state_update(member, self._make_voice_state(self.voiceChannel), self._make_voice_state(newChannel))
        self.assertEqual(self.music.musicStates[self.serverId]['lastPlayed']['channel'], newChannel)

    async def test_on_voice_state_update_bot_connecting_is_not_treated_as_a_move(self):
        member = self._make_bot_client()
        vc = self._make_voice_client()
        self._seed_state(voiceClient = vc, lastPlayed = {'url': 'u', 'name': 'T', 'channel': None, 'searchString': 's'})
        # before.channel is None on a fresh connect; playMusic owns lastPlayed from there
        await self.music.on_voice_state_update(member, self._make_voice_state(), self._make_voice_state(self.voiceChannel))
        self.assertIsNone(self.music.musicStates[self.serverId]['lastPlayed']['channel'])

    async def test_on_voice_state_update_last_listener_leaving_disconnects(self):
        self._make_bot_client()
        listener = self._make_member(54321)
        botMember = self._make_member(77777, isBot = True)
        self.voiceChannel.members = [botMember]
        vc = self._make_voice_client(channel = self.voiceChannel)
        self._seed_state(voiceClient = vc, isPlaying = True)
        await self.music.on_voice_state_update(listener, self._make_voice_state(self.voiceChannel), self._make_voice_state())
        vc.disconnect.assert_awaited_once()
        self.assertIsNone(self.music.musicStates[self.serverId]['voiceClient'])

    async def test_on_voice_state_update_keeps_playing_while_a_listener_remains(self):
        self._make_bot_client()
        listener = self._make_member(54321)
        botMember = self._make_member(77777, isBot = True)
        self.voiceChannel.members = [botMember, self._make_member(11223)]
        vc = self._make_voice_client(channel = self.voiceChannel)
        self._seed_state(voiceClient = vc, isPlaying = True)
        await self.music.on_voice_state_update(listener, self._make_voice_state(self.voiceChannel), self._make_voice_state())
        vc.disconnect.assert_not_called()

    async def test_on_voice_state_update_user_joining_another_channel_is_ignored(self):
        self._make_bot_client()
        listener = self._make_member(54321)
        otherChannel = Mock()
        otherChannel.id = 44444
        vc = self._make_voice_client(channel = self.voiceChannel)
        self._seed_state(voiceClient = vc, isPlaying = True)
        # before.channel is None — the old code would have had nothing to say, but the members
        # check must not dereference it either
        await self.music.on_voice_state_update(listener, self._make_voice_state(), self._make_voice_state(otherChannel))
        vc.disconnect.assert_not_called()
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

    #region cached_youtube_files
    async def test_cached_youtube_files_empty_noop(self):
        await self.music.cached_youtube_files.coro(self.music)

    async def test_cached_youtube_files_under_timeout_increments(self):
        self.music.cachedYouTubeFiles['song'] = {
            'filepath': '/tmp/song.mp3',
            'searchString': 'song',
            'url': 'http://example.com',
            'inactiveMinutes': 1,
            'lifetimeMinutes': 1
        }
        with patch('GBotDiscord.src.music.music_cog.os.path.exists', return_value = True):
            await self.music.cached_youtube_files.coro(self.music)
        self.assertEqual(self.music.cachedYouTubeFiles['song']['inactiveMinutes'], 2)
        self.assertEqual(self.music.cachedYouTubeFiles['song']['lifetimeMinutes'], 2)

    async def test_cached_youtube_files_over_timeout_removes_file(self):
        self.music.cachedYouTubeFiles['song'] = {
            'filepath': '/tmp/song.mp3',
            'searchString': 'song',
            'url': 'http://example.com',
            'inactiveMinutes': GBotPropertiesManager.MUSIC_CACHE_DELETION_TIMEOUT_MINUTES,
            'lifetimeMinutes': 10
        }
        with patch('GBotDiscord.src.music.music_cog.os.path.exists', return_value = True), \
             patch('GBotDiscord.src.music.music_cog.os.remove') as mockRemove:
            await self.music.cached_youtube_files.coro(self.music)
        mockRemove.assert_called_once_with('/tmp/song.mp3')
        self.assertNotIn('song', self.music.cachedYouTubeFiles)

    async def test_cached_youtube_files_missing_file_over_timeout_drops(self):
        self.music.cachedYouTubeFiles['song'] = {
            'filepath': '/tmp/missing.mp3',
            'searchString': 'song',
            'url': 'http://example.com',
            'inactiveMinutes': GBotPropertiesManager.MUSIC_CACHE_DELETION_TIMEOUT_MINUTES,
            'lifetimeMinutes': 10
        }
        with patch('GBotDiscord.src.music.music_cog.os.path.exists', return_value = False):
            await self.music.cached_youtube_files.coro(self.music)
        self.assertNotIn('song', self.music.cachedYouTubeFiles)

    async def test_cached_youtube_files_missing_file_under_timeout_keeps(self):
        self.music.cachedYouTubeFiles['song'] = {
            'filepath': '/tmp/missing.mp3',
            'searchString': 'song',
            'url': 'http://example.com',
            'inactiveMinutes': 0,
            'lifetimeMinutes': 0
        }
        with patch('GBotDiscord.src.music.music_cog.os.path.exists', return_value = False):
            await self.music.cached_youtube_files.coro(self.music)
        # entry remains because neither exists nor over timeout
        self.assertIn('song', self.music.cachedYouTubeFiles)

    async def test_cached_youtube_files_handles_exception(self):
        # poison cache so iteration raises; outer try/except must swallow
        self.music.cachedYouTubeFiles = None
        await self.music.cached_youtube_files.coro(self.music)
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
        self.music.searchYouTubeAndCacheDownload = AsyncMock(return_value = None)
        await self.music.commonPlay(self.interaction, self.author, ['test'], True)
        self.interaction.response.defer.assert_called_once()

    async def test_commonPlay_no_search_results(self):
        self._seed_state()
        voiceState = Mock()
        voiceState.channel = self.voiceChannel
        self.author.voice = voiceState
        self.music.searchYouTubeAndCacheDownload = AsyncMock(return_value = None)
        await self.music.commonPlay(self.ctx, self.author, ['test'])
        self.ctx.send.assert_called_with('Could not get the video sound. Try using share button to get video URL.')

    async def test_commonPlay_duration_too_long(self):
        self._seed_state()
        voiceState = Mock()
        voiceState.channel = self.voiceChannel
        self.author.voice = voiceState
        # 4 min duration vs 3 min cache timeout -> rejected
        self.music.searchYouTubeAndCacheDownload = AsyncMock(return_value = {'title': 'T', 'url': 'http://u', 'duration': 240})
        await self.music.commonPlay(self.ctx, self.author, ['test'])
        self.ctx.send.assert_called_with(f'Please play sounds less than {GBotPropertiesManager.MUSIC_CACHE_DELETION_TIMEOUT_MINUTES} minutes.')

    async def test_commonPlay_not_playing_starts(self):
        self._seed_state(isPlaying = False)
        voiceState = Mock()
        voiceState.channel = self.voiceChannel
        self.author.voice = voiceState
        self.music.searchYouTubeAndCacheDownload = AsyncMock(return_value = {'title': 'T', 'url': 'http://u', 'duration': 60})
        self.music.channelSync = AsyncMock()
        self.music.playMusic = MagicMock()
        await self.music.commonPlay(self.ctx, self.author, ['test'])
        self.assertEqual(len(self.music.musicStates[self.serverId]['queue']), 1)
        self.ctx.send.assert_called_with(f'Playing sound:\nT')
        self.music.channelSync.assert_called_once()
        self.music.playMusic.assert_called_once_with(self.serverId)

    async def test_commonPlay_already_playing_adds_to_queue(self):
        self._seed_state(isPlaying = True, isElevatorMode = False)
        voiceState = Mock()
        voiceState.channel = self.voiceChannel
        self.author.voice = voiceState
        self.music.searchYouTubeAndCacheDownload = AsyncMock(return_value = {'title': 'T', 'url': 'http://u', 'duration': 60})
        await self.music.commonPlay(self.ctx, self.author, ['test'])
        self.assertEqual(len(self.music.musicStates[self.serverId]['queue']), 1)
        self.ctx.send.assert_called_with('Sound added to the queue (1):\nT')

    # A-23's fix put an await (the threaded search) between reading isPlaying and acting on it,
    # so two /play commands in one guild can interleave. Without the per-guild lock both see
    # "not playing", both start playback, and the second raises "Already playing audio".
    async def test_commonPlay_concurrent_plays_start_playback_once(self):
        self._seed_state(isPlaying = False)
        voiceState = Mock()
        voiceState.channel = self.voiceChannel
        self.author.voice = voiceState

        async def searchOffTheLoop(searchString, isElevatorMode):
            await asyncio.sleep(0)
            return {'title': searchString, 'url': f'http://{searchString}', 'duration': 60}
        self.music.searchYouTubeAndCacheDownload = AsyncMock(side_effect = searchOffTheLoop)

        # connecting to voice yields too, which is where the second command used to slip in
        async def connectToVoice(serverId):
            await asyncio.sleep(0)
        self.music.channelSync = AsyncMock(side_effect = connectToVoice)

        def startPlaying(serverId):
            self.music.musicStates[serverId]['isPlaying'] = True
        self.music.playMusic = MagicMock(side_effect = startPlaying)

        await asyncio.gather(
            self.music.commonPlay(self.ctx, self.author, ['first']),
            self.music.commonPlay(self.ctx, self.author, ['second'])
        )
        self.music.playMusic.assert_called_once_with(self.serverId)
        self.ctx.send.assert_any_call('Playing sound:\nfirst')
        self.ctx.send.assert_any_call('Sound added to the queue (2):\nsecond')

    async def test_commonPlay_already_playing_in_elevator_rejects(self):
        self._seed_state(isPlaying = True, isElevatorMode = True)
        voiceState = Mock()
        voiceState.channel = self.voiceChannel
        self.author.voice = voiceState
        self.music.searchYouTubeAndCacheDownload = AsyncMock(return_value = {'title': 'T', 'url': 'http://u', 'duration': 60})
        await self.music.commonPlay(self.ctx, self.author, ['test'])
        self.ctx.send.assert_called_with("Please disable elevator mode to add songs to the queue.")
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
        self._seed_state(isPlaying = True, isElevatorMode = True, lastPlayed = {'url': 'u', 'name': 'NowPlaying', 'channel': None, 'searchString': 's'})
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
        self.assertEqual(fields[0]['value'], '`NowPlaying`')
        self.assertEqual(fields[1]['value'], '`Enabled`')
        self.assertEqual(fields[2]['value'], self.author.mention)

    async def test_commonQueue_with_queued_songs(self):
        song = {'source': 'http://u', 'title': 'Track1'}
        self._seed_state(isPlaying = False, queue = [[song, self.voiceChannel, 'track1']])
        with patch('GBotDiscord.src.music.music_cog.pagination.startPages', new = AsyncMock()), \
             patch('GBotDiscord.src.music.music_cog.pagination.CustomButtonMenuPages'), \
             patch('GBotDiscord.src.music.music_cog.pagination.DescriptionPageSource') as mockSrc:
            await self.music.commonQueue(self.ctx)
        data = mockSrc.call_args.args[0]
        # queued song appears in the data list
        self.assertTrue(any('Track1' in line for line in data))

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

    async def test_commonElevator_enable_with_current_song_caches(self):
        self._seed_state(isElevatorMode = False, lastPlayed = {'url': 'u', 'name': 'T', 'channel': self.voiceChannel, 'searchString': 'current'})
        self.music.searchYouTubeAndCacheDownload = AsyncMock()
        await self.music.commonElevator(self.ctx)
        self.music.searchYouTubeAndCacheDownload.assert_called_once_with('current', True)

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
        self.music.playMusic = MagicMock()
        await self.music.commonSkip(self.ctx, self.author)
        self.music.channelSync.assert_called_once_with(self.serverId)
        self.music.playMusic.assert_called_once_with(self.serverId)
        self.ctx.send.assert_called_with('Skipped.')

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

    #region searchYouTubeAndCacheDownload
    def _patch_ytdl(self, info = None, raises = False, downloadRaises = False):
        ydl = MagicMock()
        if raises:
            ydl.extract_info = MagicMock(side_effect = Exception("yt-dlp error"))
        else:
            ydl.extract_info = MagicMock(return_value = {'entries': [info]})
        if downloadRaises:
            ydl.download = MagicMock(side_effect = Exception("download error"))
        else:
            ydl.download = MagicMock()
        ydlCtx = MagicMock()
        ydlCtx.__enter__.return_value = ydl
        ydlCtx.__exit__.return_value = False
        return patch('GBotDiscord.src.music.music_cog.YoutubeDL', return_value = ydlCtx), ydl

    async def _drainCacheDownloads(self):
        # the cache download runs as a tracked task; let it finish before asserting on it
        await asyncio.gather(*self.music.cacheDownloadTasks)

    async def test_searchYouTubeAndCacheDownload_returns_info_non_elevator(self):
        info = {'title': 'Track', 'url': 'http://u', 'duration': 60}
        patcher, ydl = self._patch_ytdl(info = info)
        with patcher:
            result = await self.music.searchYouTubeAndCacheDownload('Track', False)
        self.assertEqual(result, info)
        # not elevator -> nothing cached, no download
        self.assertNotIn('Track', self.music.cachedYouTubeFiles)
        ydl.download.assert_not_called()

    async def test_searchYouTubeAndCacheDownload_elevator_caches_new_entry(self):
        info = {'title': 'Track', 'url': 'http://u', 'duration': 60}
        patcher, ydl = self._patch_ytdl(info = info)
        with patcher:
            result = await self.music.searchYouTubeAndCacheDownload('Track', True)
            await self._drainCacheDownloads()
        self.assertEqual(result, info)
        self.assertIn('Track', self.music.cachedYouTubeFiles)
        ydl.download.assert_called_once_with(['ytsearch:Track'])

    async def test_searchYouTubeAndCacheDownload_elevator_skip_when_already_cached(self):
        info = {'title': 'Track', 'url': 'http://u', 'duration': 60}
        # seed the cache so the new-cache branch is skipped
        self.music.cachedYouTubeFiles['Track'] = {'filepath': 'x', 'searchString': 'Track', 'url': 'http://u', 'inactiveMinutes': 0, 'lifetimeMinutes': 0}
        patcher, ydl = self._patch_ytdl(info = info)
        with patcher:
            result = await self.music.searchYouTubeAndCacheDownload('Track', True)
        self.assertEqual(result, info)
        self.assertEqual(self.music.cacheDownloadTasks, set())
        ydl.download.assert_not_called()

    async def test_searchYouTubeAndCacheDownload_returns_none_on_exception(self):
        patcher, _ydl = self._patch_ytdl(raises = True)
        with patcher:
            result = await self.music.searchYouTubeAndCacheDownload('Track', False)
        self.assertIsNone(result)

    # A-23: extract_info is a blocking network call and ran directly on the event loop, so the
    # whole bot — gateway and API — stalled for the duration of every /play.
    async def test_searchYouTubeAndCacheDownload_runs_the_search_off_the_event_loop(self):
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
            result = await self.music.searchYouTubeAndCacheDownload('Track', False)
        self.assertEqual(result, info)
        self.assertEqual(len(searchThreadIds), 1)
        self.assertNotEqual(searchThreadIds[0], loopThreadId)

    # A-19: the download was a bare Thread(target = ydl.download) started inside the caller's
    # `with YoutubeDL(...)` block, so the context manager closed the instance out from under the
    # running thread. The download now builds its own instance, off the event loop.
    async def test_cacheDownload_uses_its_own_ytdl_instance_off_the_event_loop(self):
        loopThreadId = threading.get_ident()
        downloadThreadIds = []

        def recordThread(*args, **kwargs):
            downloadThreadIds.append(threading.get_ident())
        ydl = MagicMock()
        ydl.download = MagicMock(side_effect = recordThread)
        ydlCtx = MagicMock()
        ydlCtx.__enter__.return_value = ydl
        ydlCtx.__exit__.return_value = False
        with patch('GBotDiscord.src.music.music_cog.YoutubeDL', return_value = ydlCtx) as mockYtdl:
            await self.music.cacheDownload('Track', 'Track')
        # its own instance, entered and exited inside the worker thread
        mockYtdl.assert_called_once()
        ydlCtx.__exit__.assert_called_once()
        self.assertEqual(len(downloadThreadIds), 1)
        self.assertNotEqual(downloadThreadIds[0], loopThreadId)

    # A-19: the thread was fire-and-forget — no join, no error path — so a failed download left a
    # cache entry pointing at a file that would never exist, and said nothing.
    async def test_cacheDownload_failure_is_logged_and_drops_the_cache_entry(self):
        self.music.cachedYouTubeFiles['Track'] = {'filepath': 'x', 'searchString': 'Track', 'url': 'http://u', 'inactiveMinutes': 0, 'lifetimeMinutes': 0}
        self.music.logger = MagicMock()
        patcher, _ydl = self._patch_ytdl(info = None, downloadRaises = True)
        with patcher:
            await self.music.cacheDownload('Track', 'Track')
        self.music.logger.error.assert_called_once()
        self.assertNotIn('Track', self.music.cachedYouTubeFiles)

    async def test_searchYouTubeAndCacheDownload_download_task_is_held_until_it_finishes(self):
        info = {'title': 'Track', 'url': 'http://u', 'duration': 60}
        patcher, _ydl = self._patch_ytdl(info = info)
        with patcher:
            await self.music.searchYouTubeAndCacheDownload('Track', True)
            # a task with no strong reference can be garbage collected mid-download
            self.assertEqual(len(self.music.cacheDownloadTasks), 1)
            await self._drainCacheDownloads()
            await asyncio.sleep(0)
        # the done callback releases it again
        self.assertEqual(self.music.cacheDownloadTasks, set())
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
            lastPlayed = {'url': 'u', 'name': 'T', 'channel': elevatorChannel, 'searchString': 's'}
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
            lastPlayed = {'url': 'u', 'name': 'T', 'channel': elevatorChannel, 'searchString': 's'}
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
    def test_playMusic_empty_queue_no_elevator_marks_idle(self):
        vc = self._make_voice_client()
        self._seed_state(isPlaying = True, voiceClient = vc, queue = [])
        self.music.playMusic(self.serverId)
        self.assertFalse(self.music.musicStates[self.serverId]['isPlaying'])
        vc.play.assert_not_called()

    def test_playMusic_no_voice_client_marks_idle_and_keeps_the_queue(self):
        song = {'source': 'http://u', 'title': 'T'}
        self._seed_state(isPlaying = True, voiceClient = None, queue = [[song, self.voiceChannel, 'q']])
        self.music.playMusic(self.serverId)
        self.assertFalse(self.music.musicStates[self.serverId]['isPlaying'])
        self.assertEqual(len(self.music.musicStates[self.serverId]['queue']), 1)

    # C-1 leaves a voiceClient that is non-None but was never connected, and the after callback
    # keeps firing after a kick or a /stop; playing into that client raised ClientException and
    # ate the queue entry.
    def test_playMusic_disconnected_voice_client_marks_idle_and_keeps_the_queue(self):
        vc = self._make_voice_client(is_connected = False)
        song = {'source': 'http://u', 'title': 'T'}
        self._seed_state(isPlaying = True, voiceClient = vc, queue = [[song, self.voiceChannel, 'q']])
        self.music.playMusic(self.serverId)
        vc.play.assert_not_called()
        self.assertFalse(self.music.musicStates[self.serverId]['isPlaying'])
        self.assertEqual(len(self.music.musicStates[self.serverId]['queue']), 1)

    def test_playMusic_already_playing_leaves_the_running_song_alone(self):
        # nextcord raises ClientException on a second play(); the running song's after callback
        # is what advances the queue
        vc = self._make_voice_client(is_playing = True)
        song = {'source': 'http://u', 'title': 'T'}
        self._seed_state(isPlaying = True, voiceClient = vc, queue = [[song, self.voiceChannel, 'q']])
        self.music.playMusic(self.serverId)
        vc.play.assert_not_called()
        self.assertEqual(len(self.music.musicStates[self.serverId]['queue']), 1)

    def test_playMusic_after_guild_removed_is_a_noop(self):
        # on_guild_remove popped the state while a song was playing; the after callback still fires
        self.music.playMusic(self.serverId)
        self.assertNotIn(self.serverId, self.music.musicStates)

    # A-18's sibling in playMusic: elevator mode on with an empty queue and nothing played yet
    # reached the queue branch and indexed queue[0].
    def test_playMusic_elevator_without_lastPlayed_and_empty_queue_marks_idle(self):
        vc = self._make_voice_client()
        self._seed_state(isPlaying = True, isElevatorMode = True, voiceClient = vc, queue = [])
        self.music.playMusic(self.serverId)
        vc.play.assert_not_called()
        self.assertFalse(self.music.musicStates[self.serverId]['isPlaying'])

    def test_playMusic_queue_item_plays_and_pops(self):
        song = {'source': 'http://u', 'title': 'T'}
        vc = self._make_voice_client()
        self._seed_state(voiceClient = vc, queue = [[song, self.voiceChannel, 'q']])
        with patch('GBotDiscord.src.music.music_cog.nextcord.FFmpegPCMAudio') as mockAudio:
            self.music.playMusic(self.serverId)
        vc.play.assert_called_once()
        mockAudio.assert_called_once()
        # queue popped
        self.assertEqual(len(self.music.musicStates[self.serverId]['queue']), 0)
        # lastPlayed populated
        self.assertEqual(self.music.musicStates[self.serverId]['lastPlayed']['name'], 'T')
        self.assertEqual(self.music.musicStates[self.serverId]['lastPlayed']['url'], 'http://u')
        self.assertTrue(self.music.musicStates[self.serverId]['isPlaying'])

    def test_playMusic_elevator_replays_lastPlayed_without_popping(self):
        vc = self._make_voice_client()
        song = {'source': 'http://other', 'title': 'Other'}
        lastPlayed = {'url': 'http://prev', 'name': 'Prev', 'channel': self.voiceChannel, 'searchString': 'prev'}
        self._seed_state(voiceClient = vc, isElevatorMode = True, queue = [[song, self.voiceChannel, 'q']], lastPlayed = lastPlayed)
        with patch('GBotDiscord.src.music.music_cog.nextcord.FFmpegPCMAudio'):
            self.music.playMusic(self.serverId)
        # queue not popped (elevator replays lastPlayed)
        self.assertEqual(len(self.music.musicStates[self.serverId]['queue']), 1)
        # lastPlayed unchanged
        self.assertEqual(self.music.musicStates[self.serverId]['lastPlayed']['name'], 'Prev')

    def test_playMusic_plays_from_cache_when_available(self):
        vc = self._make_voice_client()
        song = {'source': 'http://u', 'title': 'T'}
        self._seed_state(voiceClient = vc, queue = [[song, self.voiceChannel, 'q']])
        self.music.cachedYouTubeFiles['T'] = {
            'filepath': '/tmp/T.mp3',
            'searchString': 'q',
            'url': 'http://cached',
            'inactiveMinutes': 5,
            'lifetimeMinutes': 5
        }
        with patch('GBotDiscord.src.music.music_cog.nextcord.FFmpegPCMAudio') as mockAudio, \
             patch('GBotDiscord.src.music.music_cog.os.path.exists', return_value = True):
            self.music.playMusic(self.serverId)
        # cached entry reactivated and cached url used
        self.assertEqual(self.music.cachedYouTubeFiles['T']['inactiveMinutes'], 0)
        self.assertEqual(self.music.musicStates[self.serverId]['lastPlayed']['url'], 'http://cached')
        mockAudio.assert_called_once_with('/tmp/T.mp3')

    def test_playMusic_falls_back_to_url_when_cached_file_missing(self):
        vc = self._make_voice_client()
        song = {'source': 'http://u', 'title': 'T'}
        self._seed_state(voiceClient = vc, queue = [[song, self.voiceChannel, 'q']])
        self.music.cachedYouTubeFiles['T'] = {
            'filepath': '/tmp/missing.mp3',
            'searchString': 'q',
            'url': 'http://cached',
            'inactiveMinutes': 0,
            'lifetimeMinutes': 0
        }
        with patch('GBotDiscord.src.music.music_cog.nextcord.FFmpegPCMAudio') as mockAudio, \
             patch('GBotDiscord.src.music.music_cog.os.path.exists', return_value = False):
            self.music.playMusic(self.serverId)
        # url path used because cached file is missing
        self.assertEqual(self.music.musicStates[self.serverId]['lastPlayed']['url'], 'http://u')
        mockAudio.assert_called_once()

    # A-20: after=lambda e: self.playMusic(serverId) ran on ffmpeg's audio thread, mutating
    # musicStates off the event loop. Returning a coroutine is what makes nextcord submit the
    # work to the loop (run_coroutine_threadsafe) instead of running it there.
    async def test_playMusic_after_callback_returns_a_coroutine_for_the_event_loop(self):
        vc = self._make_voice_client()
        song = {'source': 'http://u', 'title': 'T'}
        self._seed_state(voiceClient = vc, queue = [[song, self.voiceChannel, 'q']])
        with patch('GBotDiscord.src.music.music_cog.nextcord.FFmpegPCMAudio'):
            self.music.playMusic(self.serverId)
        after = vc.play.call_args.kwargs['after']
        self.music.playMusic = MagicMock()
        advance = after(None)
        self.assertTrue(asyncio.iscoroutine(advance))
        # nothing has touched the state yet — it only runs once the loop awaits it
        self.music.playMusic.assert_not_called()
        await advance
        self.music.playMusic.assert_called_once_with(self.serverId)
    #endregion

    #region onSongFinished
    # A-20: the callback's error argument was discarded, so an ffmpeg failure was
    # indistinguishable from a song ending and silently advanced the queue.
    async def test_onSongFinished_logs_the_playback_error(self):
        self.music.logger = MagicMock()
        self.music.playMusic = MagicMock()
        await self.music.onSongFinished(self.serverId, Exception("ffmpeg exited"))
        self.music.logger.error.assert_called_once()
        self.music.playMusic.assert_called_once_with(self.serverId)

    async def test_onSongFinished_without_error_advances_quietly(self):
        self.music.logger = MagicMock()
        self.music.playMusic = MagicMock()
        await self.music.onSongFinished(self.serverId, None)
        self.music.logger.error.assert_not_called()
        self.music.playMusic.assert_called_once_with(self.serverId)
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
            queue = [[song, self.voiceChannel, 'q']],
            lastPlayed = {'url': 'u', 'name': 'T', 'channel': self.voiceChannel, 'searchString': 'q'}
        )
        await self.music.disconnectAndClearQueue(self.serverId)
        vc.disconnect.assert_called_once()
        state = self.music.musicStates[self.serverId]
        self.assertIsNone(state['voiceClient'])
        self.assertEqual(state['queue'], [])
        self.assertFalse(state['isPlaying'])
        self.assertFalse(state['isElevatorMode'])
        self.assertEqual(state['lastPlayed']['url'], '')
        self.assertEqual(state['lastPlayed']['name'], '')
        self.assertIsNone(state['lastPlayed']['channel'])
        self.assertEqual(state['lastPlayed']['searchString'], '')

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

    def test_init_creates_videos_dir_when_missing(self):
        # cover the makedirs call at line 29 — exists returns False so the directory is created
        self.exists_patcher.stop()
        self.makedirs_patcher.stop()
        with patch('GBotDiscord.src.music.music_cog.os.path.exists', return_value = False), \
             patch('GBotDiscord.src.music.music_cog.os.makedirs') as mockMakedirs:
            Music(self.client)
            mockMakedirs.assert_called_once()
        # restart the original patches so addCleanup teardown doesn't fail
        self.exists_patcher.start()
        self.makedirs_patcher.start()

    def test_setup_adds_cog(self):
        from GBotDiscord.src.music import music_cog
        client = MagicMock()
        music_cog.setup(client)
        client.add_cog.assert_called_once()
        addedCog = client.add_cog.call_args[0][0]
        self.assertIsInstance(addedCog, Music)


if __name__ == '__main__':
    unittest.main()
