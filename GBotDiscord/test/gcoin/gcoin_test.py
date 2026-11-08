#region IMPORTS
import unittest
from unittest.mock import MagicMock, Mock, AsyncMock, patch
import nextcord
from nextcord.ext import commands
from nextcord.ext.commands.context import Context
from decimal import Decimal

from GBotDiscord.src import pagination
from GBotDiscord.src import presentation
from GBotDiscord.src import utils
from GBotDiscord.src.gcoin import gcoin_cog
from GBotDiscord.src.gcoin import gcoin_queries
from GBotDiscord.src.gcoin.gcoin_cog import GCoin, RankingPages, SendFlow, WalletCard
from GBotDiscord.src.leaderboards import leaderboards_queries
from GBotDiscord.src.firebase import GBotFirebaseService
from GBotDiscord.src.properties import GBotPropertiesManager
from GBotDiscord.src.exceptions import EnforcePositiveTransactions, EnforceRealUsersError, EnforceSenderFundsError, EnforceSenderReceiverNotEqual
from GBotDiscord.test import isolation
#endregion

# to run this test suite:
#   - execute the following command from the GBot directory: python -m unittest GBotDiscord/test/gcoin/gcoin_test.py
#   - or use the "Python: Current File" run configuration to run gcoin_test.py
#   - or use the "Python: Current File" run configuration to run tests.py to run all test suites

def member(userId, name, bot = False, avatar = None):
    found = Mock(id = userId, bot = bot, mention = f'<@{userId}>', display_name = name.capitalize(), avatar = avatar)
    found.name = name
    return found

REAL_PERFORM_TRANSACTION = gcoin_queries.performTransaction
REAL_VALIDATE_TRANSACTION = gcoin_queries.validateTransaction

HISTORY = {
    'a': {'date': '11/05/26 08:00:00 PM', 'gcoin': '+5.00', 'other': 'Storms', 'memo': 'x5'},
    'b': {'date': '11/06/26 08:00:00 PM', 'gcoin': '-10.00', 'other': 'GTrade', 'memo': 'Crafted Sword'},
    'c': {'date': '11/04/26 08:00:00 PM', 'gcoin': '+20.00', 'other': 'sam', 'memo': 'received'}
}

# ✖️ Close has no label, which nextcord keeps as MISSING
CLOSE = nextcord.utils.MISSING

