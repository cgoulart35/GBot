#region IMPORTS
import asyncio
import threading
import unittest
from unittest.mock import MagicMock, Mock, AsyncMock, patch
import nextcord
from nextcord.ext import commands
from nextcord.ext.commands.context import Context
from datetime import datetime, timedelta
from decimal import Decimal

from GBotDiscord.src import utils
from GBotDiscord.src.config import config_queries
from GBotDiscord.src.firebase import GBotFirebaseService
from GBotDiscord.src.gcoin import gcoin_queries
from GBotDiscord.src.leaderboards import leaderboards_queries
from GBotDiscord.src.storms import storms_cog
from GBotDiscord.src.storms.storms_cog import Storms
from GBotDiscord.src import pagination
from GBotDiscord.test import isolation
from GBotDiscord.src.exceptions import EnforcePositiveTransactions, EnforceSenderFundsError, StormNotConfigured
from GBotDiscord.src.properties import GBotPropertiesManager
from GBotDiscord.test.card_assertions import assertErrorCard
from GBotDiscord.src import presentation
#endregion

# to run this test suite:
#   - execute the following command from the GBot directory: python -m unittest GBotDiscord/test/storms/storms_test.py
#   - or use the "Python: Current File" run configuration to run storms_test.py
#   - or use the "Python: Current File" run configuration to run tests.py to run all test suites
class TestStorms(unittest.IsolatedAsyncioTestCase):

    @classmethod
    def setUpClass(self):
        print('\nExecuting storms unit tests...\n')

    @classmethod
    def tearDownClass(self):
        print('\n\nCompleted storms unit tests.\n')

    def setUp(self):
        # the tests below replace this on the shared module
        self.addCleanup(setattr, presentation, 'sendEmbed', presentation.sendEmbed)
        GBotPropertiesManager.STORMS_MIN_TIME_BETWEEN_SECONDS = 3600
        GBotPropertiesManager.STORMS_MAX_TIME_BETWEEN_SECONDS = 14400
        GBotPropertiesManager.STORMS_DELETE_MESSAGES_AFTER_SECONDS = 60

        self.serverId = '99999'

        self.icon = Mock()
        self.icon.url = "icon url"

        self.author = Mock()
        self.author.id = 54321
        self.author.name = "author name"
        self.author.mention = "<@!54321>"
        self.author.bot = False
        self.author.send = AsyncMock()

        self.guild: nextcord.Guild = Mock()
        self.guild.id = int(self.serverId)
        self.guild.name = "guild name"
        self.guild.icon = self.icon

        self.stormChannel = Mock()
        self.stormChannel.id = 77777
        self.stormChannel.mention = "<#77777>"
        self.stormChannel.send = AsyncMock()
        self.stormChannel.delete_messages = AsyncMock()

        self.otherChannel = Mock()
        self.otherChannel.id = 88888
        self.otherChannel.mention = "<#88888>"
        self.otherChannel.send = AsyncMock()

        self.message = Mock()
        self.message.channel = self.stormChannel
        self.message.delete = AsyncMock()

        self.ctx: Context = Mock(spec = Context)
        self.ctx.guild = self.guild
        self.ctx.author = self.author
        self.ctx.channel = self.stormChannel
        self.ctx.send = AsyncMock()
        self.ctx.message = self.message

        self.interaction: nextcord.Interaction = Mock(spec = nextcord.Interaction)
        self.interaction.guild = self.guild
        self.interaction.user = self.author
        self.interaction.channel = self.stormChannel
        self.interaction.send = AsyncMock()
        self.interaction.response = Mock()
        self.interaction.response.defer = AsyncMock()

        self.client: nextcord.Client = commands.Bot()
        self.client.fetch_channel = AsyncMock(return_value = self.stormChannel)
        self.client.fetch_guild = AsyncMock(return_value = self.guild)

        self.storms: Storms = Storms(self.client)

        # freeze time so date strings are deterministic
        self.fixed_now = datetime(2024, 5, 15, 10, 30, 0)
        self.date = self.fixed_now.strftime("%m/%d/%y %I:%M:%S %p")
        self.datetime_patcher = patch('GBotDiscord.src.storms.storms_cog.datetime')
        mock_datetime = self.datetime_patcher.start()
        mock_datetime.now.return_value = self.fixed_now
        mock_datetime.strptime = datetime.strptime
        self.addCleanup(self.datetime_patcher.stop)

        # default mocks for isServerStormsConfigured -> configured + stormChannel
        config_queries.getServerValue = MagicMock(side_effect = lambda sid, key: {
            'toggle_storms': True,
            'channel_storms': str(self.stormChannel.id),
        }.get(key))

    def _seed_state(self, serverId = None, stormState = 0, triggerTime = None, generatedAtTime = None, winningNumber = 42, attemptsMap = None, fiveMinuteWarning = False, oneMinuteWarning = False, deleteReady = True, deleteMessages = None):
        serverId = serverId if serverId is not None else self.serverId
        self.storms.stormLocks[serverId] = asyncio.Lock()
        self.storms.stormStates[serverId] = {
            'stormState': stormState,
            'triggerTime': triggerTime if triggerTime is not None else self.date,
            'generatedAtTime': generatedAtTime if generatedAtTime is not None else self.date,
            'winningNumber': winningNumber,
            'attemptsMap': attemptsMap if attemptsMap is not None else {},
            'fiveMinuteWarning': fiveMinuteWarning,
            'oneMinuteWarning': oneMinuteWarning,
            'deleteReady': deleteReady,
            'deleteMessages': deleteMessages if deleteMessages is not None else [],
            'card': None,
            'startedBy': None,
            'hints': {}
        }

    #region on_guild_join / on_guild_remove
    async def test_on_guild_join_adds_lock_and_new_storm(self):
        # use a different server id so we don't collide with setup
        otherGuild = Mock()
        otherGuild.id = 12121
        otherGuild.name = "other"
        await self.storms.on_guild_join(otherGuild)
        self.assertIn(str(otherGuild.id), self.storms.stormLocks)
        self.assertIn(str(otherGuild.id), self.storms.stormStates)
        self.assertEqual(self.storms.stormStates[str(otherGuild.id)]['stormState'], 0)

    async def test_on_guild_remove_pops_state(self):
        self._seed_state()
        await self.storms.on_guild_remove(self.guild)
        self.assertNotIn(self.serverId, self.storms.stormLocks)
        self.assertNotIn(self.serverId, self.storms.stormStates)

    # A-14: pop() had no default, so leaving a guild that filterGuildsForInstance never
    # initialized raised KeyError inside the listener.
    async def test_on_guild_remove_uninitialized_guild_does_not_raise(self):
        await self.storms.on_guild_remove(self.guild)
        self.assertNotIn(self.serverId, self.storms.stormStates)
    #endregion

    #region on_ready
    async def test_on_ready_initializes_state_when_empty(self):
        self.storms.client = Mock(guilds = [self.guild])
        self.storms.storm_invoker.start = MagicMock()
        await self.storms.on_ready()
        self.assertIn(self.serverId, self.storms.stormStates)
        self.assertIn(self.serverId, self.storms.stormLocks)
        self.storms.storm_invoker.start.assert_called_once()

    async def test_on_ready_keeps_existing_state_and_adds_a_server_joined_while_offline(self):
        # this also fires on a reconnect: a storm in progress survives, and the newcomer gets state
        self._seed_state(stormState = 1)
        newGuild = Mock(id = int(self.serverId) + 1)
        self.storms.client = Mock(guilds = [self.guild, newGuild])
        self.storms.storm_invoker.start = MagicMock()
        await self.storms.on_ready()
        self.assertEqual(self.storms.stormStates[self.serverId]['stormState'], 1)
        self.assertIn(str(newGuild.id), self.storms.stormStates)

    async def test_on_ready_task_already_running(self):
        self._seed_state()
        self.storms.storm_invoker.start = MagicMock(side_effect = RuntimeError("already started"))
        await self.storms.on_ready()
        self.storms.storm_invoker.start.assert_called_once()
    #endregion

    #region storm_invoker
    async def test_storm_invoker_state0_not_yet_triggered(self):
        # trigger is in the future
        triggerTime = (self.fixed_now + timedelta(seconds = 60)).strftime("%m/%d/%y %I:%M:%S %p")
        self._seed_state(stormState = 0, triggerTime = triggerTime)
        await self.storms.storm_invoker.coro(self.storms)
        # state unchanged
        self.assertEqual(self.storms.stormStates[self.serverId]['stormState'], 0)

    async def test_storm_invoker_state0_triggers_and_starts_storm(self):
        # trigger was 5 seconds ago
        triggerTime = (self.fixed_now - timedelta(seconds = 5)).strftime("%m/%d/%y %I:%M:%S %p")
        self._seed_state(stormState = 0, triggerTime = triggerTime)
        await self.storms.storm_invoker.coro(self.storms)
        # state should advance to 1, with the incoming card posted
        self.assertEqual(self.storms.stormStates[self.serverId]['stormState'], 1)
        self.assertEqual(self.stormChannel.send.await_args.kwargs['embed'].title, '⛈️ Storm incoming!')

    async def test_storm_invoker_state0_triggered_but_not_configured_regenerates(self):
        triggerTime = (self.fixed_now - timedelta(seconds = 5)).strftime("%m/%d/%y %I:%M:%S %p")
        self._seed_state(stormState = 0, triggerTime = triggerTime, winningNumber = 42)
        # configure returns False
        self.client.fetch_channel = AsyncMock(side_effect = Exception("not found"))
        # generate uses random.randint — patch to deterministic
        with patch('GBotDiscord.src.storms.storms_cog.random') as mock_random:
            mock_random.randint = MagicMock(side_effect = [100, 7])  # first for delay seconds, second for winningNumber
            await self.storms.storm_invoker.coro(self.storms)
        # storm regenerated with new winning number
        self.assertEqual(self.storms.stormStates[self.serverId]['winningNumber'], 7)
        self.assertEqual(self.storms.stormStates[self.serverId]['stormState'], 0)

    async def test_storm_invoker_state0_delete_ready_triggers_purge(self):
        # not yet triggered (in the future), but generatedAtTime was long enough ago
        triggerTime = (self.fixed_now + timedelta(seconds = 600)).strftime("%m/%d/%y %I:%M:%S %p")
        generatedAt = (self.fixed_now - timedelta(seconds = 120)).strftime("%m/%d/%y %I:%M:%S %p")
        msg = Mock()
        self._seed_state(stormState = 0, triggerTime = triggerTime, generatedAtTime = generatedAt, deleteReady = True, deleteMessages = [msg])
        utils.purgePreviousMessages = AsyncMock()
        await self.storms.storm_invoker.coro(self.storms)
        utils.purgePreviousMessages.assert_called_once()

    async def test_storm_invoker_state1_five_minute_warning(self):
        # storm started 5+ minutes ago, no 5-min warning yet
        triggerTime = (self.fixed_now - timedelta(minutes = 5, seconds = 1)).strftime("%m/%d/%y %I:%M:%S %p")
        self._seed_state(stormState = 1, triggerTime = triggerTime, fiveMinuteWarning = False, oneMinuteWarning = False)
        presentation.sendEmbed = AsyncMock(return_value = Mock())
        await self.storms.storm_invoker.coro(self.storms)
        self.assertTrue(self.storms.stormStates[self.serverId]['fiveMinuteWarning'])
        presentation.sendEmbed.assert_called()

    async def test_storm_invoker_state1_one_minute_warning(self):
        # storm started 9+ minutes ago, 5-min already warned, no 1-min yet
        triggerTime = (self.fixed_now - timedelta(minutes = 9, seconds = 1)).strftime("%m/%d/%y %I:%M:%S %p")
        self._seed_state(stormState = 1, triggerTime = triggerTime, fiveMinuteWarning = True, oneMinuteWarning = False)
        presentation.sendEmbed = AsyncMock(return_value = Mock())
        await self.storms.storm_invoker.coro(self.storms)
        self.assertTrue(self.storms.stormStates[self.serverId]['oneMinuteWarning'])

    async def test_storm_invoker_state1_timeout_at_10_minutes(self):
        triggerTime = (self.fixed_now - timedelta(minutes = 10, seconds = 1)).strftime("%m/%d/%y %I:%M:%S %p")
        self._seed_state(stormState = 1, triggerTime = triggerTime, fiveMinuteWarning = True, oneMinuteWarning = True)
        presentation.sendEmbed = AsyncMock(return_value = Mock())
        await self.storms.storm_invoker.coro(self.storms)
        # state should be reset (generateNewStorm sets stormState back to 0)
        self.assertEqual(self.storms.stormStates[self.serverId]['stormState'], 0)

    async def test_storm_invoker_handles_exception(self):
        # malformed trigger time -> the per-guild try/except logs and swallows
        self._seed_state(stormState = 0, triggerTime = "not a date")
        await self.storms.storm_invoker.coro(self.storms)

    # used to abort the whole pass, so one guild's failure skipped every guild after it
    async def test_storm_invoker_one_guild_failing_does_not_skip_the_next(self):
        self.storms.logger = MagicMock()
        self.storms.stormStates['poisoned'] = {}
        self._seed_state(stormState = 1, triggerTime = (self.fixed_now - timedelta(minutes = 11)).strftime("%m/%d/%y %I:%M:%S %p"))
        self.storms.stormTimeout = AsyncMock()
        self.storms.isServerStormsConfigured = AsyncMock(return_value = (False, None))
        await self.storms.storm_invoker.coro(self.storms)
        self.storms.logger.error.assert_called_once()
        self.storms.stormTimeout.assert_awaited_once_with(self.serverId)

    # No send permission in the channel, say. It stayed pending and retried against Discord every
    # second, and because that raised out of the pass, every later guild lost its storms for good.
    async def test_storm_invoker_failed_start_schedules_a_new_storm(self):
        self.storms.logger = MagicMock()
        past = (self.fixed_now - timedelta(minutes = 1)).strftime("%m/%d/%y %I:%M:%S %p")
        self._seed_state(stormState = 0, triggerTime = past)
        self.storms.isServerStormsConfigured = AsyncMock(return_value = (True, Mock()))
        self.storms.startStorm = AsyncMock(side_effect = Exception('Missing Permissions'))
        await self.storms.storm_invoker.coro(self.storms)
        self.storms.logger.error.assert_called_once()
        self.assertEqual(self.storms.stormStates[self.serverId]['stormState'], 0)
        self.assertNotEqual(self.storms.stormStates[self.serverId]['triggerTime'], past)

    # A-13: the loop iterated stormStates.items() directly while awaiting, so a guild removed
    # mid-tick raised "dictionary changed size during iteration" and silently lost the tick.
    async def test_storm_invoker_survives_state_removed_mid_iteration(self):
        otherServerId = '11111'
        triggerTime = (self.fixed_now - timedelta(seconds = 5)).strftime("%m/%d/%y %I:%M:%S %p")
        self._seed_state(stormState = 0, triggerTime = triggerTime)
        self._seed_state(serverId = otherServerId, stormState = 0, triggerTime = triggerTime)
        presentation.sendEmbed = AsyncMock(return_value = Mock())

        # starting the first guild's storm removes the second guild's state, as on_guild_remove would
        originalStartStorm = self.storms.startStorm
        async def startStormAndRemoveOther(serverId, channel):
            self.storms.stormStates.pop(otherServerId, None)
            self.storms.stormLocks.pop(otherServerId, None)
            await originalStartStorm(serverId, channel)
        self.storms.startStorm = startStormAndRemoveOther
        self.storms.logger = MagicMock()

        await self.storms.storm_invoker.coro(self.storms)
        self.storms.logger.error.assert_not_called()
        self.assertNotIn(otherServerId, self.storms.stormStates)
        self.assertEqual(self.storms.stormStates[self.serverId]['stormState'], 1)
    #endregion

    #region commonUmbrella
    #endregion

    #region commonGuess
    #endregion

    #region commonBet
    async def test_win_and_umbrella_rewards_run_off_the_event_loop(self):
        threads = []
        def record(*args):
            threads.append(threading.current_thread())
        with patch.object(gcoin_queries, 'performTransaction', new = record), patch.object(leaderboards_queries, 'incrementUserNumValue', new = record):
            self.storms.stormStates[self.serverId] = {'attemptsMap': {}, 'deleteMessages': []}
            await GBotFirebaseService.run(self.storms.rewardUmbrella, 1, 'name')
            await GBotFirebaseService.run(self.storms.rewardWin, self.serverId, '1', 'name', None, 'date')
        self.assertTrue(threads)
        self.assertTrue(all(thread is not threading.main_thread() for thread in threads))

    #endregion

    #region guessNumber
    #endregion

    #region generateNewStorm
    def test_generateNewStorm_no_prior_state(self):
        with patch('GBotDiscord.src.storms.storms_cog.random') as mock_random:
            mock_random.randint = MagicMock(side_effect = [60, 123])
            self.storms.generateNewStorm(self.serverId)
        state = self.storms.stormStates[self.serverId]
        self.assertEqual(state['stormState'], 0)
        self.assertEqual(state['winningNumber'], 123)
        self.assertEqual(state['deleteMessages'], [])

    def test_generateNewStorm_with_prior_state_preserves_deleteMessages(self):
        existingMsg = Mock()
        self._seed_state(deleteMessages = [existingMsg])
        with patch('GBotDiscord.src.storms.storms_cog.random') as mock_random:
            mock_random.randint = MagicMock(side_effect = [60, 99])
            self.storms.generateNewStorm(self.serverId)
        self.assertEqual(self.storms.stormStates[self.serverId]['deleteMessages'], [existingMsg])

    def test_generateNewStorm_startNow_skips_random_delay(self):
        with patch('GBotDiscord.src.storms.storms_cog.random') as mock_random:
            mock_random.randint = MagicMock(side_effect = [55])  # only one call - for winningNumber
            self.storms.generateNewStorm(self.serverId, startNow = True)
        # trigger time should equal fixed_now
        self.assertEqual(self.storms.stormStates[self.serverId]['triggerTime'], self.date)
    #endregion

    #region startStorm
    #endregion

    #region stormTimeout
    #endregion

    #region completeStorm
    #endregion

    #region saveMessageForPurge
    def test_saveMessageForPurge_appends(self):
        self._seed_state()
        msg = Mock()
        self.storms.saveMessageForPurge(self.serverId, msg)
        self.assertIn(msg, self.storms.stormStates[self.serverId]['deleteMessages'])
    #endregion

    #region purgePreviousStormMessages
    async def test_purgePreviousStormMessages_empty_noop(self):
        self._seed_state()
        utils.purgePreviousMessages = AsyncMock()
        await self.storms.purgePreviousStormMessages(self.serverId, [])
        utils.purgePreviousMessages.assert_not_called()
        self.assertFalse(self.storms.stormStates[self.serverId]['deleteReady'])

    async def test_purgePreviousStormMessages_none_noop(self):
        self._seed_state()
        utils.purgePreviousMessages = AsyncMock()
        await self.storms.purgePreviousStormMessages(self.serverId, None)
        utils.purgePreviousMessages.assert_not_called()

    async def test_purgePreviousStormMessages_success(self):
        self._seed_state()
        utils.purgePreviousMessages = AsyncMock()
        msgs = [Mock()]
        await self.storms.purgePreviousStormMessages(self.serverId, msgs)
        utils.purgePreviousMessages.assert_called_once_with(msgs, self.stormChannel)
        # deleteMessages reset
        self.assertEqual(self.storms.stormStates[self.serverId]['deleteMessages'], [])

    async def test_purgePreviousStormMessages_not_configured(self):
        self._seed_state()
        config_queries.getServerValue = MagicMock(return_value = None)
        utils.sendMessageToAdmins = AsyncMock()
        msgs = [Mock()]
        await self.storms.purgePreviousStormMessages(self.serverId, msgs)
        utils.sendMessageToAdmins.assert_called_once()
        self.assertEqual(self.storms.stormStates[self.serverId]['deleteMessages'], [])

    async def test_purgePreviousStormMessages_purge_raises(self):
        self._seed_state()
        utils.purgePreviousMessages = AsyncMock(side_effect = Exception("denied"))
        utils.sendMessageToAdmins = AsyncMock()
        msgs = [Mock()]
        await self.storms.purgePreviousStormMessages(self.serverId, msgs)
        utils.sendMessageToAdmins.assert_called_once()
        self.assertEqual(self.storms.stormStates[self.serverId]['deleteMessages'], [])
    #endregion

    #region guess attempt helpers
    def test_getPlayerGuessCount_present(self):
        self._seed_state(attemptsMap = {'54321': 3})
        self.assertEqual(self.storms.getPlayerGuessCount(self.serverId, '54321'), 3)

    def test_getPlayerGuessCount_missing(self):
        self._seed_state()
        self.assertEqual(self.storms.getPlayerGuessCount(self.serverId, '54321'), 0)

    def test_recordGuessAttempt_increments(self):
        self._seed_state()
        self.storms.recordGuessAttempt(self.serverId, '54321')
        self.assertEqual(self.storms.stormStates[self.serverId]['attemptsMap']['54321'], 1)
        self.storms.recordGuessAttempt(self.serverId, '54321')
        self.assertEqual(self.storms.stormStates[self.serverId]['attemptsMap']['54321'], 2)
    #endregion

    #region applyMultiplier
    def test_applyMultiplier_tier1_first_guess(self):
        self._seed_state(attemptsMap = {'54321': 1})
        leaderboards_queries.incrementUserNumValue = MagicMock()
        result = self.storms.applyMultiplier(self.serverId, '54321', 'author', Decimal('1'))
        self.assertEqual(result, (Decimal('10.00'), 'x10'))
        leaderboards_queries.incrementUserNumValue.assert_called_once_with('54321', 'author', 'numStormTier1Multi')

    def test_applyMultiplier_tier2_second_guess(self):
        self._seed_state(attemptsMap = {'54321': 2})
        leaderboards_queries.incrementUserNumValue = MagicMock()
        result = self.storms.applyMultiplier(self.serverId, '54321', 'author', Decimal('1'))
        self.assertEqual(result, (Decimal('5.00'), 'x5'))
        leaderboards_queries.incrementUserNumValue.assert_called_once_with('54321', 'author', 'numStormTier2Multi')

    def test_applyMultiplier_tier3_third_guess(self):
        self._seed_state(attemptsMap = {'54321': 3})
        leaderboards_queries.incrementUserNumValue = MagicMock()
        result = self.storms.applyMultiplier(self.serverId, '54321', 'author', Decimal('1'))
        self.assertEqual(result, (Decimal('2.50'), 'x2.5'))

    def test_applyMultiplier_tier4_fourth_guess(self):
        self._seed_state(attemptsMap = {'54321': 4})
        leaderboards_queries.incrementUserNumValue = MagicMock()
        result = self.storms.applyMultiplier(self.serverId, '54321', 'author', Decimal('1'))
        self.assertEqual(result, (Decimal('1.25'), 'x1.25'))

    def test_applyMultiplier_no_multiplier_after_four_guesses(self):
        self._seed_state(attemptsMap = {'54321': 5})
        leaderboards_queries.incrementUserNumValue = MagicMock()
        result = self.storms.applyMultiplier(self.serverId, '54321', 'author', Decimal('1'))
        self.assertEqual(result, (Decimal('1.00'), 'x1'))
        # no statistic tracked at tier 5+
        leaderboards_queries.incrementUserNumValue.assert_not_called()
    #endregion

    #region isServerStormsConfigured
    async def test_isServerStormsConfigured_success(self):
        result = await self.storms.isServerStormsConfigured(self.serverId)
        self.assertEqual(result, (True, self.stormChannel))

    async def test_isServerStormsConfigured_fetch_channel_fails(self):
        self.client.fetch_channel = AsyncMock(side_effect = Exception("not found"))
        result = await self.storms.isServerStormsConfigured(self.serverId)
        self.assertEqual(result, (False, None))

    async def test_isServerStormsConfigured_disabled(self):
        config_queries.getServerValue = MagicMock(side_effect = lambda sid, key: {
            'toggle_storms': False,
            'channel_storms': str(self.stormChannel.id),
        }.get(key))
        result = await self.storms.isServerStormsConfigured(self.serverId)
        # toggle off -> False but channel still returned
        self.assertEqual(result[0], False)
        self.assertEqual(result[1], self.stormChannel)
    #endregion

    #region prefix command wrappers
    # Slash wrappers route through SlashApplicationCommand.__call__ which auto-binds parent_cog
    # and can't be invoked the same way; commonX paths are covered by direct calls above.
    #endregion


    async def test_storm_invoker_five_minute_warning_unconfigured_skips_embed(self):
        # 5-minute warning trigger fires but isServerStormsConfigured returns (False, None) —
        # covers the `if isConfigured[0]:` False branch on line 101
        triggerTime = (self.fixed_now - timedelta(minutes = 5, seconds = 1)).strftime("%m/%d/%y %I:%M:%S %p")
        self._seed_state(stormState = 1, triggerTime = triggerTime, fiveMinuteWarning = False, oneMinuteWarning = False)
        self.storms.isServerStormsConfigured = AsyncMock(return_value = (False, None))
        presentation.sendEmbed = AsyncMock(return_value = Mock())
        await self.storms.storm_invoker.coro(self.storms)
        # five-minute warning flag still flipped, but no embed sent
        self.assertTrue(self.storms.stormStates[self.serverId]['fiveMinuteWarning'])
        presentation.sendEmbed.assert_not_called()

    async def test_storm_invoker_one_minute_warning_unconfigured_skips_embed(self):
        triggerTime = (self.fixed_now - timedelta(minutes = 9, seconds = 1)).strftime("%m/%d/%y %I:%M:%S %p")
        self._seed_state(stormState = 1, triggerTime = triggerTime, fiveMinuteWarning = True, oneMinuteWarning = False)
        self.storms.isServerStormsConfigured = AsyncMock(return_value = (False, None))
        presentation.sendEmbed = AsyncMock(return_value = Mock())
        await self.storms.storm_invoker.coro(self.storms)
        self.assertTrue(self.storms.stormStates[self.serverId]['oneMinuteWarning'])
        presentation.sendEmbed.assert_not_called()

    def test_setup_adds_cog(self):
        from GBotDiscord.src.storms import storms_cog
        client = MagicMock()
        storms_cog.setup(client)
        client.add_cog.assert_called_once()
        addedCog = client.add_cog.call_args[0][0]
        self.assertIsInstance(addedCog, Storms)

    #region version 2: one live card, private hints
    def press(self, user = None, customId = None, kind = nextcord.InteractionType.component):
        interaction = Mock(spec = nextcord.Interaction)
        interaction.guild = self.guild
        interaction.user = user or self.author
        interaction.channel = self.stormChannel
        interaction.type = kind
        interaction.data = {'custom_id': customId} if customId else {}
        answered = []
        interaction.response = Mock(defer = AsyncMock(side_effect = lambda **kwargs: answered.append(True)), send_modal = AsyncMock(), send_message = AsyncMock(), is_done = Mock(side_effect = lambda: bool(answered)))
        interaction.send = AsyncMock()
        return interaction

    def live(self, stormState = 2, **kwargs):
        isolation.restorePagination()
        self._seed_state(stormState = stormState, **kwargs)
        self.card = Mock(edit = AsyncMock())
        self.storms.stormStates[self.serverId]['card'] = self.card
        self.author.display_name = 'Stormer'
        self.client.get_guild = Mock(return_value = self.guild)
        self.guild.get_member = Mock(side_effect = lambda userId: self.author if userId == self.author.id else None)
        patcher = patch.object(storms_cog.predicates, 'recheck', AsyncMock())
        self.recheck = patcher.start()
        self.addCleanup(patcher.stop)
        for name, value in (('performTransaction', MagicMock()), ('getUserBalance', MagicMock(return_value = Decimal('100')))):
            patcher = patch.object(gcoin_queries, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(leaderboards_queries, 'incrementUserNumValue', MagicMock())
        patcher.start()
        self.addCleanup(patcher.stop)
        return self.storms.stormStates[self.serverId]

    async def test_the_command_guesses_bets_or_puts_up_the_umbrella(self):
        self.live()
        with patch.object(self.storms, 'commonGuess', AsyncMock()) as commonGuess:
            await self.storms.stormsSlash(self.interaction, 42, '1,000.555')
            commonGuess.assert_awaited_with(self.interaction, self.interaction.user, 42, Decimal('1000.56'))
            await self.storms.storms.callback(self.storms, self.ctx, 7, None)
            commonGuess.assert_awaited_with(self.ctx, self.author, 7, None)
        await self.storms.commonStorms(self.ctx, self.author, None, Decimal('5'))
        assertErrorCard(self.ctx.send, f'Sorry {self.author.mention}, please give a number to bet on.')
        with patch.object(self.storms, 'commonUmbrella', AsyncMock()) as commonUmbrella:
            self.storms.stormStates[self.serverId]['stormState'] = 1
            await self.storms.commonStorms(self.ctx, self.author, None, None)
        commonUmbrella.assert_awaited_once_with(self.ctx, self.author)

    async def test_with_nothing_to_do_it_says_what_is_going_on(self):
        self.live()
        interaction = self.press(kind = nextcord.InteractionType.application_command)
        await self.storms.commonStorms(interaction, self.author, None, None)
        self.assertIn('A Storm is on', interaction.send.await_args.args[0])
        self.assertTrue(interaction.send.await_args.kwargs['ephemeral'])
        self.storms.stormStates[self.serverId]['stormState'] = 0
        await self.storms.commonStorms(self.ctx, self.author, None, None)
        self.assertEqual(self.ctx.send.await_args.args[0], '🌞 No Storm right now. They roll in every 1 to 4 hours.')
        # a prefix answer is cleared with the Storm's messages
        self.assertIn(self.ctx.send.return_value, self.storms.stormStates[self.serverId]['deleteMessages'])

    async def test_the_incoming_card(self):
        self.live(stormState = 0)
        await self.storms.startStorm(self.serverId, self.stormChannel)
        kwargs = self.stormChannel.send.await_args.kwargs
        self.assertEqual(kwargs['embed'].title, '⛈️ Storm incoming!')
        self.assertIn('**0.25 GCoin**', kwargs['embed'].description)
        self.assertIn(f'Ends <t:{int((self.fixed_now + timedelta(minutes = 10)).timestamp())}:R>.', kwargs['embed'].description)
        self.assertEqual([item.custom_id for item in kwargs['view'].children], ['storms:umbrella', 'storms:how'])
        self.assertTrue(kwargs['view'].is_finished())
        state = self.storms.stormStates[self.serverId]
        self.assertEqual(state['stormState'], 1)
        self.assertIs(state['card'], self.stormChannel.send.return_value)
        self.assertIn(state['card'], state['deleteMessages'])

    async def test_the_umbrella_starts_it_on_the_same_card(self):
        state = self.live(stormState = 1)
        interaction = self.press(customId = 'storms:umbrella')
        await self.storms.on_interaction(interaction)
        interaction.response.defer.assert_awaited_once_with(ephemeral = True)
        self.recheck.assert_awaited_with(interaction, feature = 'toggle_storms')
        self.assertEqual((state['stormState'], state['startedBy']), (2, self.author.id))
        embed = self.card.edit.await_args.kwargs['embed']
        self.assertEqual(embed.title, '🌧️ Storm in progress')
        self.assertEqual({field.name: field.value for field in embed.fields}, {'Players': 'Nobody has guessed yet.', 'Started by': f'<@{self.author.id}> ☂️'})
        self.assertEqual([item.custom_id for item in self.card.edit.await_args.kwargs['view'].children], ['storms:guess', 'storms:bet', 'storms:how'])
        self.assertEqual(interaction.send.await_args.args[0], f'☂️ {self.author.mention}, you started the Storm and earned **0.25 GCoin**!')
        gcoin_queries.performTransaction.assert_called_once()
        # too late, for anyone else
        interaction = self.press(customId = 'storms:umbrella')
        await self.storms.on_interaction(interaction)
        self.assertIn('already been started', interaction.send.await_args.kwargs['embed'].description)

    async def test_the_umbrella_typed_elsewhere_points_at_the_channel(self):
        self.live(stormState = 1)
        self.ctx.channel = self.otherChannel
        await self.storms.commonUmbrella(self.ctx, self.author)
        self.assertTrue(self.ctx.send.await_args.args[0].endswith(f' Guess in {self.stormChannel.mention}.'))
        # the typed message goes, or waits for the purge if it can't
        self.message.delete.assert_awaited_once()
        self.message.delete.side_effect = nextcord.Forbidden(Mock(status = 403, reason = 'no'), 'no')
        self.storms.stormStates[self.serverId]['stormState'] = 0
        await self.storms.commonUmbrella(self.ctx, self.author)
        self.assertIn('no active Storm', self.ctx.send.await_args.kwargs['embed'].description)
        self.assertIn(self.message, self.storms.stormStates[self.serverId]['deleteMessages'])

    async def test_not_configured_tells_the_admins(self):
        self.live(stormState = 1)
        config_queries.getServerValue = MagicMock(return_value = None)
        with patch.object(utils, 'sendMessageToAdmins', AsyncMock()) as sendMessageToAdmins:
            await self.storms.commonUmbrella(self.ctx, self.author)
            await self.storms.commonGuess(self.ctx, self.author, 5, Decimal('1'))
        self.assertEqual(sendMessageToAdmins.await_count, 2)
        self.assertIn("'s bet failed", sendMessageToAdmins.await_args.args[2])
        assertErrorCard(self.ctx.send, f'Sorry {self.author.mention}, Storms are not configured in this server.')

    async def test_a_wrong_guess_gets_a_private_hint_and_updates_the_card(self):
        state = self.live(winningNumber = 137)
        interaction = self.press(kind = nextcord.InteractionType.application_command)
        await self.storms.commonGuess(interaction, self.author, 42)
        interaction.response.defer.assert_awaited_once_with(ephemeral = True, with_message = False)
        self.assertEqual(interaction.send.await_args.args[0], '🎯 Not quite! **42** is too low ⬆️, so go higher. That was try 1, so a win on your next try pays x5.')
        self.assertTrue(interaction.send.await_args.kwargs['ephemeral'])
        self.assertEqual(self.card.edit.await_args.kwargs['embed'].fields[0].value, 'Stormer · 1 try')
        for _ in range(3):
            await self.storms.commonGuess(self.press(kind = nextcord.InteractionType.application_command), self.author, 150)
        interaction = self.press(kind = nextcord.InteractionType.application_command)
        await self.storms.commonGuess(interaction, self.author, 199)
        self.assertEqual(interaction.send.await_args.args[0], '🎯 Not quite! **199** is too high ⬇️, so go lower. That was try 5, so wins pay x1 from here.')
        self.assertEqual(state['attemptsMap'], {str(self.author.id): 5})

    async def test_a_typed_guess_shows_only_that_it_was_wrong(self):
        state = self.live(winningNumber = 137)
        await self.storms.commonGuess(self.ctx, self.author, 42)
        self.assertEqual(self.ctx.send.await_args.args[0], '❌ **Stormer** guessed wrong.')
        view = self.ctx.send.await_args.kwargs['view']
        self.assertEqual(view.children[0].custom_id, f'storms:hint:{self.author.id}')
        self.assertTrue(view.is_finished())
        self.assertIn('too low', state['hints'][self.author.id])
        self.message.delete.assert_awaited_once()
        interaction = self.press(customId = f'storms:hint:{self.author.id}')
        await self.storms.on_interaction(interaction)
        interaction.response.send_message.assert_awaited_once_with(state['hints'][self.author.id], ephemeral = True)
        someoneElse = Mock(id = 1, mention = '<@1>')
        interaction = self.press(someoneElse, f'storms:hint:{self.author.id}')
        await self.storms.on_interaction(interaction)
        self.assertIn('for whoever guessed', interaction.send.await_args.kwargs['embed'].description)
        # once the Storm is over the hint has gone with it
        self.storms.generateNewStorm(self.serverId)
        interaction = self.press(customId = f'storms:hint:{self.author.id}')
        await self.storms.on_interaction(interaction)
        interaction.response.send_message.assert_awaited_once_with('That hint is gone, as the Storm has moved on.', ephemeral = True)

    async def test_a_win_turns_the_card_into_the_result(self):
        self.live(winningNumber = 137, attemptsMap = {str(self.author.id): 1, '2': 3})
        interaction = self.press(kind = nextcord.InteractionType.application_command)
        await self.storms.commonGuess(interaction, self.author, 137)
        self.assertEqual(interaction.send.await_args.args[0], f'🎉 {self.author.mention}, you guessed it and won **5.00 GCoin**!')
        kwargs = self.card.edit.await_args.kwargs
        self.assertIsNone(kwargs['view'])
        self.assertEqual(kwargs['embed'].title, '🎉 Storm won! ⚡ x5')
        self.assertEqual(kwargs['embed'].description, f'{self.author.mention} guessed **137** on their 2nd try and won **5.00 GCoin**!')
        self.assertEqual(kwargs['embed'].fields[0].value, 'Someone · 3 tries\nStormer · 2 tries 🏆')
        self.assertEqual(self.storms.stormStates[self.serverId]['stormState'], 0)
        # typed, the win needs no hint button
        self.live(winningNumber = 7)
        await self.storms.commonGuess(self.ctx, self.author, 7)
        self.assertNotIn('view', self.ctx.send.await_args.kwargs)

    async def test_bets(self):
        self.live(winningNumber = 137)
        interaction = self.press(kind = nextcord.InteractionType.application_command)
        await self.storms.commonGuess(interaction, self.author, 42, Decimal('5'))
        self.assertTrue(interaction.send.await_args.args[0].startswith('💸 So close! You lost **5.00 GCoin**. **42** is too low'))
        self.assertEqual(gcoin_queries.performTransaction.call_args.args[4], 'Lost Bet')
        for amount, problem in ((Decimal('500'), 'insufficient funds'), (Decimal('0'), 'non-positive')):
            interaction = self.press(kind = nextcord.InteractionType.application_command)
            await self.storms.commonGuess(interaction, self.author, 42, amount)
            self.assertIn(problem, interaction.send.await_args.kwargs['embed'].description)
        # a refused bet counts for nothing
        self.assertEqual(self.storms.stormStates[self.serverId]['attemptsMap'], {str(self.author.id): 1})
        interaction = self.press(kind = nextcord.InteractionType.application_command)
        await self.storms.commonGuess(interaction, self.author, 137, Decimal('5'))
        self.assertEqual(self.card.edit.await_args.kwargs['embed'].title, '🎉 Storm won! ⚡ x5')

    async def test_guesses_need_a_storm_and_a_number_in_range(self):
        self.live(stormState = 1)
        interaction = self.press(kind = nextcord.InteractionType.application_command)
        await self.storms.commonGuess(interaction, self.author, 42)
        self.assertIn('no active Storm', interaction.send.await_args.kwargs['embed'].description)
        self.storms.stormStates[self.serverId]['stormState'] = 2
        await self.storms.commonGuess(interaction, self.author, 201)
        self.assertIn('from 1 to 200', interaction.send.await_args.kwargs['embed'].description)

    async def test_guess_and_bet_buttons_open_forms(self):
        self.live(winningNumber = 137)
        interaction = self.press(customId = 'storms:guess')
        await self.storms.on_interaction(interaction)
        form = interaction.response.send_modal.await_args.args[0]
        self.assertEqual((form.title, [box.label for box in form.inputs]), ('Guess the number', ['Your guess (1 to 200)']))
        with patch.object(self.storms, 'commonGuess', AsyncMock()) as commonGuess:
            submitted = self.press(kind = nextcord.InteractionType.modal_submit)
            await form.onSubmit(submitted, ['42'])
            submitted.response.defer.assert_awaited_once_with(ephemeral = True, with_message = True)
            commonGuess.assert_awaited_once_with(submitted, submitted.user, 42, None)
            interaction = self.press(customId = 'storms:bet')
            await self.storms.on_interaction(interaction)
            form = interaction.response.send_modal.await_args.args[0]
            self.assertEqual([box.label for box in form.inputs], ['Your guess (1 to 200)', 'GCoin to bet'])
            await form.onSubmit(self.press(kind = nextcord.InteractionType.modal_submit), ['42', '2.555'])
            commonGuess.assert_awaited_with(unittest.mock.ANY, unittest.mock.ANY, 42, Decimal('2.56'))
            submitted = self.press(kind = nextcord.InteractionType.modal_submit)
            await form.onSubmit(submitted, ['forty', 'lots'])
        self.assertIn('a whole number and a valid amount', submitted.send.await_args.kwargs['embed'].description)

    async def test_how_it_works_and_unknown_presses(self):
        self.live()
        interaction = self.press(customId = 'storms:how')
        await self.storms.on_interaction(interaction)
        embed = interaction.response.send_message.await_args.kwargs['embed']
        self.assertEqual(embed.title, '📖 How Storms work')
        self.assertIn('Umbrella', embed.description)
        await self.storms.on_interaction(self.press(customId = 'storms:dance'))
        await self.storms.on_interaction(self.press(customId = 'gtrade:buy:1'))
        with patch.object(self.storms, 'answerCardButton', AsyncMock(side_effect = KeyError('x'))), patch.object(storms_cog.presentation, 'sendInteractionError', AsyncMock()) as sendInteractionError:
            await self.storms.on_interaction(self.press(customId = 'storms:guess'))
        sendInteractionError.assert_awaited_once()

    async def test_a_storm_that_times_out_says_how_it_ended(self):
        self.live(stormState = 1)
        await self.storms.stormTimeout(self.serverId)
        embed = self.card.edit.await_args.kwargs['embed']
        self.assertEqual((embed.title, embed.description, embed.fields), ('🌞 Storm over', 'Nobody put up an umbrella this time.', []))
        self.assertEqual(self.storms.stormStates[self.serverId]['stormState'], 0)
        self.live(winningNumber = 99, attemptsMap = {str(self.author.id): 2})
        await self.storms.stormTimeout(self.serverId)
        embed = self.card.edit.await_args.kwargs['embed']
        self.assertEqual(embed.description, 'Nobody guessed it. The number was **99**.')
        self.assertEqual(embed.fields[0].value, 'Stormer · 2 tries')

    async def test_a_card_that_cannot_be_edited_is_only_logged(self):
        self.live()
        self.card.edit.side_effect = nextcord.NotFound(Mock(status = 404, reason = 'gone'), 'gone')
        with patch.object(self.storms.logger, 'error') as error:
            await self.storms.showCard(self.serverId)
            await self.storms.endCard(self.card, presentation.brandEmbed(title = 'x'))
        self.assertEqual(error.call_count, 2)
        self.storms.stormStates[self.serverId]['card'] = None
        await self.storms.showCard(self.serverId)
        await self.storms.endCard(None, None)

    async def test_the_players_list_stays_short(self):
        self.live(attemptsMap = {str(n): 1 for n in range(20)})
        self.client.get_guild = Mock(return_value = None)
        players = self.storms.describePlayers(self.serverId)
        self.assertEqual(players.count('\n'), 15)
        self.assertTrue(players.endswith('…and 5 more'))

    def test_the_api_leaves_out_what_is_not_data(self):
        self.assertEqual(Storms.STATE_NOT_SHOWN, ('deleteMessages', 'card', 'hints'))
    #endregion

if __name__ == '__main__':
    unittest.main()
