#region IMPORTS
import asyncio
import unittest
from unittest.mock import MagicMock, Mock, AsyncMock, patch
import nextcord
from nextcord.ext import commands
from nextcord.ext.commands.context import Context
from datetime import datetime, timedelta
from decimal import Decimal

from GBotDiscord.src import utils
from GBotDiscord.src.config import config_queries
from GBotDiscord.src.gcoin import gcoin_queries
from GBotDiscord.src.leaderboards import leaderboards_queries
from GBotDiscord.src.storms.storms_cog import Storms
from GBotDiscord.src.exceptions import EnforcePositiveTransactions, EnforceSenderFundsError, StormNotConfigured
from GBotDiscord.src.properties import GBotPropertiesManager
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
    #endregion

    #region on_ready
    async def test_on_ready_initializes_state_when_empty(self):
        utils.filterGuildsForInstance = MagicMock(return_value = {self.serverId: {}})
        config_queries.getAllServers = MagicMock(return_value = {self.serverId: {}})
        self.storms.storm_invoker.start = MagicMock()
        await self.storms.on_ready()
        self.assertIn(self.serverId, self.storms.stormStates)
        self.storms.storm_invoker.start.assert_called_once()

    async def test_on_ready_skips_init_when_state_exists(self):
        self._seed_state(stormState = 1)
        utils.filterGuildsForInstance = MagicMock()
        self.storms.storm_invoker.start = MagicMock()
        await self.storms.on_ready()
        # filterGuildsForInstance should not be called because stormStates is non-empty
        utils.filterGuildsForInstance.assert_not_called()
        # but the task is still started
        self.storms.storm_invoker.start.assert_called_once()
        # state preserved
        self.assertEqual(self.storms.stormStates[self.serverId]['stormState'], 1)

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
        utils.sendDiscordEmbed = AsyncMock(return_value = Mock())
        await self.storms.storm_invoker.coro(self.storms)
        # state should advance to 1
        self.assertEqual(self.storms.stormStates[self.serverId]['stormState'], 1)
        utils.sendDiscordEmbed.assert_called_once()

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
        utils.sendDiscordEmbed = AsyncMock(return_value = Mock())
        await self.storms.storm_invoker.coro(self.storms)
        self.assertTrue(self.storms.stormStates[self.serverId]['fiveMinuteWarning'])
        utils.sendDiscordEmbed.assert_called()

    async def test_storm_invoker_state1_one_minute_warning(self):
        # storm started 9+ minutes ago, 5-min already warned, no 1-min yet
        triggerTime = (self.fixed_now - timedelta(minutes = 9, seconds = 1)).strftime("%m/%d/%y %I:%M:%S %p")
        self._seed_state(stormState = 1, triggerTime = triggerTime, fiveMinuteWarning = True, oneMinuteWarning = False)
        utils.sendDiscordEmbed = AsyncMock(return_value = Mock())
        await self.storms.storm_invoker.coro(self.storms)
        self.assertTrue(self.storms.stormStates[self.serverId]['oneMinuteWarning'])

    async def test_storm_invoker_state1_timeout_at_10_minutes(self):
        triggerTime = (self.fixed_now - timedelta(minutes = 10, seconds = 1)).strftime("%m/%d/%y %I:%M:%S %p")
        self._seed_state(stormState = 1, triggerTime = triggerTime, fiveMinuteWarning = True, oneMinuteWarning = True)
        utils.sendDiscordEmbed = AsyncMock(return_value = Mock())
        await self.storms.storm_invoker.coro(self.storms)
        # state should be reset (generateNewStorm sets stormState back to 0)
        self.assertEqual(self.storms.stormStates[self.serverId]['stormState'], 0)

    async def test_storm_invoker_handles_exception(self):
        # malformed trigger time -> outer try/except logs and swallows
        self._seed_state(stormState = 0, triggerTime = "not a date")
        await self.storms.storm_invoker.coro(self.storms)
    #endregion

    #region commonUmbrella
    async def test_commonUmbrella_not_configured(self):
        self._seed_state()
        config_queries.getServerValue = MagicMock(return_value = None)
        utils.sendMessageToAdmins = AsyncMock()
        await self.storms.commonUmbrella(self.ctx, self.author)
        self.ctx.send.assert_any_call(f'Sorry {self.author.mention}, Storms are not configured in this server.')
        utils.sendMessageToAdmins.assert_called_once()

    async def test_commonUmbrella_state_0_no_active_storm(self):
        self._seed_state(stormState = 0)
        utils.sendDiscordEmbed = AsyncMock(return_value = Mock())
        await self.storms.commonUmbrella(self.ctx, self.author)
        self.ctx.send.assert_any_call(f'Sorry {self.author.mention}, there is currently no active Storm.')

    async def test_commonUmbrella_state_2_already_started(self):
        self._seed_state(stormState = 2)
        await self.storms.commonUmbrella(self.ctx, self.author)
        self.ctx.send.assert_any_call(f'Sorry {self.author.mention}, the Storm has already been started!')

    async def test_commonUmbrella_concurrent_callers_serialize_one_winner(self):
        # Regression for A-4: the lock was a threading.Lock acquired with blocking=False and
        # the result discarded, so a second concurrent umbrella ran unguarded — both callers
        # could observe stormState 1 and both get rewarded, and the loser's `finally` released
        # the winner's lock. With an asyncio.Lock the second caller waits, then sees state 2.
        self._seed_state(stormState = 1)
        leaderboards_queries.incrementUserNumValue = MagicMock()
        gcoin_queries.performTransaction = MagicMock()

        # yield control inside the critical section so the two calls genuinely interleave
        async def slowEmbed(*args, **kwargs):
            await asyncio.sleep(0)
            return Mock()
        utils.sendDiscordEmbed = AsyncMock(side_effect = slowEmbed)

        secondAuthor = Mock()
        secondAuthor.id = 99999
        secondAuthor.name = "second author"
        secondAuthor.mention = "<@!99999>"
        await asyncio.gather(
            self.storms.commonUmbrella(self.ctx, self.author),
            self.storms.commonUmbrella(self.ctx, secondAuthor),
        )

        # exactly one reward was handed out, and the loser was told it already started
        self.assertEqual(gcoin_queries.performTransaction.call_count, 1)
        self.assertEqual(leaderboards_queries.incrementUserNumValue.call_count, 1)
        self.assertEqual(self.storms.stormStates[self.serverId]['stormState'], 2)
        self.ctx.send.assert_any_call(f'Sorry {secondAuthor.mention}, the Storm has already been started!')

    async def test_commonUmbrella_state_1_starts_storm_in_configured_channel(self):
        self._seed_state(stormState = 1)
        leaderboards_queries.incrementUserNumValue = MagicMock()
        gcoin_queries.performTransaction = MagicMock()
        utils.sendDiscordEmbed = AsyncMock(return_value = Mock())
        await self.storms.commonUmbrella(self.ctx, self.author)
        # state advanced to 2
        self.assertEqual(self.storms.stormStates[self.serverId]['stormState'], 2)
        # rewarded + tracked
        leaderboards_queries.incrementUserNumValue.assert_called_once_with(self.author.id, self.author.name, 'numStormStarts')
        gcoin_queries.performTransaction.assert_called_once()
        utils.sendDiscordEmbed.assert_called_once()

    async def test_commonUmbrella_state_1_starts_storm_in_other_channel(self):
        self._seed_state(stormState = 1)
        self.ctx.channel = self.otherChannel
        leaderboards_queries.incrementUserNumValue = MagicMock()
        gcoin_queries.performTransaction = MagicMock()
        utils.sendDiscordEmbed = AsyncMock(return_value = Mock())
        await self.storms.commonUmbrella(self.ctx, self.author)
        # extra "please see your progress" message sent via context
        self.ctx.send.assert_any_call(f'{self.author.mention}, please see your progress in {self.stormChannel.mention}.')
        # embed was sent to configured channel (not ctx)
        utils.sendDiscordEmbed.assert_called_once()
        self.assertEqual(utils.sendDiscordEmbed.call_args.args[0], self.stormChannel)
    #endregion

    #region commonGuess
    async def test_commonGuess_not_configured(self):
        self._seed_state()
        config_queries.getServerValue = MagicMock(return_value = None)
        utils.sendMessageToAdmins = AsyncMock()
        await self.storms.commonGuess(self.ctx, self.author, 50)
        self.ctx.send.assert_any_call(f'Sorry {self.author.mention}, Storms are not configured in this server.')

    async def test_commonGuess_no_active_storm(self):
        self._seed_state(stormState = 0)
        await self.storms.commonGuess(self.ctx, self.author, 50)
        self.ctx.send.assert_any_call(f'Sorry {self.author.mention}, there is currently no active Storm.')

    async def test_commonGuess_no_active_storm_out_of_channel(self):
        self._seed_state(stormState = 0)
        self.ctx.channel = self.otherChannel
        await self.storms.commonGuess(self.ctx, self.author, 50)
        self.stormChannel.send.assert_any_call(f'Sorry {self.author.mention}, there is currently no active Storm.')

    async def test_commonGuess_state2_routes_to_guessNumber(self):
        self._seed_state(stormState = 2, winningNumber = 50)
        gcoin_queries.performTransaction = MagicMock()
        leaderboards_queries.incrementUserNumValue = MagicMock()
        utils.sendDiscordEmbed = AsyncMock(return_value = Mock())
        await self.storms.commonGuess(self.ctx, self.author, 50)
        # correct guess → performTransaction called for the reward
        gcoin_queries.performTransaction.assert_called_once()
    #endregion

    #region commonBet
    async def test_commonBet_not_configured(self):
        self._seed_state()
        config_queries.getServerValue = MagicMock(return_value = None)
        utils.sendMessageToAdmins = AsyncMock()
        await self.storms.commonBet(self.ctx, self.author, Decimal('5'), 50)
        self.ctx.send.assert_any_call(f'Sorry {self.author.mention}, Storms are not configured in this server.')

    async def test_commonBet_no_active_storm(self):
        self._seed_state(stormState = 0)
        await self.storms.commonBet(self.ctx, self.author, Decimal('5'), 50)
        self.ctx.send.assert_any_call(f'Sorry {self.author.mention}, there is currently no active Storm.')

    async def test_commonBet_insufficient_funds(self):
        self._seed_state(stormState = 2, winningNumber = 50)
        gcoin_queries.getUserBalance = MagicMock(return_value = Decimal('1'))
        await self.storms.commonBet(self.ctx, self.author, Decimal('10'), 50)
        self.ctx.send.assert_any_call(f'Sorry {self.author.mention}, you have insufficient funds.')

    async def test_commonBet_non_positive_caught(self):
        # zero or negative bet hits EnforcePositiveTransactions inside performTransaction
        self._seed_state(stormState = 2, winningNumber = 50)
        gcoin_queries.getUserBalance = MagicMock(return_value = Decimal('100'))
        leaderboards_queries.incrementUserNumValue = MagicMock()
        # correct guess path will call performTransaction which raises
        gcoin_queries.performTransaction = MagicMock(side_effect = EnforcePositiveTransactions)
        await self.storms.commonBet(self.ctx, self.author, Decimal('0'), 50)
        self.ctx.send.assert_any_call(f'Sorry {self.author.mention}, you can not bet a non-positive amount.')

    async def test_commonBet_success(self):
        self._seed_state(stormState = 2, winningNumber = 50)
        gcoin_queries.getUserBalance = MagicMock(return_value = Decimal('100'))
        gcoin_queries.performTransaction = MagicMock()
        leaderboards_queries.incrementUserNumValue = MagicMock()
        utils.sendDiscordEmbed = AsyncMock(return_value = Mock())
        await self.storms.commonBet(self.ctx, self.author, Decimal('5'), 50)
        gcoin_queries.performTransaction.assert_called_once()
    #endregion

    #region guessNumber
    async def test_guessNumber_correct_no_bet_first_guess_multiplier(self):
        self._seed_state(stormState = 2, winningNumber = 42)
        gcoin_queries.performTransaction = MagicMock()
        leaderboards_queries.incrementUserNumValue = MagicMock()
        utils.sendDiscordEmbed = AsyncMock(return_value = Mock())
        isConfigured = (True, self.stormChannel)
        await self.storms.guessNumber(self.ctx, isConfigured, True, self.serverId, self.author, 42)
        # numStormWins and numStormTier1Multi both incremented
        self.assertEqual(leaderboards_queries.incrementUserNumValue.call_count, 2)
        # reward = 1.00 * 10 (tier 1 multiplier) = 10.00
        gcoin_queries.performTransaction.assert_called_once()
        rewardArg = gcoin_queries.performTransaction.call_args.args[0]
        self.assertEqual(rewardArg, Decimal('10.00'))

    async def test_guessNumber_correct_with_bet(self):
        self._seed_state(stormState = 2, winningNumber = 42)
        gcoin_queries.getUserBalance = MagicMock(return_value = Decimal('100'))
        gcoin_queries.performTransaction = MagicMock()
        leaderboards_queries.incrementUserNumValue = MagicMock()
        utils.sendDiscordEmbed = AsyncMock(return_value = Mock())
        isConfigured = (True, self.stormChannel)
        # 5.00 bet * 10 (tier 1) = 50.00
        await self.storms.guessNumber(self.ctx, isConfigured, True, self.serverId, self.author, 42, Decimal('5.00'))
        rewardArg = gcoin_queries.performTransaction.call_args.args[0]
        self.assertEqual(rewardArg, Decimal('50.00'))

    async def test_guessNumber_bet_exceeds_balance_raises(self):
        self._seed_state(stormState = 2, winningNumber = 42)
        gcoin_queries.getUserBalance = MagicMock(return_value = Decimal('1'))
        with self.assertRaises(EnforceSenderFundsError):
            await self.storms.guessNumber(self.ctx, (True, self.stormChannel), True, self.serverId, self.author, 42, Decimal('10'))

    async def test_guessNumber_incorrect_no_bet_hint_greater_than(self):
        self._seed_state(stormState = 2, winningNumber = 100)
        # guess too low
        await self.storms.guessNumber(self.ctx, (True, self.stormChannel), True, self.serverId, self.author, 50)
        # message should hint "greater than 50"
        sentMsg = self.ctx.send.call_args.args[0]
        self.assertIn('greater than 50', sentMsg)

    async def test_guessNumber_incorrect_no_bet_hint_less_than(self):
        self._seed_state(stormState = 2, winningNumber = 25)
        # guess too high
        await self.storms.guessNumber(self.ctx, (True, self.stormChannel), True, self.serverId, self.author, 100)
        sentMsg = self.ctx.send.call_args.args[0]
        self.assertIn('less than 100', sentMsg)

    async def test_guessNumber_incorrect_with_bet_loses_gcoin(self):
        self._seed_state(stormState = 2, winningNumber = 100)
        gcoin_queries.getUserBalance = MagicMock(return_value = Decimal('50'))
        gcoin_queries.performTransaction = MagicMock()
        await self.storms.guessNumber(self.ctx, (True, self.stormChannel), True, self.serverId, self.author, 50, Decimal('5'))
        # losing bet → performTransaction called once for the loss
        gcoin_queries.performTransaction.assert_called_once()
        sentMsg = self.ctx.send.call_args.args[0]
        self.assertIn(f'lost 5 GCoin', sentMsg)

    async def test_guessNumber_incorrect_out_of_channel(self):
        self._seed_state(stormState = 2, winningNumber = 100)
        await self.storms.guessNumber(self.ctx, (True, self.stormChannel), False, self.serverId, self.author, 50)
        # message sent on the configured channel, not ctx
        self.stormChannel.send.assert_called_once()
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
    async def test_startStorm_with_icon(self):
        self._seed_state()
        utils.sendDiscordEmbed = AsyncMock(return_value = Mock())
        await self.storms.startStorm(self.serverId, self.stormChannel)
        self.assertEqual(self.storms.stormStates[self.serverId]['stormState'], 1)
        # last positional arg of sendDiscordEmbed is thumbnailUrl
        thumbnailUrl = utils.sendDiscordEmbed.call_args.args[6]
        self.assertEqual(thumbnailUrl, self.icon.url)

    async def test_startStorm_without_icon(self):
        self._seed_state()
        self.guild.icon = None
        utils.sendDiscordEmbed = AsyncMock(return_value = Mock())
        await self.storms.startStorm(self.serverId, self.stormChannel)
        thumbnailUrl = utils.sendDiscordEmbed.call_args.args[6]
        self.assertIsNone(thumbnailUrl)
    #endregion

    #region stormTimeout
    async def test_stormTimeout_regenerates_storm(self):
        self._seed_state(stormState = 2)
        utils.sendDiscordEmbed = AsyncMock(return_value = Mock())
        with patch('GBotDiscord.src.storms.storms_cog.random') as mock_random:
            mock_random.randint = MagicMock(side_effect = [60, 99])
            await self.storms.stormTimeout(self.serverId)
        # state reset to 0
        self.assertEqual(self.storms.stormStates[self.serverId]['stormState'], 0)
        # storm over message sent
        utils.sendDiscordEmbed.assert_called_once()

    async def test_stormTimeout_not_configured_skips_message(self):
        self._seed_state(stormState = 2)
        config_queries.getServerValue = MagicMock(return_value = None)
        utils.sendDiscordEmbed = AsyncMock(return_value = Mock())
        with patch('GBotDiscord.src.storms.storms_cog.random') as mock_random:
            mock_random.randint = MagicMock(side_effect = [60, 99])
            await self.storms.stormTimeout(self.serverId)
        utils.sendDiscordEmbed.assert_not_called()
    #endregion

    #region completeStorm
    async def test_completeStorm_in_configured_channel(self):
        self._seed_state(stormState = 2)
        utils.sendDiscordEmbed = AsyncMock(return_value = Mock())
        multiplierInfo = (Decimal('10.00'), 'x10')
        with patch('GBotDiscord.src.storms.storms_cog.random') as mock_random:
            mock_random.randint = MagicMock(side_effect = [60, 99])
            await self.storms.completeStorm(self.ctx, (True, self.stormChannel), True, self.serverId, self.author.mention, multiplierInfo)
        # storm is regenerated -> stormState reset to 0
        self.assertEqual(self.storms.stormStates[self.serverId]['stormState'], 0)
        self.ctx.send.assert_called_once_with(f'Congratulations {self.author.mention}, you guessed correctly and earned 10.00 points! (x10 applied)')

    async def test_completeStorm_out_of_configured_channel(self):
        self._seed_state(stormState = 2)
        utils.sendDiscordEmbed = AsyncMock(return_value = Mock())
        multiplierInfo = (Decimal('5.00'), 'x5')
        with patch('GBotDiscord.src.storms.storms_cog.random') as mock_random:
            mock_random.randint = MagicMock(side_effect = [60, 99])
            await self.storms.completeStorm(self.ctx, (True, self.stormChannel), False, self.serverId, self.author.mention, multiplierInfo)
        self.stormChannel.send.assert_called_once_with(f'Congratulations {self.author.mention}, you guessed correctly and earned 5.00 points! (x5 applied)')
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
    async def test_umbrella_prefix_delegates(self):
        self._seed_state(stormState = 0)
        await self.storms.umbrella(self.storms, self.ctx)
        self.ctx.send.assert_any_call(f'Sorry {self.author.mention}, there is currently no active Storm.')

    async def test_guess_prefix_delegates(self):
        self._seed_state(stormState = 0)
        await self.storms.guess(self.storms, self.ctx, 42)
        self.ctx.send.assert_any_call(f'Sorry {self.author.mention}, there is currently no active Storm.')

    async def test_bet_prefix_delegates(self):
        self._seed_state(stormState = 0)
        await self.storms.bet(self.storms, self.ctx, Decimal('5'), 42)
        self.ctx.send.assert_any_call(f'Sorry {self.author.mention}, there is currently no active Storm.')
    #endregion

    #region slash command wrappers (delegate to commonX)
    async def test_umbrellaSlash_delegates(self):
        self.storms.commonUmbrella = AsyncMock()
        await self.storms.umbrellaSlash(self.interaction)
        self.storms.commonUmbrella.assert_awaited_once_with(self.interaction, self.interaction.user)

    async def test_guessSlash_delegates(self):
        self.storms.commonGuess = AsyncMock()
        await self.storms.guessSlash(self.interaction, 42)
        self.storms.commonGuess.assert_awaited_once_with(self.interaction, self.interaction.user, 42)

    async def test_betSlash_delegates(self):
        self.storms.commonBet = AsyncMock()
        await self.storms.betSlash(self.interaction, 5, 42)
        self.storms.commonBet.assert_awaited_once_with(self.interaction, self.interaction.user, Decimal('5'), 42)
    #endregion

    async def test_commonUmbrella_state_0_out_of_channel(self):
        self._seed_state(stormState = 0)
        self.ctx.channel = self.otherChannel
        await self.storms.commonUmbrella(self.ctx, self.author)
        self.stormChannel.send.assert_any_call(f'Sorry {self.author.mention}, there is currently no active Storm.')

    async def test_commonUmbrella_state_2_out_of_channel(self):
        self._seed_state(stormState = 2)
        self.ctx.channel = self.otherChannel
        await self.storms.commonUmbrella(self.ctx, self.author)
        self.stormChannel.send.assert_any_call(f'Sorry {self.author.mention}, the Storm has already been started!')

    async def test_commonBet_no_active_storm_out_of_channel(self):
        self._seed_state(stormState = 0)
        self.ctx.channel = self.otherChannel
        await self.storms.commonBet(self.ctx, self.author, Decimal('5'), 50)
        self.stormChannel.send.assert_any_call(f'Sorry {self.author.mention}, there is currently no active Storm.')

    async def test_commonBet_insufficient_funds_out_of_channel(self):
        self._seed_state(stormState = 2, winningNumber = 50)
        self.ctx.channel = self.otherChannel
        gcoin_queries.getUserBalance = MagicMock(return_value = Decimal('1'))
        await self.storms.commonBet(self.ctx, self.author, Decimal('10'), 50)
        self.stormChannel.send.assert_any_call(f'Sorry {self.author.mention}, you have insufficient funds.')

    async def test_commonBet_non_positive_out_of_channel(self):
        self._seed_state(stormState = 2, winningNumber = 50)
        self.ctx.channel = self.otherChannel
        gcoin_queries.getUserBalance = MagicMock(return_value = Decimal('100'))
        leaderboards_queries.incrementUserNumValue = MagicMock()
        gcoin_queries.performTransaction = MagicMock(side_effect = EnforcePositiveTransactions)
        await self.storms.commonBet(self.ctx, self.author, Decimal('0'), 50)
        self.stormChannel.send.assert_any_call(f'Sorry {self.author.mention}, you can not bet a non-positive amount.')

    async def test_commonUmbrella_with_interaction_skips_message_purge(self):
        # Interaction context — `isinstance(context, Context)` False → skip the context.message save
        self._seed_state(stormState = 0)
        await self.storms.commonUmbrella(self.interaction, self.author)
        # check passes if no exception raised; no assertion needed on purge list

    async def test_commonGuess_with_interaction_skips_message_purge(self):
        self._seed_state(stormState = 0)
        await self.storms.commonGuess(self.interaction, self.author, 50)

    async def test_commonBet_with_interaction_skips_message_purge(self):
        self._seed_state(stormState = 0)
        await self.storms.commonBet(self.interaction, self.author, Decimal('5'), 50)

    async def test_storm_invoker_five_minute_warning_unconfigured_skips_embed(self):
        # 5-minute warning trigger fires but isServerStormsConfigured returns (False, None) —
        # covers the `if isConfigured[0]:` False branch on line 101
        triggerTime = (self.fixed_now - timedelta(minutes = 5, seconds = 1)).strftime("%m/%d/%y %I:%M:%S %p")
        self._seed_state(stormState = 1, triggerTime = triggerTime, fiveMinuteWarning = False, oneMinuteWarning = False)
        self.storms.isServerStormsConfigured = AsyncMock(return_value = (False, None))
        utils.sendDiscordEmbed = AsyncMock(return_value = Mock())
        await self.storms.storm_invoker.coro(self.storms)
        # five-minute warning flag still flipped, but no embed sent
        self.assertTrue(self.storms.stormStates[self.serverId]['fiveMinuteWarning'])
        utils.sendDiscordEmbed.assert_not_called()

    async def test_storm_invoker_one_minute_warning_unconfigured_skips_embed(self):
        triggerTime = (self.fixed_now - timedelta(minutes = 9, seconds = 1)).strftime("%m/%d/%y %I:%M:%S %p")
        self._seed_state(stormState = 1, triggerTime = triggerTime, fiveMinuteWarning = True, oneMinuteWarning = False)
        self.storms.isServerStormsConfigured = AsyncMock(return_value = (False, None))
        utils.sendDiscordEmbed = AsyncMock(return_value = Mock())
        await self.storms.storm_invoker.coro(self.storms)
        self.assertTrue(self.storms.stormStates[self.serverId]['oneMinuteWarning'])
        utils.sendDiscordEmbed.assert_not_called()

    def test_setup_adds_cog(self):
        from GBotDiscord.src.storms import storms_cog
        client = MagicMock()
        storms_cog.setup(client)
        client.add_cog.assert_called_once()
        addedCog = client.add_cog.call_args[0][0]
        self.assertIsInstance(addedCog, Storms)


if __name__ == '__main__':
    unittest.main()