class TestGCoin(unittest.IsolatedAsyncioTestCase):

    @classmethod
    def setUpClass(self):
        print('\nExecuting gcoin unit tests...\n')

    @classmethod
    def tearDownClass(self):
        print('\n\nCompleted gcoin unit tests.\n')

    def setUp(self):
        isolation.restorePagination()
        GBotPropertiesManager.GBOT_VERSION = '8.2'
        self.client: nextcord.Client = commands.Bot()
        self.gcoin: GCoin = GCoin(self.client)
        self.author = member(1, 'stormer', avatar = Mock(url = 'avatar url'))
        self.friend = member(2, 'sam')
        self.bot = member(3, 'gbot', bot = True)
        self.guild = Mock(id = 100, icon = Mock(url = 'icon url'))
        self.guild.members = [self.author, self.friend, self.bot]
        self.guild.get_member = Mock(side_effect = lambda userId: {1: self.author, 2: self.friend, 3: self.bot}.get(userId))
        self.balances = {'1': {'balance': '1250.50'}, '2': {'balance': '87.25'}, '9': {'balance': '4000'}}
        self.isAdmin = False
        for target, name, value in (
            (gcoin_queries, 'getUserBalance', MagicMock(side_effect = lambda userId: Decimal(self.balances.get(str(userId), {'balance': '0'})['balance']))),
            (gcoin_queries, 'getUserTransactionHistory', MagicMock(return_value = HISTORY)),
            (gcoin_queries, 'getAllUserBalances', MagicMock(side_effect = lambda: self.balances)),
            (leaderboards_queries, 'getLeaderboard', MagicMock(side_effect = lambda: self.balances)),
            (gcoin_queries, 'validateTransaction', MagicMock()),
            (gcoin_queries, 'performTransaction', MagicMock()),
            (utils, 'isUserAdminOrOwner', MagicMock(side_effect = lambda *args: self.isAdmin)),
            (gcoin_cog.predicates, 'recheck', AsyncMock()),
            (utils, 'isUserInThisGuildAndNotABot', AsyncMock(return_value = True))):
            patcher = patch.object(target, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def interaction(self, user = None, guild = 'default'):
        interaction = Mock(spec = nextcord.Interaction)
        interaction.user = user or self.author
        interaction.guild = self.guild if guild == 'default' else guild
        interaction.channel = Mock(id = 5, send = AsyncMock())
        answered = []
        interaction.response = Mock(defer = AsyncMock(side_effect = lambda **kwargs: answered.append(True)), send_modal = AsyncMock(), send_message = AsyncMock(), edit_message = AsyncMock(), is_done = Mock(side_effect = lambda: bool(answered)))
        interaction.send = AsyncMock()
        interaction.edit_original_message = AsyncMock()
        return interaction

    def prefix(self):
        ctx = Mock(spec = Context)
        ctx.guild = self.guild
        ctx.author = self.author
        ctx.send = AsyncMock()
        return ctx

    def labelled(self, view, label):
        return next(item for item in view.children if getattr(item, 'label', None) == label)

    async def openWallet(self, user = None, context = None):
        context = context or self.interaction()
        await self.gcoin.commonWallet(context, self.author, user)
        kwargs = context.send.await_args.kwargs
        return kwargs['embed'], kwargs['view'], kwargs

    #region the wallet
    async def test_the_command_and_the_right_click_open_a_wallet(self):
        with patch.object(self.gcoin, 'commonWallet', AsyncMock()) as commonWallet:
            interaction = self.interaction()
            await self.gcoin.gcoinSlash(interaction, self.friend)
            commonWallet.assert_awaited_with(interaction, interaction.user, self.friend)
            context = self.prefix()
            await self.gcoin.gcoin.callback(self.gcoin, context, None)
            commonWallet.assert_awaited_with(context, self.author, None)
            await self.gcoin.viewWallet(interaction, self.friend)
            commonWallet.assert_awaited_with(interaction, interaction.user, self.friend)

    async def test_your_own_wallet(self):
        embed, view, kwargs = await self.openWallet()
        self.assertTrue(kwargs['ephemeral'])
        self.assertEqual(embed.title, '💰 Your wallet')
        self.assertEqual(embed.description, '**1,250.50 GCoin**')
        self.assertEqual(embed.thumbnail.url, 'avatar url')
        fields = {field.name: field.value for field in embed.fields}
        self.assertEqual(fields, {'Last in': '`+5.00` Storms (x5)', 'Last out': '`-10.00` GTrade (Crafted Sword)', 'This server': '🥇 1st of 2'})
        self.assertEqual([item.label for item in view.children], ['Send', 'History', 'Ranking', CLOSE])

    async def test_someone_elses_wallet(self):
        embed, view, _ = await self.openWallet(self.friend)
        self.assertEqual(embed.title, "💰 Sam's wallet")
        self.assertIsNone(embed.thumbnail.url)
        self.assertEqual({field.name: field.value for field in embed.fields}, {'This server': '🥈 2nd of 2'})
        # their history is theirs, unless an admin asks
        self.assertEqual([item.label for item in view.children], ['Send to Sam', 'Ranking', CLOSE])
        self.isAdmin = True
        _, view, _ = await self.openWallet(self.friend)
        self.assertIn('History', [item.label for item in view.children])

    async def test_a_prefix_wallet_is_public_to_show_off(self):
        context = self.prefix()
        _, _, kwargs = await self.openWallet(context = context)
        self.assertNotIn('ephemeral', kwargs)

    async def test_ranks_further_down_and_nothing_yet(self):
        self.balances = {str(n): {'balance': str(100 - n)} for n in range(4, 10)} | {'1': {'balance': '1'}}
        self.guild.members = [member(n, f'm{n}') for n in range(4, 10)] + [self.author]
        gcoin_queries.getUserTransactionHistory.return_value = None
        embed, _, _ = await self.openWallet()
        fields = {field.name: field.value for field in embed.fields}
        self.assertEqual(fields['This server'], '7th of 7')
        self.assertEqual(fields['Last in'], 'Nothing yet')
        self.balances = {}
        embed, _, _ = await self.openWallet()
        self.assertEqual({field.name: field.value for field in embed.fields}['This server'], 'Not ranked yet')

    async def test_a_wallet_in_a_private_message(self):
        interaction = self.interaction(guild = None)
        embed, view, _ = await self.openWallet(context = interaction)
        self.assertNotIn('This server', [field.name for field in embed.fields])
        self.assertEqual([item.label for item in view.children], ['History', 'Ranking', CLOSE])
        interaction = self.interaction(guild = None)
        await self.gcoin.commonWallet(interaction, self.author, self.friend)
        self.assertIn('in a server', interaction.send.await_args.kwargs['embed'].description)

    async def test_a_wallet_for_someone_not_here_or_a_bot_is_refused(self):
        for user, inGuild in ((self.bot, False), (member(8, 'gone'), False)):
            interaction = self.interaction()
            with patch.object(utils, 'isUserInThisGuildAndNotABot', AsyncMock(return_value = inGuild)):
                await self.gcoin.commonWallet(interaction, self.author, user)
            self.assertIn('specify a user in this guild', interaction.send.await_args.kwargs['embed'].description)
            interaction.response.defer.assert_not_awaited()
        # asking for your own by name is just your own
        with patch.object(utils, 'isUserInThisGuildAndNotABot', AsyncMock(return_value = False)):
            embed, _, _ = await self.openWallet(self.author)
        self.assertEqual(embed.title, '💰 Your wallet')
    #endregion

    #region sending
    async def test_sending_from_your_own_wallet_picks_who_first(self):
        await self.startSending()

    async def startSending(self):
        _, card, _ = await self.openWallet()
        interaction = self.interaction()
        await self.labelled(card, 'Send').callback(interaction)
        kwargs = interaction.response.send_message.await_args.kwargs
        self.assertTrue(kwargs['ephemeral'])
        flow = kwargs['view']
        self.assertIsInstance(flow, SendFlow)
        self.assertEqual(kwargs['embed'].description, 'Who are you sending GCoin to?')
        picker = flow.children[0]
        self.assertIsInstance(picker, nextcord.ui.UserSelect)
        # yourself, or a bot, is refused on the spot
        for wrong, problem in ((self.author, 'yourself'), (self.bot, 'someone in this server')):
            pressed = self.interaction()
            await flow.pick(pressed, wrong)
            self.assertIn(problem, pressed.response.edit_message.await_args.kwargs['embed'].fields[-1].value)
        pressed = self.interaction()
        await flow.pick(pressed, self.friend)
        form = pressed.response.send_modal.await_args.args[0]
        self.assertEqual(form.title, 'Send to Sam')
        self.assertEqual([box.label for box in form.inputs], ['Amount of GCoin', 'Note (optional)'])
        self.assertFalse(form.inputs[1].required)
        return flow

    async def test_the_amount_is_confirmed_with_what_you_will_have_left(self):
        flow = await self.startSending()
        submitted = self.interaction()
        await flow.submitted(submitted, ['1,000.555', 'for snacks'])
        gcoin_cog.predicates.recheck.assert_awaited_with(submitted, feature = 'toggle_gcoin')
        embed = submitted.edit_original_message.await_args.kwargs['embed']
        self.assertEqual(embed.title, '💸 Send 1,000.56 GCoin to Sam?')
        self.assertEqual(embed.description, "You'll have **249.94 GCoin** left.\n> for snacks")
        self.assertEqual(embed.color, presentation.WARNING_COLOR)
        confirmed = self.interaction()
        await self.labelled(flow, 'Send').callback(confirmed)
        args = gcoin_queries.performTransaction.call_args.args
        self.assertEqual((args[0], args[2], args[3], args[4:]), (Decimal('1000.56'), {'id': 1, 'name': 'stormer'}, {'id': 2, 'name': 'sam'}, ('sent', 'received', True, True)))
        # the person receiving it has to be able to see it, so it's public
        confirmed.channel.send.assert_awaited_once_with('💸 <@1> sent <@2> **1,000.56 GCoin**.\n> for snacks')
        # a second click of the same Send moves nothing more
        again = self.interaction()
        await self.labelled(flow, 'Send').callback(again)
        gcoin_queries.performTransaction.assert_called_once()
        again.response.defer.assert_awaited_once()
        self.assertEqual(confirmed.edit_original_message.await_args.kwargs['content'], '💸 You sent <@2> **1,000.56 GCoin**.')

    async def test_a_bad_amount_or_too_little_goes_back_to_picking(self):
        flow = await self.startSending()
        for typed, error, problem in (('lots', None, 'valid amount'), ('NaN', None, 'valid amount'), ('5', EnforceSenderFundsError, 'insufficient funds'), ('-5', EnforcePositiveTransactions, 'non-positive'), ('5', EnforceRealUsersError, 'valid user'), ('5', EnforceSenderReceiverNotEqual, 'yourself')):
            gcoin_queries.validateTransaction.side_effect = error
            submitted = self.interaction()
            await flow.submitted(submitted, [typed, ''])
            embed = submitted.edit_original_message.await_args.kwargs['embed']
            self.assertEqual(embed.description, 'Who are you sending GCoin to?')
            self.assertIn(problem, embed.fields[-1].value)
        gcoin_queries.validateTransaction.side_effect = KeyError('x')
        with self.assertRaises(KeyError):
            await flow.submitted(self.interaction(), ['5', ''])

    async def test_cancelling_sends_nothing(self):
        flow = await self.startSending()
        await flow.submitted(self.interaction(), ['5', ''])
        cancelled = self.interaction()
        await self.labelled(flow, 'Cancel').callback(cancelled)
        cancelled.response.edit_message.assert_awaited_once_with(content = '🚫 Cancelled, so nothing was sent.', embed = None, view = None)
        gcoin_queries.performTransaction.assert_not_called()

    async def test_funds_gone_by_the_time_it_is_confirmed(self):
        flow = await self.startSending()
        await flow.submitted(self.interaction(), ['5', ''])
        gcoin_queries.performTransaction.side_effect = EnforceSenderFundsError()
        confirmed = self.interaction()
        await self.labelled(flow, 'Send').callback(confirmed)
        self.assertEqual(confirmed.edit_original_message.await_args.kwargs['content'], '❌ You have insufficient funds.')
        confirmed.channel.send.assert_not_awaited()

    async def test_a_failure_after_the_money_moved_is_not_a_bad_amount(self):
        # "please enter a valid amount" here would invite sending it a second time
        gcoin_queries.performTransaction.side_effect = RuntimeError('database went away')
        with self.assertRaises(RuntimeError):
            await self.gcoin.transfer(Mock(send = AsyncMock()), self.author, self.friend, Decimal('1'), '')

    async def test_an_announcement_that_fails_is_only_logged(self):
        channel = Mock(id = 5, send = AsyncMock(side_effect = nextcord.Forbidden(Mock(status = 403, reason = 'no'), 'no')))
        with patch.object(self.gcoin.logger, 'error') as error:
            self.assertIsNone(await self.gcoin.transfer(channel, self.author, self.friend, Decimal('1'), ''))
        error.assert_called_once()

    async def test_sending_from_someone_elses_wallet_goes_straight_to_the_amount(self):
        _, card, _ = await self.openWallet(self.friend)
        interaction = self.interaction()
        await self.labelled(card, 'Send to Sam').callback(interaction)
        form = interaction.response.send_modal.await_args.args[0]
        submitted = self.interaction()
        await form.onSubmit(submitted, ['5', ''])
        submitted.response.defer.assert_awaited_once_with(ephemeral = True, with_message = True)
        kwargs = submitted.send.await_args.kwargs
        self.assertTrue(kwargs['ephemeral'])
        self.assertEqual(kwargs['embed'].title, '💸 Send 5.00 GCoin to Sam?')
        self.assertIsInstance(kwargs['view'], SendFlow)

    async def test_send_from_a_wallet_that_is_not_theirs_to_send_to(self):
        # someone else pressing a public wallet's Send would be refused by the card, but a wallet for
        # someone who has since left can still be pressed by its owner
        _, card, _ = await self.openWallet(self.friend)
        self.guild.get_member = Mock(return_value = None)
        interaction = self.interaction()
        await self.labelled(card, 'Send to Sam').callback(interaction)
        interaction.response.send_modal.assert_not_awaited()
        self.assertIn('someone in this server', interaction.send.await_args.kwargs['embed'].description)

    def test_performTransaction_still_enforces_its_own_checks(self):
        with self.assertRaises(EnforcePositiveTransactions), patch.object(gcoin_queries, 'validateTransaction', REAL_VALIDATE_TRANSACTION):
            REAL_PERFORM_TRANSACTION(Decimal('0'), 'date', {'id': 1, 'name': 'a'}, {'id': 2, 'name': 'b'}, '', '')
    #endregion

    #region history and ranking
    async def test_history_from_the_wallet(self):
        _, card, _ = await self.openWallet()
        interaction = self.interaction()
        with patch.object(pagination, 'startPages', AsyncMock()) as startPages:
            await self.labelled(card, 'History').callback(interaction)
        interaction.response.defer.assert_awaited_once_with(ephemeral = True)
        gcoin_cog.predicates.recheck.assert_awaited_with(interaction, feature = 'toggle_gcoin', privateMessagesAllowed = True)
        pages = startPages.await_args.args[1]
        self.assertTrue(startPages.await_args.kwargs['ephemeral'])
        self.assertEqual(pages.source.title, "📜 stormer's Transaction History")
        self.assertEqual([entry[0] for entry in pages.source.entries], ['1. GTrade (Crafted Sword)', '2. Storms (x5)', '3. sam (received)'])
        self.assertEqual(pages.source.entries[0][1], '📉 `-10.00 GCoin`\n`11/06/26 08:00 PM`')

    async def test_someone_elses_history_is_for_admins(self):
        interaction = self.interaction()
        await self.gcoin.commonHistory(interaction, self.author, self.friend)
        self.assertIn('need to be an admin', interaction.send.await_args.kwargs['embed'].description)
        self.isAdmin = True
        gcoin_queries.getUserTransactionHistory.return_value = None
        await self.gcoin.commonHistory(interaction, self.author, self.friend)
        self.assertIn('<@2> has no transaction history', interaction.send.await_args.kwargs['embed'].description)
        await self.gcoin.commonHistory(interaction, self.author, None)
        self.assertIn('you have no transaction history', interaction.send.await_args.kwargs['embed'].description)

    async def test_history_shows_the_latest_hundred(self):
        gcoin_queries.getUserTransactionHistory.return_value = {str(n): {'date': f'11/0{1 + n % 9}/26 08:00:00 PM', 'gcoin': '+1', 'other': 'x', 'memo': 'y'} for n in range(150)}
        with patch.object(pagination, 'startPages', AsyncMock()) as startPages:
            await self.gcoin.commonHistory(self.interaction(), self.author, None)
        self.assertEqual(len(startPages.await_args.args[1].source.entries), 100)

    async def test_the_ranking_has_this_server_and_everywhere(self):
        board = {
            '1': {'username': 'stormer', 'balance': '1250.50', 'numStormWins': '12', 'numWhoDisWins': '0'},
            '9': {'username': 'kim', 'balance': '4000', 'numWhoDisWins': '3'},
            '8': {'username': 'broke', 'balance': '0'}}
        _, card, _ = await self.openWallet()
        interaction = self.interaction()
        board['2'] = {'username': 'sam', 'balance': '87.25'}
        with patch.object(leaderboards_queries, 'getLeaderboard', return_value = board), patch.object(pagination, 'startPages', AsyncMock()) as startPages:
            await self.labelled(card, 'Ranking').callback(interaction)
        pages = startPages.await_args.args[1]
        self.assertIsInstance(pages, RankingPages)
        self.assertEqual(pages.source.entries, ['🥇 **Stormer** · `1,250.50 GCoin`', '🥈 **Sam** · `87.25 GCoin`'])
        self.assertEqual(pages.sources['everywhere'].entries, ['🥇 **kim** · `4,000.00 GCoin` · ❓ 3', '🥈 **stormer** · `1,250.50 GCoin` · 🌧️ 12', '🥉 **sam** · `87.25 GCoin`'])
        await pages.render()
        self.assertEqual([item.label for item in pages.children][1:], ['This server', 'Everywhere', 'Website'])
        self.assertEqual(self.labelled(pages, 'Website').url, gcoin_cog.LEADERBOARD_URL)
        self.assertEqual(self.labelled(pages, 'This server').style, nextcord.ButtonStyle.primary)
        pressed = self.interaction()
        await self.labelled(pages, 'Everywhere').callback(pressed)
        self.assertEqual(pressed.response.edit_message.await_args.kwargs['embed'].title, '🏆 Ranking · Everywhere')
        self.assertEqual(self.labelled(pages, 'Everywhere').style, nextcord.ButtonStyle.primary)
        for row in pages.to_components():
            self.assertLessEqual(len(row['components']), 5)

    async def test_the_ranking_in_a_private_message_is_only_everywhere(self):
        with patch.object(leaderboards_queries, 'getLeaderboard', return_value = None), patch.object(pagination, 'startPages', AsyncMock()) as startPages:
            await self.gcoin.openRanking(self.interaction(guild = None))
        pages = startPages.await_args.args[1]
        self.assertEqual(list(pages.sources), ['everywhere'])
        # a single page still gets its tabs and link
        self.assertTrue(pages.needsControls())
        self.assertEqual((await pages.render()).description, 'Nobody has any GCoin yet.')
        self.assertNotIn('This server', [item.label for item in pages.children])
    #endregion

    def test_setup_adds_cog(self):
        client = MagicMock()
        gcoin_cog.setup(client)
        self.assertIsInstance(client.add_cog.call_args[0][0], GCoin)

if __name__ == '__main__':
    unittest.main()
