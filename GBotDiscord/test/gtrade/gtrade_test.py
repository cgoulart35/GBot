import threading
#region IMPORTS
import asyncio
import unittest
from unittest.mock import MagicMock, Mock, AsyncMock, patch
import nextcord
from nextcord.ext import commands
from nextcord.ext.commands.context import Context
from datetime import datetime, timedelta
from decimal import Decimal

from GBotDiscord.test.utils import AsyncIter
from GBotDiscord.src import utils
from GBotDiscord.src import pagination
from GBotDiscord.src.gtrade import gtrade_cog
from GBotDiscord.test import isolation
from GBotDiscord.src.gtrade import gtrade_queries
from GBotDiscord.src.gcoin import gcoin_queries
from GBotDiscord.src.gtrade.gtrade_cog import GTrade
from GBotDiscord.src.exceptions import ItemNoLongerAvailable, EnforceSenderFundsError, EnforceRealUsersError, EnforcePositiveTransactions, NotSubscribed
from GBotDiscord.src.properties import GBotPropertiesManager
from GBotDiscord.src.firebase import GBotFirebaseService
from GBotDiscord.test.card_assertions import assertErrorCard
from GBotDiscord.src import presentation
#endregion

# to run this test suite:
#   - execute the following command from the GBot directory: python -m unittest GBotDiscord/test/gtrade/gtrade_test.py
#   - or use the "Python: Current File" run configuration to run gtrade_test.py
#   - or use the "Python: Current File" run configuration to run tests.py to run all test suites
# other suites and this one replace these with mocks and never restore them
_REAL_PERFORM_TRANSACTION = gcoin_queries.performTransaction
_REAL_PARTY_CHANGES = gcoin_queries.partyChanges
_REAL_CREATE_ITEM_CHANGES = gtrade_queries.createItemChanges
_REAL_REMOVE_ITEM_CHANGES = gtrade_queries.removeItemChanges
_REAL_REMOVE_RELATED_CHANGES = gtrade_queries.removeRelatedPendingTradeTransactionsChanges

class TestGTrade(unittest.IsolatedAsyncioTestCase):

    @classmethod
    def setUpClass(self):
        print('\nExecuting gtrade unit tests...\n')

    @classmethod
    def tearDownClass(self):
        print('\n\nCompleted gtrade unit tests.\n')

    async def craft(self, name, value, imageUrl = None):
        # what the prefix command used to do: an image attached to the message, or a link
        attachments = self.ctx.message.attachments if isinstance(getattr(self.ctx.message, 'attachments', None), list) else []
        await self.gtrade.commonCraft(self.ctx, self.ctx.author, name, value, attachments[0] if attachments else None, imageUrl)

    async def destroy(self, context, author, item):
        # what the card's 💥 Destroy does once it is confirmed: the trade lock, then the destroy
        async with self.gtrade.tradeLock:
            text = await self.gtrade.destroyUnderLock(author, item)
        await context.send(text)
        return text

    def setUp(self):
        # the money step is mocked per test; the check in front of it has its own tests below
        self._realValidate = gcoin_queries.validateTransaction
        gcoin_queries.validateTransaction = MagicMock()
        self.addCleanup(setattr, gcoin_queries, 'validateTransaction', self._realValidate)
        gtrade_queries.getPendingTradeTransactionWithId = MagicMock(return_value = {'trxType': 'market'})
        GBotPropertiesManager.USER_RESPONSE_TIMEOUT_SECONDS = 300
        GBotPropertiesManager.GTRADE_MARKET_SALE_TIMEOUT_HOURS = 3
        GBotPropertiesManager.GTRADE_TRANSACTION_REQUEST_TIMEOUT_MINUTES = 5

        self.avatar = Mock()
        self.avatar.url = "avatar url"

        self.icon = Mock()
        self.icon.url = "icon url"

        self.author = Mock()
        self.author.id = 54321
        self.author.name = "author name"
        self.author.mention = "<@!54321>"
        self.author.bot = False
        self.author.avatar = self.avatar

        self.user = Mock()
        self.user.id = 12345
        self.user.name = "user name"
        self.user.mention = "<@!12345>"
        self.user.bot = False
        self.user.avatar = self.avatar

        self.guild: nextcord.Guild = Mock()
        self.guild.id = 99999
        self.guild.name = "guild name"
        self.guild.icon = self.icon
        self.guild.get_member = MagicMock(side_effect = lambda uid: self.author if uid == self.author.id else self.user)
        self.guild.fetch_members = MagicMock(return_value = AsyncIter([self.author, self.user]))

        self.channel = Mock()
        self.channel.id = 88888
        self.channel.send = AsyncMock()

        self.ctx: Context = Mock()
        self.ctx.guild = self.guild
        self.ctx.author = self.author
        self.ctx.channel = self.channel
        self.ctx.send = AsyncMock()

        self.interaction: nextcord.Interaction = Mock(spec = nextcord.Interaction)
        self.interaction.guild = self.guild
        self.interaction.user = self.author
        self.interaction.channel = self.channel
        self.interaction.send = AsyncMock()
        self.interaction.response = Mock()
        self.interaction.response.defer = AsyncMock()
        self.interaction.response.send_autocomplete = AsyncMock()

        self.client: nextcord.Client = commands.Bot()
        self.client.fetch_channel = AsyncMock(return_value = self.channel)
        # in every guild by default; only the other-bot test takes this away
        self.client.get_guild = MagicMock(return_value = self.guild)

        self.gtrade: GTrade = GTrade(self.client)
        self.ctx.message = Mock(attachments = [])

        # default async util mocks; individual tests can override
        utils.isUserInThisGuildAndNotABot = AsyncMock(return_value = True)
        utils.isUrlImageContentTypeAndStatus200 = AsyncMock(return_value = True)
        utils.getServerPrefixOrDefault = MagicMock(return_value = '.')

        # freeze time so date strings are deterministic
        self.fixed_now = datetime(2024, 5, 15, 10, 30, 0)
        self.date = self.fixed_now.strftime("%m/%d/%y %I:%M:%S %p")
        self.datetime_patcher = patch('GBotDiscord.src.gtrade.gtrade_cog.datetime')
        mock_datetime = self.datetime_patcher.start()
        mock_datetime.now.return_value = self.fixed_now
        mock_datetime.strptime = datetime.strptime
        self.addCleanup(self.datetime_patcher.stop)

    def _make_item(self, name = "sword", value = "5.00", originalName = None, originalValue = None, originalCreator = None, originalServer = "guild name", dateCreated = None, dataType = "image", dataJson = None):
        return {
            'name': name,
            'value': value,
            'originalName': originalName if originalName is not None else name,
            'originalValue': originalValue if originalValue is not None else value,
            'originalCreator': originalCreator if originalCreator is not None else self.author.name,
            'originalServer': originalServer,
            'dateCreated': dateCreated if dateCreated is not None else self.date,
            'dateObtained': self.date,
            'dataType': dataType,
            'dataJson': dataJson if dataJson is not None else {'imageUrl': 'http://example.com/img.png'}
        }

    # region Events
    async def test_on_guild_remove(self):
        gtrade_queries.removeAllServerPendingTradeTransaction = MagicMock()
        await self.gtrade.on_guild_remove(self.guild)
        gtrade_queries.removeAllServerPendingTradeTransaction.assert_called_once_with(self.guild.id)

    async def test_on_ready_starts_task(self):
        self.gtrade.remove_expired_transactions.start = MagicMock()
        await self.gtrade.on_ready()
        self.gtrade.remove_expired_transactions.start.assert_called_once()

    async def test_on_ready_already_running(self):
        # if task is already running, RuntimeError is swallowed and logged
        self.gtrade.remove_expired_transactions.start = MagicMock(side_effect = RuntimeError("already started"))
        await self.gtrade.on_ready()
        self.gtrade.remove_expired_transactions.start.assert_called_once()
    # endregion

    # region remove_expired_transactions
    async def test_remove_expired_transactions_no_transactions(self):
        gtrade_queries.getAllTradeTransactions = MagicMock(return_value = None)
        gtrade_queries.removePendingTradeTransaction = MagicMock()
        await self.gtrade.remove_expired_transactions.coro(self.gtrade)
        gtrade_queries.removePendingTradeTransaction.assert_not_called()
        self.channel.send.assert_not_called()

    async def test_remove_expired_transactions_market_not_expired(self):
        # posted 1 hour ago, timeout is 3 hours
        timePosted = (self.fixed_now - timedelta(hours = 1)).strftime("%m/%d/%y %I:%M:%S %p")
        gtrade_queries.getAllTradeTransactions = MagicMock(return_value = {
            str(self.guild.id): {
                'trx1': {
                    'trxType': 'market',
                    'item': {'name': 'sword'},
                    'timePosted': timePosted,
                    'sourceChannelId': str(self.channel.id),
                    'sellerId': str(self.author.id)
                }
            }
        })
        gtrade_queries.removePendingTradeTransaction = MagicMock()
        await self.gtrade.remove_expired_transactions.coro(self.gtrade)
        gtrade_queries.removePendingTradeTransaction.assert_not_called()
        self.channel.send.assert_not_called()

    async def test_remove_expired_transactions_market_expired(self):
        # posted 4 hours ago, timeout is 3 hours
        timePosted = (self.fixed_now - timedelta(hours = 4)).strftime("%m/%d/%y %I:%M:%S %p")
        gtrade_queries.getAllTradeTransactions = MagicMock(return_value = {
            str(self.guild.id): {
                'trx1': {
                    'trxType': 'market',
                    'item': {'name': 'sword'},
                    'timePosted': timePosted,
                    'sourceChannelId': str(self.channel.id),
                    'sellerId': str(self.author.id)
                }
            }
        })
        gtrade_queries.removePendingTradeTransaction = MagicMock()
        await self.gtrade.remove_expired_transactions.coro(self.gtrade)
        gtrade_queries.removePendingTradeTransaction.assert_called_once_with(str(self.guild.id), 'trx1')
        assertErrorCard(self.channel.send, f"Sorry {utils.idToUserStr(self.author.id)}, your market sale for 'sword' has expired after 3 hours.")

    async def test_remove_expired_transactions_buy_request_not_expired(self):
        # posted 2 minutes ago, timeout is 5 minutes
        timePosted = (self.fixed_now - timedelta(minutes = 2)).strftime("%m/%d/%y %I:%M:%S %p")
        gtrade_queries.getAllTradeTransactions = MagicMock(return_value = {
            str(self.guild.id): {
                'trx1': {
                    'trxType': 'buy',
                    'item': {'name': 'sword'},
                    'timePosted': timePosted,
                    'sourceChannelId': str(self.channel.id),
                    'buyerId': str(self.author.id),
                    'sellerId': str(self.user.id)
                }
            }
        })
        gtrade_queries.removePendingTradeTransaction = MagicMock()
        await self.gtrade.remove_expired_transactions.coro(self.gtrade)
        gtrade_queries.removePendingTradeTransaction.assert_not_called()

    async def test_remove_expired_transactions_buy_request_expired(self):
        # posted 10 minutes ago, timeout is 5 minutes; buy request notifies the buyer
        timePosted = (self.fixed_now - timedelta(minutes = 10)).strftime("%m/%d/%y %I:%M:%S %p")
        gtrade_queries.getAllTradeTransactions = MagicMock(return_value = {
            str(self.guild.id): {
                'trx1': {
                    'trxType': 'buy',
                    'item': {'name': 'sword'},
                    'timePosted': timePosted,
                    'sourceChannelId': str(self.channel.id),
                    'buyerId': str(self.author.id),
                    'sellerId': str(self.user.id)
                }
            }
        })
        gtrade_queries.removePendingTradeTransaction = MagicMock()
        await self.gtrade.remove_expired_transactions.coro(self.gtrade)
        gtrade_queries.removePendingTradeTransaction.assert_called_once_with(str(self.guild.id), 'trx1')
        assertErrorCard(self.channel.send, f"Sorry {utils.idToUserStr(self.author.id)}, your buy request for 'sword' from {utils.idToUserStr(self.user.id)} has expired after 5 minutes.")

    async def test_remove_expired_transactions_sell_request_expired(self):
        # posted 10 minutes ago, sell request notifies the seller
        timePosted = (self.fixed_now - timedelta(minutes = 10)).strftime("%m/%d/%y %I:%M:%S %p")
        gtrade_queries.getAllTradeTransactions = MagicMock(return_value = {
            str(self.guild.id): {
                'trx1': {
                    'trxType': 'sell',
                    'item': {'name': 'sword'},
                    'timePosted': timePosted,
                    'sourceChannelId': str(self.channel.id),
                    'buyerId': str(self.user.id),
                    'sellerId': str(self.author.id)
                }
            }
        })
        gtrade_queries.removePendingTradeTransaction = MagicMock()
        await self.gtrade.remove_expired_transactions.coro(self.gtrade)
        gtrade_queries.removePendingTradeTransaction.assert_called_once_with(str(self.guild.id), 'trx1')
        assertErrorCard(self.channel.send, f"Sorry {utils.idToUserStr(self.author.id)}, your sell request for 'sword' to {utils.idToUserStr(self.user.id)} has expired after 5 minutes.")

    def _expired_market_trx(self):
        return {
            'trxType': 'market',
            'item': {'name': 'sword'},
            'timePosted': (self.fixed_now - timedelta(hours = 4)).strftime("%m/%d/%y %I:%M:%S %p"),
            'sourceChannelId': str(self.channel.id),
            'sellerId': str(self.author.id)
        }

    # one malformed entry used to abort the pass every minute, so nothing after it ever expired
    async def test_remove_expired_transactions_bad_entry_does_not_block_the_rest(self):
        self.gtrade.logger = MagicMock()
        gtrade_queries.getAllTradeTransactions = MagicMock(return_value = {
            str(self.guild.id): {'bad': {}, 'trx1': self._expired_market_trx()}
        })
        gtrade_queries.removePendingTradeTransaction = MagicMock()
        await self.gtrade.remove_expired_transactions.coro(self.gtrade)
        gtrade_queries.removePendingTradeTransaction.assert_called_once_with(str(self.guild.id), 'trx1')
        self.gtrade.logger.error.assert_called_once()

    # Both bots share one Firebase project. The other bot's channels are out of reach, so its
    # entries were deleted with their owners never told.
    async def test_remove_expired_transactions_leaves_other_bots_guilds_alone(self):
        self.gtrade.client.get_guild = MagicMock(return_value = None)
        gtrade_queries.getAllTradeTransactions = MagicMock(return_value = {
            '777': {'trx1': self._expired_market_trx()}
        })
        gtrade_queries.removePendingTradeTransaction = MagicMock()
        await self.gtrade.remove_expired_transactions.coro(self.gtrade)
        gtrade_queries.removePendingTradeTransaction.assert_not_called()
        self.gtrade.client.get_guild.assert_called_once_with(777)

    async def test_remove_expired_transactions_handles_exception(self):
        # raises inside the try block; outer try/except logs and swallows so test must not raise
        gtrade_queries.getAllTradeTransactions = MagicMock(side_effect = Exception("boom"))
        await self.gtrade.remove_expired_transactions.coro(self.gtrade)
    # endregion

    # region commonCraft
    def image(self, contentType = 'image/png'):
        return Mock(url = 'http://example.com/upload.png', content_type = contentType, to_file = AsyncMock(return_value = 'the file'))

    async def test_craft_negative_value(self):
        await self.craft("sword", -5, "http://good.example/img.png")
        assertErrorCard(self.ctx.send, f'Sorry {self.author.mention}, you can not craft items with non-positive values.')

    async def test_craft_zero_value(self):
        await self.craft("sword", 0, "http://good.example/img.png")
        assertErrorCard(self.ctx.send, f'Sorry {self.author.mention}, you can not craft items with non-positive values.')

    async def test_craft_invalid_decimal(self):
        await self.craft("sword", "ten", "http://good.example/img.png")
        assertErrorCard(self.ctx.send, f'Sorry {self.author.mention}, please enter a valid amount.')

    async def test_craft_max_items(self):
        gtrade_queries.getAllUserItems = MagicMock(return_value = {f'i{i}': self._make_item(name = f'n{i}') for i in range(self.gtrade.NUM_MAX_ITEMS)})
        await self.craft("sword", 5, "http://good.example/img.png")
        assertErrorCard(self.ctx.send, f"Sorry {self.author.mention}, you can't have more than {self.gtrade.NUM_MAX_ITEMS} items.")

    async def test_craft_name_conflict(self):
        gtrade_queries.getAllUserItems = MagicMock(return_value = {'id1': self._make_item(name = 'sword')})
        await self.craft("sword", 5, "http://good.example/img.png")
        assertErrorCard(self.ctx.send, f'Sorry {self.author.mention}, you already have an item with this name.')

    async def test_craft_needs_exactly_one_image(self):
        gtrade_queries.getAllUserItems = MagicMock(return_value = None)
        gcoin_queries.performTransaction = MagicMock()
        await self.craft("sword", 5)
        assertErrorCard(self.ctx.send, f'Sorry {self.author.mention}, please give a link to an image, or right-click an uploaded one and use **Apps → Craft item**.')
        self.ctx.send.reset_mock()
        self.ctx.message.attachments = [self.image()]
        await self.craft("sword", 5, "http://good.example/img.png")
        assertErrorCard(self.ctx.send, f'Sorry {self.author.mention}, please give a link to an image, or right-click an uploaded one and use **Apps → Craft item**.')
        gcoin_queries.performTransaction.assert_not_called()

    async def test_craft_refuses_what_is_not_an_image(self):
        gtrade_queries.getAllUserItems = MagicMock(return_value = None)
        gcoin_queries.performTransaction = MagicMock()
        expected = f"Sorry {self.author.mention}, that isn't an image GBot can use. Try a PNG, JPG, GIF or WebP, or a direct link to one."
        for attachment in (self.image('application/pdf'), self.image(None)):
            self.ctx.send.reset_mock()
            self.ctx.message.attachments = [attachment]
            await self.craft("sword", 5)
            assertErrorCard(self.ctx.send, expected)
        self.ctx.message.attachments = []
        self.ctx.send.reset_mock()
        utils.isUrlImageContentTypeAndStatus200 = AsyncMock(return_value = False)
        await self.craft("sword", 5, "http://bad.example/img")
        assertErrorCard(self.ctx.send, expected)
        gcoin_queries.performTransaction.assert_not_called()

    async def test_craft_url_success(self):
        gtrade_queries.getAllUserItems = MagicMock(return_value = None)
        gtrade_queries.createItemChanges = MagicMock(return_value = {'new/item': {}})
        gcoin_queries.performTransaction = MagicMock()
        utils.isUrlImageContentTypeAndStatus200 = AsyncMock(return_value = True)
        await self.craft("sword", 5, "http://good.example/img.png")
        gcoin_queries.performTransaction.assert_called_once_with(Decimal('5.00'), self.date, {'id': self.author.id, 'name': self.author.name}, {'id': None, 'name': 'GTrade'}, 'crafted', '', False, True, {'new/item': {}})
        gtrade_queries.createItemChanges.assert_called_once_with(self.author.id, "sword", Decimal('5.00'), self.author.name, self.guild.name, self.date, "sword", Decimal('5.00'), self.date, "image", {'imageUrl': "http://good.example/img.png"})
        self.ctx.send.assert_called_once_with(f"🔨 {self.author.mention}, you crafted 'sword' for 5.00 GCoin.")

    async def test_craft_attachment_success(self):
        gtrade_queries.getAllUserItems = MagicMock(return_value = None)
        gtrade_queries.createItemChanges = MagicMock(return_value = {'new/item': {}})
        gcoin_queries.performTransaction = MagicMock()
        gtrade_queries.createItemChanges = MagicMock(return_value = {'gtrade/personal/54321/item9': {}})
        gtrade_queries.setItemImageUrl = MagicMock()
        self.ctx.message.attachments = [self.image()]
        self.ctx.send = AsyncMock(return_value = Mock(attachments = [Mock(url = 'https://cdn.discordapp.com/kept.png')]))
        await self.craft("sword", 5)
        gtrade_queries.createItemChanges.assert_called_once_with(self.author.id, "sword", Decimal('5.00'), self.author.name, self.guild.name, self.date, "sword", Decimal('5.00'), self.date, "image", {'imageUrl': 'http://example.com/upload.png'})
        # the upload is posted with the result, and the item keeps that copy
        self.assertEqual(self.ctx.send.await_args.kwargs['file'], 'the file')
        self.assertIn("you crafted 'sword'", self.ctx.send.await_args.args[0])
        gtrade_queries.setItemImageUrl.assert_called_once_with(self.author.id, 'item9', 'https://cdn.discordapp.com/kept.png')

    async def test_a_slash_craft_fetches_its_reply_to_keep_the_image(self):
        gtrade_queries.getAllUserItems = MagicMock(return_value = None)
        gtrade_queries.createItemChanges = MagicMock(return_value = {'gtrade/personal/54321/item9': {}})
        gcoin_queries.performTransaction = MagicMock()
        gtrade_queries.setItemImageUrl = MagicMock()
        reply = Mock(attachments = [], fetch = AsyncMock(return_value = Mock(attachments = [Mock(url = 'https://cdn.discordapp.com/kept.png')])))
        self.interaction.send = AsyncMock(return_value = reply)
        await self.gtrade.commonCraft(self.interaction, self.author, 'sword', '5', self.image(), None)
        self.interaction.response.defer.assert_awaited_once()
        gtrade_queries.setItemImageUrl.assert_called_once_with(self.author.id, 'item9', 'https://cdn.discordapp.com/kept.png')

    async def test_an_image_that_cannot_be_kept_still_crafts_and_is_logged(self):
        gtrade_queries.getAllUserItems = MagicMock(return_value = None)
        gtrade_queries.createItemChanges = MagicMock(return_value = {'gtrade/personal/54321/item9': {}})
        gcoin_queries.performTransaction = MagicMock()
        gtrade_queries.setItemImageUrl = MagicMock()
        self.ctx.message.attachments = [self.image()]
        self.ctx.send = AsyncMock(side_effect = nextcord.HTTPException(Mock(status = 413, reason = 'too big'), 'too big'))
        with self.assertLogs(self.gtrade.logger, level = 'ERROR'):
            await self.craft("sword", 5)
        gcoin_queries.performTransaction.assert_called_once()
        gtrade_queries.setItemImageUrl.assert_not_called()

    async def test_craft_in_private_message(self):
        self.ctx.guild = None
        gtrade_queries.getAllUserItems = MagicMock(return_value = None)
        gtrade_queries.createItemChanges = MagicMock(return_value = {'new/item': {}})
        gcoin_queries.performTransaction = MagicMock()
        await self.craft("sword", 5, "http://good.example/img.png")
        # originalServer should be 'Direct Message' when guild is None
        self.assertEqual(gtrade_queries.createItemChanges.call_args.args[4], 'Direct Message')

    async def test_craft_insufficient_funds(self):
        gtrade_queries.getAllUserItems = MagicMock(return_value = None)
        gcoin_queries.performTransaction = MagicMock(side_effect = EnforceSenderFundsError)
        await self.craft("sword", 5, "http://good.example/img.png")
        assertErrorCard(self.ctx.send, f'Sorry {self.author.mention}, you have insufficient funds.')
    # endregion

    # region commonRename
    async def test_rename_no_existing_item(self):
        gtrade_queries.getAllUserItems = MagicMock(return_value = None)
        await self.gtrade.commonRename(self.ctx, self.ctx.author, "sword", "blade")
        assertErrorCard(self.ctx.send, f"Sorry {self.author.mention}, you do not have an item named 'sword'.")

    async def test_rename_name_conflict(self):
        gtrade_queries.getAllUserItems = MagicMock(return_value = {
            'id1': self._make_item(name = 'sword'),
            'id2': self._make_item(name = 'blade')
        })
        await self.gtrade.commonRename(self.ctx, self.ctx.author, "sword", "blade")
        assertErrorCard(self.ctx.send, f'Sorry {self.author.mention}, you already have an item with this name.')

    async def test_rename_item_not_found_but_other_items_exist(self):
        gtrade_queries.getAllUserItems = MagicMock(return_value = {'id1': self._make_item(name = 'shield')})
        await self.gtrade.commonRename(self.ctx, self.ctx.author, "sword", "blade")
        assertErrorCard(self.ctx.send, f"Sorry {self.author.mention}, you do not have an item named 'sword'.")

    async def test_rename_success(self):
        gtrade_queries.getAllUserItems = MagicMock(return_value = {'id1': self._make_item(name = 'sword')})
        gtrade_queries.renameItem = MagicMock()
        gtrade_queries.renameItemRelatedPendingTradeTransactions = MagicMock()
        await self.gtrade.commonRename(self.ctx, self.ctx.author, "sword", "blade")
        gtrade_queries.renameItem.assert_called_once_with(self.author.id, 'id1', 'blade')
        gtrade_queries.renameItemRelatedPendingTradeTransactions.assert_called_once_with(self.author.id, 'sword', 'blade')
        self.ctx.send.assert_called_once_with(f"✏️ {self.author.mention}, you renamed your item 'sword' to 'blade'.")
    # endregion

    # region commonDestroy
    async def test_destroy_no_item(self):
        gtrade_queries.getUserItem = MagicMock(return_value = None)
        self.assertEqual(await self.destroy(self.ctx, self.ctx.author, "sword"), "🚫 'sword' is no longer yours to destroy.")

    async def test_destroy_success(self):
        item = self._make_item(name = 'sword', value = '3.50')
        gtrade_queries.getUserItem = MagicMock(return_value = ('id1', item))
        gtrade_queries.removeItemChanges = MagicMock(return_value = {})
        gtrade_queries.removeRelatedPendingTradeTransactionsChanges = MagicMock(return_value = {})
        gcoin_queries.performTransaction = MagicMock()
        text = await self.destroy(self.ctx, self.ctx.author, "sword")
        gtrade_queries.removeItemChanges.assert_called_once_with(self.author.id, 'id1')
        gtrade_queries.removeRelatedPendingTradeTransactionsChanges.assert_called_once_with(self.author.id, 'sword')
        gcoin_queries.performTransaction.assert_called_once_with(Decimal('3.50'), self.date, {'id': None, 'name': 'GTrade'}, {'id': self.author.id, 'name': self.author.name}, '', 'destroyed', False, False, {})
        self.assertEqual(text, f"💥 {self.author.mention}, you destroyed your item 'sword' for 3.50 GCoin.")

    def click(self, user, customId = 'gtrade:accept:trx1'):
        interaction = Mock(spec = nextcord.Interaction)
        interaction.type = nextcord.InteractionType.component
        interaction.data = {'custom_id': customId}
        interaction.guild = self.guild
        interaction.user = user
        interaction.channel = self.channel
        interaction.message = Mock(content = 'the request', edit = AsyncMock())
        interaction.response = Mock(send_message = AsyncMock(), edit_message = AsyncMock(), defer = AsyncMock())
        interaction.send = AsyncMock()
        return interaction

    def tradeOnFile(self, kind, sellerId, buyerId = None):
        trx = {'trxType': kind, 'sellerId': str(sellerId), 'item': {'name': 'sword', 'value': '4.00'}}
        if buyerId is not None:
            trx['buyerId'] = str(buyerId)
        self.pending = {'trx1': trx}
        gtrade_queries.getPendingTradeTransactionWithId = MagicMock(side_effect = lambda serverId, trxId: self.pending.get(trxId))
        gtrade_queries.removePendingTradeTransaction = MagicMock(side_effect = lambda serverId, trxId: self.pending.pop(trxId))
        return trx

    def checksPass(self, subscribed = True, gtradeOn = True):
        subscribedPatch = patch('GBotDiscord.src.gtrade.gtrade_cog.predicates.ensureSubscribed', AsyncMock(side_effect = None if subscribed else NotSubscribed()))
        togglePatch = patch('GBotDiscord.src.gtrade.gtrade_cog.config_queries.getServerValue', MagicMock(return_value = gtradeOn))
        return subscribedPatch, togglePatch

    async def press(self, interaction):
        subscribedPatch, togglePatch = self.checksPass()
        with subscribedPatch, togglePatch:
            await self.gtrade.on_interaction(interaction)

    async def test_requests_and_listings_carry_buttons_with_the_trade_id(self):
        request = self.gtrade.tradeButtons('abc', 'request')
        self.assertEqual([item.custom_id for item in request.children], ['gtrade:accept:abc', 'gtrade:decline:abc', 'gtrade:cancel:abc'])
        self.assertIsNone(request.timeout)
        listing = self.gtrade.tradeButtons('abc', 'market')
        self.assertEqual([item.custom_id for item in listing.children], ['gtrade:buy:abc', 'gtrade:cancel:abc'])

    async def test_sent_buttons_leave_nextcords_view_store(self):
        context = Mock(send = AsyncMock())
        await self.gtrade.sendWithTradeButtons(context, 'text', 'abc', 'request')
        view = context.send.await_args.kwargs['view']
        self.assertTrue(view.is_finished())
        self.assertFalse(view.auto_defer)

    async def test_a_click_is_acknowledged_before_anything_else(self):
        self.tradeOnFile('buy', self.author.id, self.user.id)
        order = []
        interaction = self.click(self.author, 'gtrade:decline:trx1')
        interaction.response.defer = AsyncMock(side_effect = lambda: order.append('acknowledged'))
        gtrade_queries.getPendingTradeTransactionWithId = MagicMock(side_effect = lambda *args: (order.append('database'), self.pending.get('trx1'))[1])
        await self.press(interaction)
        self.assertEqual(order[:2], ['acknowledged', 'database'])

    async def test_accepting_a_buy_request_completes_it_even_with_a_crossed_sell_request(self):
        # the seller had also asked to sell the same item to the same buyer
        item = self._make_item(name = 'sword', value = '4.00')
        self.tradeOnFile('buy', self.author.id, self.user.id)
        crossed = {'trxType': 'sell', 'sellerId': str(self.author.id), 'buyerId': str(self.user.id), 'item': {'name': 'sword', 'value': '4.00'}}
        gtrade_queries.getUserItem = MagicMock(return_value = ('id1', item))
        gtrade_queries.getPendingTradeTransaction = MagicMock(side_effect = lambda serverId, trxType, *args: ('trx1', self.pending['trx1']) if trxType == 'buy' and 'trx1' in self.pending else (('trx2', crossed) if trxType == 'sell' else None))
        gtrade_queries.getAllUserItems = MagicMock(return_value = None)
        gtrade_queries.removeRelatedPendingTradeTransactionsChanges = MagicMock(return_value = {})
        gtrade_queries.removeItemChanges = MagicMock(return_value = {})
        gtrade_queries.createItemChanges = MagicMock(return_value = {})
        gcoin_queries.performTransaction = MagicMock(side_effect = lambda *args: self.pending.clear())
        removed = []
        gtrade_queries.removePendingTradeTransaction = MagicMock(side_effect = lambda serverId, trxId: removed.append(trxId))
        await self.press(self.click(self.author))
        gcoin_queries.performTransaction.assert_called_once()
        self.assertEqual(removed, [])

    # region one message for many trades
    def gathered(self):
        return gtrade_cog.Gathered(Mock(guild = self.guild, user = self.author, channel = self.channel))

    async def test_gathered_trades_are_kept_rather_than_posted(self):
        gathered = self.gathered()
        await self.gtrade.sendWithTradeButtons(gathered, 'line', 't1', 'market', 'sword', Decimal('4.00'))
        self.assertIsNone(await self.gtrade.announce(gathered, 'sold'))
        self.assertEqual((gathered.trades, gathered.announced), ([('t1', 'market', 'line', 'sword', Decimal('4.00'))], ['sold']))
        self.channel.send.assert_not_awaited()

    async def test_one_message_stands_for_several_listings(self):
        gathered = self.gathered()
        gathered.trades = [('t1', 'market', 'l1', 'sword', Decimal('4.00')), ('t2', 'market', 'l2', 'bow', Decimal('2.50'))]
        gathered.announced = ['🎉 sold one']
        await self.gtrade.announceGathered(gathered, self.author, None)
        first, second = self.channel.send.await_args_list
        self.assertEqual(first.args, ('🎉 sold one',))
        self.assertEqual(second.args[0], f'🏷️ {self.author.mention} put 2 items up for sale:\n• sword · 4.00 GCoin\n• bow · 2.50 GCoin')
        view = second.kwargs['view']
        self.assertEqual([button.custom_id for button in view.children], ['gtrade:openmarket:all'])
        self.assertTrue(view.is_finished())

    async def test_one_message_offers_one_member_several_items(self):
        gathered = self.gathered()
        gathered.trades = [('t1', 'request', 'l1', 'sword', Decimal('4.00')), ('t2', 'request', 'l2', 'bow', Decimal('2.50'))]
        await self.gtrade.announceGathered(gathered, self.author, self.user)
        sent = self.channel.send.await_args
        self.assertEqual(sent.args[0], f'🤝 {self.user.mention}, {self.author.mention} wants to sell you 2 items:\n• sword · 4.00 GCoin\n• bow · 2.50 GCoin')
        self.assertEqual([button.custom_id for button in sent.kwargs['view'].children], ['gtrade:acceptall:54321-12345', 'gtrade:declineall:54321-12345', 'gtrade:cancelall:54321-12345'])

    async def test_a_lone_gathered_trade_keeps_its_own_message_and_nothing_gathered_posts_nothing(self):
        gathered = self.gathered()
        await self.gtrade.announceGathered(gathered, self.author, None)
        self.channel.send.assert_not_awaited()
        gathered.trades = [('t1', 'market', 'the listing', 'sword', Decimal('4.00'))]
        await self.gtrade.announceGathered(gathered, self.author, None)
        sent = self.channel.send.await_args
        self.assertEqual(sent.args, ('the listing',))
        self.assertEqual([button.custom_id for button in sent.kwargs['view'].children], ['gtrade:buy:t1', 'gtrade:cancel:t1'])

    async def test_the_market_button_opens_the_market_for_whoever_pressed(self):
        self.gtrade.openMarket = AsyncMock()
        interaction = self.click(self.user, 'gtrade:openmarket:all')
        await self.press(interaction)
        self.gtrade.openMarket.assert_awaited_once_with(interaction, self.user)
        for subscribed, gtradeOn, said in ((False, True, 'GBot is not active in this server.'), (True, False, 'GTrade is turned off in this server.')):
            with self.subTest(said = said):
                self.gtrade.openMarket.reset_mock()
                interaction = self.click(self.user, 'gtrade:openmarket:all')
                subscribedPatch, togglePatch = self.checksPass(subscribed, gtradeOn)
                with subscribedPatch, togglePatch:
                    await self.gtrade.on_interaction(interaction)
                self.gtrade.openMarket.assert_not_awaited()
                interaction.send.assert_awaited_once_with(said, ephemeral = True)

    def offersOnFile(self):
        offer = lambda name: {'trxType': 'sell', 'sellerId': str(self.author.id), 'buyerId': str(self.user.id), 'item': {'name': name, 'value': '4.00'}}
        self.pending = {'t1': offer('sword'), 't2': offer('bow'), 't3': {'trxType': 'market', 'sellerId': str(self.author.id), 'item': {'name': 'cup', 'value': '1.00'}}}
        gtrade_queries.getAllServerPendingTradeTransactions = MagicMock(side_effect = lambda serverId: dict(self.pending))
        gtrade_queries.removePendingTradeTransaction = MagicMock(side_effect = lambda serverId, trxId: self.pending.pop(trxId))

    async def test_several_offers_are_declined_or_cancelled_together(self):
        for action, presser, line in (('declineall', self.user, f'-# ❌ {self.user.mention} declined these.'), ('cancelall', self.author, f'-# 🚫 {self.author.mention} cancelled these.')):
            with self.subTest(action = action):
                self.offersOnFile()
                interaction = self.click(presser, f'gtrade:{action}:54321-12345')
                await self.press(interaction)
                interaction.response.defer.assert_awaited_once()
                # only that seller's offers to that buyer: the listing stays
                self.assertEqual(list(self.pending), ['t3'])
                interaction.message.edit.assert_awaited_once_with(content = f'the request\n{line}', view = None)

    async def test_several_offers_are_only_for_who_they_name(self):
        self.offersOnFile()
        for action, presser in (('acceptall', self.author), ('declineall', self.author), ('cancelall', self.user)):
            with self.subTest(action = action):
                interaction = self.click(presser, f'gtrade:{action}:54321-12345')
                await self.press(interaction)
                interaction.send.assert_awaited_once_with("These buttons aren't for you.", ephemeral = True)
        self.assertEqual(len(self.pending), 3)
        # and the checks a command would make come first
        interaction = self.click(self.user, 'gtrade:declineall:54321-12345')
        subscribedPatch, togglePatch = self.checksPass(gtradeOn = False)
        with subscribedPatch, togglePatch:
            await self.gtrade.on_interaction(interaction)
        self.assertEqual(len(self.pending), 3)

    async def test_several_offers_are_accepted_together_with_one_message_for_them_all(self):
        self.offersOnFile()
        async def buy(context, author, item, seller):
            self.assertTrue(self.gtrade.tradeLock.locked())
            self.assertEqual((author, seller), (self.user, self.author))
            if item == 'sword':
                await self.gtrade.announce(context, '🎉 bought sword')
            else:
                await context.send('❌ no funds for bow')
        self.gtrade.buyUnderLock = AsyncMock(side_effect = buy)
        self.guild.get_member = MagicMock(side_effect = lambda uid: {self.author.id: self.author, self.user.id: self.user}.get(uid))
        interaction = self.click(self.user, 'gtrade:acceptall:54321-12345')
        await self.press(interaction)
        self.channel.send.assert_awaited_once_with('🎉 bought sword\n❌ no funds for bow')
        # one was refused, so the buttons stay for it
        interaction.message.edit.assert_not_awaited()
        self.assertFalse(self.gtrade.tradeLock.locked())
        # all of them went through, so the buttons go, and a message that's gone is no trouble
        async def buyAll(context, author, item, seller):
            await self.gtrade.announce(context, f'🎉 bought {item}')
        self.gtrade.buyUnderLock = AsyncMock(side_effect = buyAll)
        self.channel.send.reset_mock()
        interaction = self.click(self.user, 'gtrade:acceptall:54321-12345')
        await self.press(interaction)
        interaction.message.edit.assert_awaited_once_with(view = None)
        self.channel.send.assert_awaited_once_with('🎉 bought sword\n🎉 bought bow')
        interaction = self.click(self.user, 'gtrade:acceptall:54321-12345')
        interaction.message.edit = AsyncMock(side_effect = nextcord.HTTPException(Mock(status = 404, reason = 'Not Found'), 'gone'))
        await self.press(interaction)
        interaction.message.edit.assert_awaited_once_with(view = None)

    async def test_several_offers_that_are_gone_say_so(self):
        self.offersOnFile()
        self.guild.get_member = MagicMock(return_value = None)
        self.gtrade.buyUnderLock = AsyncMock()
        # the seller left
        interaction = self.click(self.user, 'gtrade:acceptall:54321-12345')
        await self.press(interaction)
        interaction.send.assert_awaited_once_with('⌛ These offers are no longer available.', ephemeral = True)
        self.gtrade.buyUnderLock.assert_not_awaited()
        # or nothing is left of them
        self.pending.clear()
        interaction = self.click(self.user, 'gtrade:declineall:54321-12345')
        await self.press(interaction)
        interaction.send.assert_awaited_once_with('⌛ These offers are no longer available.', ephemeral = True)
        interaction.message.edit.assert_awaited_once_with(view = None)

    async def test_trades_that_expire_together_are_told_in_one_message(self):
        timePosted = (self.fixed_now - timedelta(minutes = 10)).strftime("%m/%d/%y %I:%M:%S %p")
        offer = lambda name: {'trxType': 'sell', 'item': {'name': name}, 'timePosted': timePosted, 'sourceChannelId': str(self.channel.id), 'buyerId': str(self.user.id), 'sellerId': str(self.author.id)}
        gtrade_queries.getAllTradeTransactions = MagicMock(return_value = {str(self.guild.id): {'trx1': offer('sword'), 'trx2': offer('bow')}})
        gtrade_queries.removePendingTradeTransaction = MagicMock()
        await self.gtrade.remove_expired_transactions.coro(self.gtrade)
        self.assertEqual(gtrade_queries.removePendingTradeTransaction.call_count, 2)
        seller, buyer = utils.idToUserStr(self.author.id), utils.idToUserStr(self.user.id)
        self.channel.send.assert_awaited_once()
        assertErrorCard(self.channel.send, f"Sorry {seller}, 2 of your trades expired:\n• Your sell request for 'sword' to {buyer} has expired after 5 minutes.\n• Your sell request for 'bow' to {buyer} has expired after 5 minutes.")
        # a channel that's gone is logged, and the trades are still removed
        self.client.fetch_channel = AsyncMock(side_effect = Exception('gone'))
        self.gtrade.logger = MagicMock()
        await self.gtrade.remove_expired_transactions.coro(self.gtrade)
        self.assertEqual(gtrade_queries.removePendingTradeTransaction.call_count, 4)
        self.gtrade.logger.error.assert_called_once()
    # endregion

    async def test_other_interactions_are_left_alone(self):
        self.gtrade.answerTradeButton = AsyncMock()
        command = self.click(self.author)
        command.type = nextcord.InteractionType.application_command
        await self.gtrade.on_interaction(command)
        other = self.click(self.author, 'something:else')
        await self.gtrade.on_interaction(other)
        missing = self.click(self.author)
        missing.data = None
        await self.gtrade.on_interaction(missing)
        self.gtrade.answerTradeButton.assert_not_awaited()

    async def test_a_click_runs_the_same_checks_as_the_commands(self):
        self.tradeOnFile('buy', self.author.id, self.user.id)
        for subscribed, gtradeOn, expected in ((False, True, 'not active'), (True, False, 'turned off')):
            interaction = self.click(self.author)
            subscribedPatch, togglePatch = self.checksPass(subscribed, gtradeOn)
            with subscribedPatch, togglePatch:
                await self.gtrade.on_interaction(interaction)
            self.assertIn(expected, interaction.send.await_args.args[0])
        self.assertIn('trx1', self.pending)

    async def test_a_finished_or_expired_trade_says_so_and_drops_its_buttons(self):
        self.pending = {}
        gtrade_queries.getPendingTradeTransactionWithId = MagicMock(return_value = None)
        interaction = self.click(self.author)
        await self.press(interaction)
        self.assertIn('no longer available', interaction.send.await_args.args[0])
        interaction.message.edit.assert_awaited_once_with(view = None)
        interaction.message.edit.side_effect = nextcord.HTTPException(Mock(status = 404, reason = 'gone'), 'gone')
        await self.press(interaction)

    async def test_only_the_right_person_can_press_each_button(self):
        stranger = Mock(id = 777, mention = '<@!777>')
        # a buy request from user to author: author answers, user can cancel
        for kind, sellerId, buyerId in (('buy', self.author.id, self.user.id), ('sell', self.user.id, self.author.id)):
            self.tradeOnFile(kind, sellerId, buyerId)
            requester = self.user
            for who, action in ((requester, 'accept'), (requester, 'decline'), (stranger, 'accept'), (stranger, 'cancel'), (self.author, 'cancel'), (self.author, 'buy'), (self.author, 'nonsense')):
                interaction = self.click(who, f'gtrade:{action}:trx1')
                await self.press(interaction)
                self.assertEqual(interaction.send.await_args.args[0], "These buttons aren't for you.", (kind, action))
        self.tradeOnFile('market', self.author.id)
        for action in ('buy', 'accept', 'decline'):
            interaction = self.click(self.author, f'gtrade:{action}:trx1')
            await self.press(interaction)
            self.assertEqual(interaction.send.await_args.args[0], "These buttons aren't for you.")

    async def test_declining_or_cancelling_ends_the_trade_on_the_same_message(self):
        for kind, who, action, word in (('buy', self.author, 'decline', 'declined'), ('buy', self.user, 'cancel', 'cancelled'), ('market', self.author, 'cancel', 'taken down')):
            self.tradeOnFile(kind, self.author.id, self.user.id if kind == 'buy' else None)
            interaction = self.click(who, f'gtrade:{action}:trx1')
            await self.press(interaction)
            self.assertNotIn('trx1', self.pending)
            content = interaction.message.edit.await_args.kwargs['content']
            self.assertTrue(content.startswith('the request\n-# '))
            self.assertIn(f'{who.mention} {word} this.', content)
            self.assertIsNone(interaction.message.edit.await_args.kwargs['view'])
            interaction.response.defer.assert_awaited_once_with()

    async def test_accepting_goes_through_the_same_buy_and_sell_code(self):
        self.gtrade.sellUnderLock = AsyncMock(side_effect = lambda *args, **kwargs: self.pending.clear())
        self.gtrade.buyUnderLock = AsyncMock(side_effect = lambda *args, **kwargs: self.pending.clear())
        # a buy request: the seller accepts by selling to the buyer
        self.tradeOnFile('buy', self.author.id, self.user.id)
        interaction = self.click(self.author)
        await self.press(interaction)
        self.gtrade.sellUnderLock.assert_awaited_once_with(interaction, self.author, 'sword', self.user, accepting = True)
        interaction.message.edit.assert_awaited_once_with(view = None)
        # a sell request: the buyer accepts by buying from the seller
        self.tradeOnFile('sell', self.user.id, self.author.id)
        interaction = self.click(self.author)
        await self.press(interaction)
        self.gtrade.buyUnderLock.assert_awaited_once_with(interaction, self.author, 'sword', self.user)
        # a listing: anyone but the seller buys it
        self.tradeOnFile('market', self.user.id)
        interaction = self.click(self.author, 'gtrade:buy:trx1')
        await self.press(interaction)
        self.assertEqual(self.gtrade.buyUnderLock.await_args.args, (interaction, self.author, 'sword', self.user))

    async def test_a_trade_that_did_not_go_through_keeps_its_buttons(self):
        self.gtrade.buyUnderLock = AsyncMock()
        self.tradeOnFile('market', self.user.id)
        interaction = self.click(self.author, 'gtrade:buy:trx1')
        await self.press(interaction)
        interaction.message.edit.assert_not_awaited()
        self.gtrade.buyUnderLock.side_effect = lambda *args: self.pending.clear()
        interaction.message.edit.side_effect = nextcord.HTTPException(Mock(status = 404, reason = 'gone'), 'gone')
        await self.press(interaction)

    async def test_a_trade_with_someone_who_left_is_no_longer_available(self):
        self.tradeOnFile('market', self.user.id)
        self.guild.get_member = MagicMock(return_value = None)
        interaction = self.click(self.author, 'gtrade:buy:trx1')
        await self.press(interaction)
        self.assertIn('the other person left', interaction.send.await_args.args[0])

    async def test_a_real_accept_completes_the_trade(self):
        item = self._make_item(name = 'sword', value = '4.00')
        self.tradeOnFile('sell', self.user.id, self.author.id)
        gtrade_queries.getUserItem = MagicMock(return_value = ('id1', item))
        gtrade_queries.getPendingTradeTransaction = MagicMock(side_effect = lambda serverId, trxType, *args: ('trx1', self.pending['trx1']) if trxType == 'sell' and 'trx1' in self.pending else None)
        gtrade_queries.getAllUserItems = MagicMock(return_value = None)
        gtrade_queries.removeRelatedPendingTradeTransactionsChanges = MagicMock(return_value = {})
        gtrade_queries.removeItemChanges = MagicMock(return_value = {})
        gtrade_queries.createItemChanges = MagicMock(return_value = {})
        gcoin_queries.performTransaction = MagicMock(side_effect = lambda *args: self.pending.clear())
        interaction = self.click(self.author)
        await self.press(interaction)
        gcoin_queries.performTransaction.assert_called_once()
        self.assertIn("bought 'sword'", interaction.send.await_args.args[0])
        interaction.message.edit.assert_awaited_once_with(view = None)
    # endregion

    # region commonItems
    # endregion

    # region slash timeouts
    # Completing a trade took 2-2.5s against a 3s limit, with money already moved, so a timeout invited a
    # second attempt. These pin the order: refuse while the reply can still be private, then defer, then move.
    def _trade(self, order):
        item = self._make_item(name = 'sword')
        gtrade_queries.getUserItem = MagicMock(return_value = ('id1', item))
        gtrade_queries.getAllUserItems = MagicMock(return_value = None)
        gtrade_queries.getPendingTradeTransaction = MagicMock(side_effect = lambda serverId, trxType, *args: ('trx', {}) if trxType == 'buy' else None)
        patcher = patch.object(utils, 'isUserInThisGuildAndNotABot', new = AsyncMock(return_value = True))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.interaction.channel = Mock(id = 5)
        self.interaction.send = AsyncMock()
        self.interaction.response.defer = AsyncMock(side_effect = lambda **kwargs: order.append('defer'))
        self.gtrade.completeTradeTransaction = MagicMock(side_effect = lambda *args: order.append('money'))

    async def test_sell_completion_defers_before_moving_money(self):
        order = []
        self._trade(order)
        await self.gtrade.commonSell(self.interaction, self.author, 'sword', self.user)
        self.assertEqual(order, ['defer', 'money'])
        self.interaction.response.defer.assert_awaited_once_with(ephemeral = False)

    async def test_sell_completion_refusal_comes_before_any_defer(self):
        order = []
        self._trade(order)
        gcoin_queries.validateTransaction = MagicMock(side_effect = EnforceSenderFundsError)
        await self.gtrade.commonSell(self.interaction, self.author, 'sword', self.user)
        self.assertEqual(order, [])
        self.assertTrue(self.interaction.send.await_args.kwargs['ephemeral'])

    async def test_validateTrade_checks_the_buyers_funds(self):
        gtrade_queries.getAllUserItems = MagicMock(return_value = None)
        gcoin_queries.validateTransaction = MagicMock()
        buyer, seller = {'id': 1, 'name': 'b'}, {'id': 2, 'name': 's'}
        self.gtrade.validateTrade(('id1', self._make_item(name = 'sword', value = '5.00')), seller, buyer)
        gcoin_queries.validateTransaction.assert_called_once_with(Decimal('5.00'), buyer, seller, True, True)

    def _realWriteTrade(self):
        # the real money and item query code down to the one database call, so these prove the shape of
        # the write rather than which helpers got called
        item = self._make_item(name = 'sword', value = '5.00')
        trades = {str(self.guild.id): {'pending': {'sellerId': str(self.user.id), 'item': item}, 'elsewhere': {'sellerId': str(self.user.id), 'item': {'name': 'other'}}}}
        patches = [
            patch.object(gcoin_queries, 'performTransaction', new = _REAL_PERFORM_TRANSACTION),
            patch.object(gcoin_queries, 'validateTransaction', new = MagicMock()),
            patch.object(gcoin_queries, 'partyChanges', new = _REAL_PARTY_CHANGES),
            patch.object(gcoin_queries, 'getUserBalance', new = MagicMock(return_value = Decimal('100.00'))),
            patch.object(gtrade_queries, 'createItemChanges', new = _REAL_CREATE_ITEM_CHANGES),
            patch.object(gtrade_queries, 'removeItemChanges', new = _REAL_REMOVE_ITEM_CHANGES),
            patch.object(gtrade_queries, 'removeRelatedPendingTradeTransactionsChanges', new = _REAL_REMOVE_RELATED_CHANGES),
            patch.object(gtrade_queries, 'getAllTradeTransactions', new = MagicMock(return_value = trades)),
            patch.object(gtrade_queries, 'getUserItem', new = MagicMock(return_value = ('id1', item))),
            patch.object(gtrade_queries, 'getAllUserItems', new = MagicMock(return_value = None)),
            patch.object(GBotFirebaseService, 'set'), patch.object(GBotFirebaseService, 'push'), patch.object(GBotFirebaseService, 'remove'),
            patch.object(GBotFirebaseService, 'get', new = MagicMock(return_value = Mock(val = lambda: None))),
        ]
        for started in patches:
            started.start()
            self.addCleanup(started.stop)
        return item

    def test_completed_trade_is_one_atomic_write(self):
        item = self._realWriteTrade()
        seller = {'id': self.user.id, 'name': 'seller'}
        buyer = {'id': self.author.id, 'name': 'buyer'}
        with patch.object(GBotFirebaseService, 'updateMany') as updateMany:
            self.gtrade.completeTradeTransaction(self.guild.id, self.date, 'pending', ('id1', item), seller, buyer)
        updateMany.assert_called_once()
        changes = updateMany.call_args.args[0]
        # the database refuses a multi-path update where one path sits inside another
        for path in changes:
            self.assertFalse([other for other in changes if other.startswith(path + '/')], path)
        self.assertEqual(changes[f'gcoin/{self.author.id}/balance'], '95.00')
        self.assertEqual(changes[f'gcoin/{self.user.id}/balance'], '105.00')
        self.assertEqual(changes[f'gtrade/trade/{self.guild.id}/pending'], None)
        self.assertNotIn(f'gtrade/trade/{self.guild.id}/elsewhere', changes)
        self.assertEqual(changes[f'gtrade/personal/{self.user.id}/id1'], None)
        newItems = [value for path, value in changes.items() if path.startswith(f'gtrade/personal/{self.author.id}/')]
        self.assertEqual([newItem['dateObtained'] for newItem in newItems], [self.date])
        GBotFirebaseService.set.assert_not_called()
        GBotFirebaseService.push.assert_not_called()
        GBotFirebaseService.remove.assert_not_called()

    def test_failed_trade_write_changes_nothing_else(self):
        item = self._realWriteTrade()
        with patch.object(GBotFirebaseService, 'updateMany', side_effect = RuntimeError('database went away')):
            with self.assertRaises(RuntimeError):
                self.gtrade.completeTradeTransaction(self.guild.id, self.date, 'pending', ('id1', item), {'id': self.user.id, 'name': 'seller'}, {'id': self.author.id, 'name': 'buyer'})
        GBotFirebaseService.set.assert_not_called()
        GBotFirebaseService.push.assert_not_called()
        GBotFirebaseService.remove.assert_not_called()

    async def test_destroy_double_submit_pays_once(self):
        # deferring yields to the event loop, so both submits can pass the first read. Real
        # interleaving over a shared inventory, as a mock of the second read would prove nothing.
        inventory = {'id1': self._make_item(name = 'sword', value = '5.00')}
        gtrade_queries.getUserItem = MagicMock(side_effect = lambda uid, name: next(iter(inventory.items()), None))
        gtrade_queries.removeItemChanges = MagicMock(return_value = {})
        gtrade_queries.removeRelatedPendingTradeTransactionsChanges = MagicMock(return_value = {})
        # the money write is what takes the item now
        gcoin_queries.performTransaction = MagicMock(side_effect = lambda *args: inventory.clear())
        async def defer(context, ephemeral = False):
            await asyncio.sleep(0)
        with patch('GBotDiscord.src.gtrade.gtrade_cog.presentation.deferIfSlash', new = defer):
            await asyncio.gather(self.destroy(self.ctx, self.author, 'sword'), self.destroy(self.ctx, self.author, 'sword'))
        gcoin_queries.performTransaction.assert_called_once()

    async def test_buy_two_buyers_one_item_only_first_pays(self):
        # the same race as above across two buyers: the second must not pay the seller for an item
        # the first already took, or the item ends up duplicated
        otherBuyer = Mock()
        otherBuyer.id = 777
        otherBuyer.name = 'other buyer'
        otherBuyer.mention = '<@!777>'
        item = self._make_item(name = 'sword', value = '5.00')
        pending = {'trx1': {'trxType': 'market'}}
        inventory = {self.user.id: {'id1': item}}
        utils.isUserInThisGuildAndNotABot = AsyncMock(return_value = True)
        gtrade_queries.getUserItem = MagicMock(side_effect = lambda uid, name: next(iter(inventory.get(uid, {}).items()), None))
        gtrade_queries.getPendingTradeTransaction = MagicMock(side_effect = lambda serverId, trxType, *args: ('trx1', pending['trx1']) if trxType == 'market' and 'trx1' in pending else None)
        gtrade_queries.getPendingTradeTransactionWithId = MagicMock(side_effect = lambda serverId, trxId: pending.get(trxId))
        gtrade_queries.removeRelatedPendingTradeTransactionsChanges = MagicMock(return_value = {})
        gtrade_queries.getAllUserItems = MagicMock(return_value = None)
        gtrade_queries.createItemChanges = MagicMock(return_value = {'new/item': {}})
        gtrade_queries.removeItemChanges = MagicMock(return_value = {})
        # the money write is what moves the item and clears the pending trade now
        def takeItem(*args):
            pending.clear()
            inventory[self.user.id].clear()
        gcoin_queries.performTransaction = MagicMock(side_effect = takeItem)
        async def defer(context):
            await asyncio.sleep(0)
        secondCtx = Mock()
        secondCtx.guild = self.guild
        secondCtx.channel = self.channel
        secondCtx.send = AsyncMock()
        with patch('GBotDiscord.src.gtrade.gtrade_cog.presentation.deferIfSlash', new = defer):
            await asyncio.gather(self.gtrade.commonBuy(self.ctx, self.author, 'sword', self.user), self.gtrade.commonBuy(secondCtx, otherBuyer, 'sword', self.user))
        gcoin_queries.performTransaction.assert_called_once()
        gtrade_queries.createItemChanges.assert_called_once()
        # the trade lock makes the second buyer wait, then find the item gone
        assertErrorCard(secondCtx.send, f"Sorry {otherBuyer.mention}, {self.user.mention} does not have an item named 'sword'.")

    async def test_buy_and_destroy_of_one_item_only_one_goes_through(self):
        # now that database work has pauses in it, a seller destroying an item can meet a buyer taking it
        item = self._make_item(name = 'sword', value = '5.00')
        pending = {'trx1': {'trxType': 'market'}}
        inventory = {self.user.id: {'id1': item}}
        utils.isUserInThisGuildAndNotABot = AsyncMock(return_value = True)
        gtrade_queries.getUserItem = MagicMock(side_effect = lambda uid, name: next(iter(inventory.get(uid, {}).items()), None))
        gtrade_queries.getPendingTradeTransaction = MagicMock(side_effect = lambda serverId, trxType, *args: ('trx1', pending['trx1']) if trxType == 'market' and 'trx1' in pending else None)
        gtrade_queries.getPendingTradeTransactionWithId = MagicMock(side_effect = lambda serverId, trxId: pending.get(trxId))
        gtrade_queries.removeRelatedPendingTradeTransactionsChanges = MagicMock(return_value = {})
        gtrade_queries.removeItemChanges = MagicMock(return_value = {})
        gtrade_queries.createItemChanges = MagicMock(return_value = {})
        gtrade_queries.getAllUserItems = MagicMock(return_value = None)
        def takeItem(*args):
            pending.clear()
            inventory[self.user.id].clear()
        gcoin_queries.performTransaction = MagicMock(side_effect = takeItem)
        sellerCtx = Mock(guild = self.guild, channel = self.channel, send = AsyncMock())
        await asyncio.gather(self.gtrade.commonBuy(self.ctx, self.author, 'sword', self.user), self.destroy(sellerCtx, self.user, 'sword'))
        gcoin_queries.performTransaction.assert_called_once()

    async def test_craft_checks_the_name_again_under_the_lock(self):
        # someone can craft the same name while the image link is being checked
        gtrade_queries.getAllUserItems = MagicMock(side_effect = [None, {'i1': self._make_item(name = 'sword')}])
        gcoin_queries.performTransaction = MagicMock()
        utils.isUrlImageContentTypeAndStatus200 = AsyncMock(return_value = True)
        await self.gtrade.commonCraft(self.ctx, self.author, 'sword', '5', None, 'https://example.com/image.png')
        gcoin_queries.performTransaction.assert_not_called()
        assertErrorCard(self.ctx.send, f'Sorry {self.author.mention}, you already have an item with this name.')

    async def test_money_runs_off_the_event_loop(self):
        threads = []
        def record(*args):
            threads.append(threading.current_thread())
        gtrade_queries.getUserItem = MagicMock(return_value = ('id1', self._make_item(name = 'sword')))
        gtrade_queries.removeRelatedPendingTradeTransactionsChanges = MagicMock(return_value = {})
        gtrade_queries.removeItemChanges = MagicMock(return_value = {})
        with patch.object(gcoin_queries, 'performTransaction', new = record):
            await self.destroy(self.ctx, self.author, 'sword')
        self.assertEqual(len(threads), 1)
        self.assertIsNot(threads[0], threading.main_thread())

    async def test_buy_completing_a_trade_taken_already_is_refused(self):
        item = self._make_item(name = 'sword', value = '5.00')
        utils.isUserInThisGuildAndNotABot = AsyncMock(return_value = True)
        gtrade_queries.getUserItem = MagicMock(return_value = ('id1', item))
        gtrade_queries.getPendingTradeTransaction = MagicMock(side_effect = lambda serverId, trxType, *args: ('trx1', {'trxType': 'market'}) if trxType == 'market' else None)
        gtrade_queries.getPendingTradeTransactionWithId = MagicMock(return_value = None)
        gtrade_queries.getAllUserItems = MagicMock(return_value = None)
        gcoin_queries.performTransaction = MagicMock()
        await self.gtrade.commonBuy(self.ctx, self.author, 'sword', self.user)
        gcoin_queries.performTransaction.assert_not_called()
        assertErrorCard(self.ctx.send, f"Sorry {self.author.mention}, 'sword' is no longer available.")

    async def test_sell_completing_a_trade_taken_already_is_refused(self):
        item = self._make_item(name = 'sword', value = '5.00')
        utils.isUserInThisGuildAndNotABot = AsyncMock(return_value = True)
        gtrade_queries.getUserItem = MagicMock(return_value = ('id1', item))
        gtrade_queries.getPendingTradeTransaction = MagicMock(side_effect = lambda serverId, trxType, *args: ('trx1', {'trxType': 'buy'}) if trxType == 'buy' else None)
        gtrade_queries.getPendingTradeTransactionWithId = MagicMock(return_value = None)
        gtrade_queries.getAllUserItems = MagicMock(return_value = None)
        gcoin_queries.performTransaction = MagicMock()
        await self.gtrade.commonSell(self.ctx, self.author, 'sword', self.user)
        gcoin_queries.performTransaction.assert_not_called()
        assertErrorCard(self.ctx.send, f"Sorry {self.author.mention}, 'sword' is no longer available.")

    def test_completeTradeTransaction_refuses_a_different_item_with_the_same_name(self):
        # sold, then the seller crafted a new one under the same name while this trade was deferred
        item = self._make_item(name = 'sword')
        gtrade_queries.getUserItem = MagicMock(return_value = ('newer item', item))
        gcoin_queries.performTransaction = MagicMock()
        with self.assertRaises(ItemNoLongerAvailable):
            self.gtrade.completeTradeTransaction(self.guild.id, self.date, 'trx1', ('id1', item), {'id': self.user.id, 'name': 'seller'}, {'id': self.author.id, 'name': 'buyer'})
        gcoin_queries.performTransaction.assert_not_called()

    async def test_craft_name_too_long(self):
        gtrade_queries.getAllUserItems = MagicMock()
        await self.gtrade.commonCraft(self.ctx, self.author, 'x' * (self.gtrade.MAX_ITEM_NAME_LENGTH + 1), '5', None, 'https://example.com/image.png')
        gtrade_queries.getAllUserItems.assert_not_called()
        assertErrorCard(self.ctx.send, f"Sorry {self.author.mention}, item names can't be longer than {self.gtrade.MAX_ITEM_NAME_LENGTH} characters.")

    async def test_rename_name_too_long(self):
        gtrade_queries.renameItem = MagicMock()
        await self.gtrade.commonRename(self.ctx, self.author, 'sword', 'x' * (self.gtrade.MAX_ITEM_NAME_LENGTH + 1))
        gtrade_queries.renameItem.assert_not_called()
        assertErrorCard(self.ctx.send, f"Sorry {self.author.mention}, item names can't be longer than {self.gtrade.MAX_ITEM_NAME_LENGTH} characters.")

    # endregion

    # region commonItem
    # endregion

    # region commonMarket
    # endregion

    # region commonBuy
    async def test_buy_user_not_in_guild(self):
        utils.isUserInThisGuildAndNotABot = AsyncMock(return_value = False)
        await self.gtrade.commonBuy(self.ctx, self.ctx.author, "sword", self.user)
        assertErrorCard(self.ctx.send, f"Sorry {self.author.mention}, please specify a user in this guild.")

    async def test_buy_self(self):
        self.user.id = self.author.id
        await self.gtrade.commonBuy(self.ctx, self.ctx.author, "sword", self.user)
        assertErrorCard(self.ctx.send, f'Sorry {self.author.mention}, you can not buy from or sell to yourself.')

    async def test_buy_user_does_not_have_item(self):
        gtrade_queries.getUserItem = MagicMock(return_value = None)
        await self.gtrade.commonBuy(self.ctx, self.ctx.author, "sword", self.user)
        assertErrorCard(self.ctx.send, f"Sorry {self.author.mention}, {self.user.mention} does not have an item named 'sword'.")

    async def test_buy_completes_pending_sell_request(self):
        item = self._make_item(name = 'sword', value = '4.00')
        gtrade_queries.getUserItem = MagicMock(side_effect = lambda uid, name: ('id1', item) if uid == self.user.id else None)
        gtrade_queries.getPendingTradeTransaction = MagicMock(side_effect = [
            ('pending-sell', {}),  # pendingSellTrx
            None                    # pendingMarketTrx
        ])
        gtrade_queries.getAllUserItems = MagicMock(return_value = None)
        gcoin_queries.performTransaction = MagicMock()
        gtrade_queries.removeRelatedPendingTradeTransactionsChanges = MagicMock(return_value = {})
        gtrade_queries.createItemChanges = MagicMock(return_value = {'new/item': {}})
        gtrade_queries.removeItemChanges = MagicMock(return_value = {})
        await self.gtrade.commonBuy(self.ctx, self.ctx.author, "sword", self.user)
        self.assertIn(f'gtrade/trade/{self.guild.id}/pending-sell', gcoin_queries.performTransaction.call_args.args[8])
        gtrade_queries.createItemChanges.assert_called_once()
        gtrade_queries.removeItemChanges.assert_called_once_with(self.user.id, 'id1')
        self.ctx.send.assert_called_once_with(f"🎉 {self.author.mention} bought 'sword' from {self.user.mention} for 4.00 GCoin.")

    async def test_buy_completes_market_transaction(self):
        item = self._make_item(name = 'sword', value = '4.00')
        gtrade_queries.getUserItem = MagicMock(return_value = ('id1', item))
        gtrade_queries.getPendingTradeTransaction = MagicMock(side_effect = [
            None,                  # pendingSellTrx
            ('pending-mkt', {})    # pendingMarketTrx
        ])
        gtrade_queries.getAllUserItems = MagicMock(return_value = None)
        gcoin_queries.performTransaction = MagicMock()
        gtrade_queries.removeRelatedPendingTradeTransactionsChanges = MagicMock(return_value = {})
        gtrade_queries.createItemChanges = MagicMock(return_value = {'new/item': {}})
        gtrade_queries.removeItemChanges = MagicMock(return_value = {})
        await self.gtrade.commonBuy(self.ctx, self.ctx.author, "sword", self.user)
        self.assertIn(f'gtrade/trade/{self.guild.id}/pending-mkt', gcoin_queries.performTransaction.call_args.args[8])

    async def test_buy_cancels_existing_buy_request(self):
        item = self._make_item(name = 'sword', value = '4.00')
        gtrade_queries.getUserItem = MagicMock(return_value = ('id1', item))
        gtrade_queries.getPendingTradeTransaction = MagicMock(side_effect = [
            None, None, ('pending-buy', {})  # sell, market, buy
        ])
        gtrade_queries.removePendingTradeTransaction = MagicMock()
        await self.gtrade.commonBuy(self.ctx, self.ctx.author, "sword", self.user)
        gtrade_queries.removePendingTradeTransaction.assert_called_once_with(self.guild.id, 'pending-buy')
        self.ctx.send.assert_called_once_with(f"🚫 {self.author.mention}, you are no longer requesting to buy 'sword' from {self.user.mention}.")

    async def test_buy_creates_new_buy_request(self):
        item = self._make_item(name = 'sword', value = '4.00')
        gtrade_queries.getUserItem = MagicMock(return_value = ('id1', item))
        gtrade_queries.getPendingTradeTransaction = MagicMock(return_value = None)
        gtrade_queries.getAllUserItems = MagicMock(return_value = None)
        gcoin_queries.getUserBalance = MagicMock(return_value = Decimal('100.00'))
        gtrade_queries.createPendingTradeTransaction = MagicMock(return_value = 'trx-new')
        await self.gtrade.commonBuy(self.ctx, self.ctx.author, "sword", self.user)
        gtrade_queries.createPendingTradeTransaction.assert_called_once_with(self.guild.id, self.date, str(self.channel.id), item, 'buy', str(self.user.id), str(self.author.id))
        self.assertEqual(self.ctx.send.call_args.args[0], f"🤝 {self.user.mention}, {self.author.mention} wants to buy 'sword' from you for 4.00 GCoin.")
        self.assertEqual([item.custom_id for item in self.ctx.send.call_args.kwargs['view'].children], ['gtrade:accept:trx-new', 'gtrade:decline:trx-new', 'gtrade:cancel:trx-new'])

    async def test_buy_new_request_max_items(self):
        gtrade_queries.getUserItem = MagicMock(return_value = ('id1', self._make_item(name = 'sword', value = '4.00')))
        gtrade_queries.getPendingTradeTransaction = MagicMock(return_value = None)
        gtrade_queries.getAllUserItems = MagicMock(return_value = {f'i{i}': self._make_item(name = f'n{i}') for i in range(self.gtrade.NUM_MAX_ITEMS)})
        await self.gtrade.commonBuy(self.ctx, self.ctx.author, "sword", self.user)
        assertErrorCard(self.ctx.send, f"Sorry {self.author.mention}, you can't have more than {self.gtrade.NUM_MAX_ITEMS} items.")

    async def test_buy_new_request_name_conflict(self):
        gtrade_queries.getUserItem = MagicMock(return_value = ('id1', self._make_item(name = 'sword', value = '4.00')))
        gtrade_queries.getPendingTradeTransaction = MagicMock(return_value = None)
        gtrade_queries.getAllUserItems = MagicMock(return_value = {'mine': self._make_item(name = 'sword')})
        await self.gtrade.commonBuy(self.ctx, self.ctx.author, "sword", self.user)
        assertErrorCard(self.ctx.send, f'Sorry {self.author.mention}, you already have an item with this name.')

    async def test_buy_new_request_insufficient_funds(self):
        gtrade_queries.getUserItem = MagicMock(return_value = ('id1', self._make_item(name = 'sword', value = '4.00')))
        gtrade_queries.getPendingTradeTransaction = MagicMock(return_value = None)
        gtrade_queries.getAllUserItems = MagicMock(return_value = None)
        gcoin_queries.getUserBalance = MagicMock(return_value = Decimal('1.00'))
        await self.gtrade.commonBuy(self.ctx, self.ctx.author, "sword", self.user)
        assertErrorCard(self.ctx.send, f'Sorry {self.author.mention}, you have insufficient funds.')

    async def test_buy_complete_buyer_max_items(self):
        # buyer (author) already has max items; completeTradeTransaction raises ItemMaxCount which surfaces as message
        item = self._make_item(name = 'sword', value = '4.00')
        gtrade_queries.getUserItem = MagicMock(return_value = ('id1', item))
        gtrade_queries.getPendingTradeTransaction = MagicMock(side_effect = [('pending-sell', {}), None])
        gtrade_queries.getAllUserItems = MagicMock(return_value = {f'i{i}': self._make_item(name = f'n{i}') for i in range(self.gtrade.NUM_MAX_ITEMS)})
        await self.gtrade.commonBuy(self.ctx, self.ctx.author, "sword", self.user)
        assertErrorCard(self.ctx.send, f"Sorry {self.author.mention}, you can't have more than {self.gtrade.NUM_MAX_ITEMS} items.")

    async def test_buy_complete_buyer_name_conflict(self):
        item = self._make_item(name = 'sword', value = '4.00')
        gtrade_queries.getUserItem = MagicMock(return_value = ('id1', item))
        gtrade_queries.getPendingTradeTransaction = MagicMock(side_effect = [('pending-sell', {}), None])
        gtrade_queries.getAllUserItems = MagicMock(return_value = {'mine': self._make_item(name = 'sword')})
        await self.gtrade.commonBuy(self.ctx, self.ctx.author, "sword", self.user)
        assertErrorCard(self.ctx.send, f'Sorry {self.author.mention}, you already have an item with this name.')
    # endregion

    # region commonSell
    async def test_sell_no_item(self):
        gtrade_queries.getUserItem = MagicMock(return_value = None)
        await self.gtrade.commonSell(self.ctx, self.ctx.author, "sword", None)
        assertErrorCard(self.ctx.send, f"Sorry {self.author.mention}, you do not have an item named 'sword'.")

    async def test_sell_market_create(self):
        item = self._make_item(name = 'sword', value = '4.00')
        gtrade_queries.getUserItem = MagicMock(return_value = ('id1', item))
        gtrade_queries.getPendingTradeTransaction = MagicMock(return_value = None)
        gtrade_queries.createPendingTradeTransaction = MagicMock(return_value = 'trx-new')
        await self.gtrade.commonSell(self.ctx, self.ctx.author, "sword", None)
        gtrade_queries.createPendingTradeTransaction.assert_called_once_with(self.guild.id, self.date, str(self.channel.id), item, 'market', str(self.author.id))
        self.assertEqual(self.ctx.send.call_args.args[0], f"🏷️ {self.author.mention}, your item 'sword' is for sale for 4.00 GCoin.")
        self.assertEqual([item.label for item in self.ctx.send.call_args.kwargs['view'].children], ['Buy', 'Take down'])

    async def test_sell_market_cancel(self):
        item = self._make_item(name = 'sword', value = '4.00')
        gtrade_queries.getUserItem = MagicMock(return_value = ('id1', item))
        gtrade_queries.getPendingTradeTransaction = MagicMock(return_value = ('pending-mkt', {}))
        gtrade_queries.removePendingTradeTransaction = MagicMock()
        await self.gtrade.commonSell(self.ctx, self.ctx.author, "sword", None)
        gtrade_queries.removePendingTradeTransaction.assert_called_once_with(self.guild.id, 'pending-mkt')
        self.ctx.send.assert_called_once_with(f"🚫 {self.author.mention}, your item 'sword' is no longer for sale.")

    async def test_sell_user_not_in_guild(self):
        gtrade_queries.getUserItem = MagicMock(return_value = ('id1', self._make_item(name = 'sword', value = '4.00')))
        utils.isUserInThisGuildAndNotABot = AsyncMock(return_value = False)
        await self.gtrade.commonSell(self.ctx, self.ctx.author, "sword", self.user)
        assertErrorCard(self.ctx.send, f"Sorry {self.author.mention}, please specify a user in this guild.")

    async def test_sell_self(self):
        gtrade_queries.getUserItem = MagicMock(return_value = ('id1', self._make_item(name = 'sword', value = '4.00')))
        self.user.id = self.author.id
        await self.gtrade.commonSell(self.ctx, self.ctx.author, "sword", self.user)
        assertErrorCard(self.ctx.send, f'Sorry {self.author.mention}, you can not buy from or sell to yourself.')

    async def test_sell_cancel_existing_sell_request(self):
        item = self._make_item(name = 'sword', value = '4.00')
        gtrade_queries.getUserItem = MagicMock(return_value = ('id1', item))
        # pendingBuyTrx None, pendingSellTrx exists
        gtrade_queries.getPendingTradeTransaction = MagicMock(side_effect = [None, ('pending-sell', {})])
        gtrade_queries.removePendingTradeTransaction = MagicMock()
        await self.gtrade.commonSell(self.ctx, self.ctx.author, "sword", self.user)
        gtrade_queries.removePendingTradeTransaction.assert_called_once_with(self.guild.id, 'pending-sell')
        self.ctx.send.assert_called_once_with(f"🚫 {self.author.mention}, you are no longer requesting to sell 'sword' to {self.user.mention}.")

    async def test_sell_create_new_sell_request(self):
        item = self._make_item(name = 'sword', value = '4.00')
        gtrade_queries.getUserItem = MagicMock(return_value = ('id1', item))
        gtrade_queries.getPendingTradeTransaction = MagicMock(return_value = None)
        gtrade_queries.createPendingTradeTransaction = MagicMock(return_value = 'trx-new')
        await self.gtrade.commonSell(self.ctx, self.ctx.author, "sword", self.user)
        gtrade_queries.createPendingTradeTransaction.assert_called_once_with(self.guild.id, self.date, str(self.channel.id), item, 'sell', str(self.author.id), str(self.user.id))
        self.assertEqual(self.ctx.send.call_args.args[0], f"🤝 {self.user.mention}, {self.author.mention} wants to sell you 'sword' for 4.00 GCoin.")
        self.assertIn('view', self.ctx.send.call_args.kwargs)

    async def test_sell_completes_pending_buy_request(self):
        item = self._make_item(name = 'sword', value = '4.00')
        gtrade_queries.getUserItem = MagicMock(return_value = ('id1', item))
        # pendingBuyTrx exists, pendingSellTrx None
        gtrade_queries.getPendingTradeTransaction = MagicMock(side_effect = [('pending-buy', {}), None])
        gtrade_queries.getAllUserItems = MagicMock(return_value = None)
        gcoin_queries.performTransaction = MagicMock()
        gtrade_queries.removeRelatedPendingTradeTransactionsChanges = MagicMock(return_value = {})
        gtrade_queries.createItemChanges = MagicMock(return_value = {'new/item': {}})
        gtrade_queries.removeItemChanges = MagicMock(return_value = {})
        await self.gtrade.commonSell(self.ctx, self.ctx.author, "sword", self.user)
        self.assertIn(f'gtrade/trade/{self.guild.id}/pending-buy', gcoin_queries.performTransaction.call_args.args[8])
        self.ctx.send.assert_called_once_with(f"🎉 {self.author.mention} sold 'sword' to {self.user.mention} for 4.00 GCoin.")

    async def test_sell_completes_buy_buyer_max_items(self):
        item = self._make_item(name = 'sword', value = '4.00')
        gtrade_queries.getUserItem = MagicMock(return_value = ('id1', item))
        gtrade_queries.getPendingTradeTransaction = MagicMock(side_effect = [('pending-buy', {}), None])
        gtrade_queries.getAllUserItems = MagicMock(return_value = {f'i{i}': self._make_item(name = f'n{i}') for i in range(self.gtrade.NUM_MAX_ITEMS)})
        await self.gtrade.commonSell(self.ctx, self.ctx.author, "sword", self.user)
        assertErrorCard(self.ctx.send, f"Sorry {self.author.mention}, {self.user.mention} already has {self.gtrade.NUM_MAX_ITEMS} items.")

    async def test_sell_completes_buy_buyer_name_conflict(self):
        item = self._make_item(name = 'sword', value = '4.00')
        gtrade_queries.getUserItem = MagicMock(return_value = ('id1', item))
        gtrade_queries.getPendingTradeTransaction = MagicMock(side_effect = [('pending-buy', {}), None])
        gtrade_queries.getAllUserItems = MagicMock(return_value = {'mine': self._make_item(name = 'sword')})
        await self.gtrade.commonSell(self.ctx, self.ctx.author, "sword", self.user)
        assertErrorCard(self.ctx.send, f'Sorry {self.author.mention}, {self.user.mention} already has an item with this name.')
    # endregion

    # region autocomplete
    # endregion

    # region slash variants — verify each forwards to its common helper
    # endregion

    # region remove_expired_transactions — unknown trxType branch
    async def test_remove_expired_transactions_unknown_trxType(self):
        # Non-market, non-buy, non-sell trxType still expires but userId/trxStr stay empty.
        # Covers the 72->75 branch (elif sell False → fall through to `if isExpired`).
        timePosted = (self.fixed_now - timedelta(minutes = 10)).strftime("%m/%d/%y %I:%M:%S %p")
        gtrade_queries.getAllTradeTransactions = MagicMock(return_value = {
            str(self.guild.id): {
                'trx1': {
                    'trxType': 'unknown',
                    'item': {'name': 'sword'},
                    'timePosted': timePosted,
                    'sourceChannelId': str(self.channel.id),
                    'buyerId': str(self.author.id),
                    'sellerId': str(self.user.id)
                }
            }
        })
        gtrade_queries.removePendingTradeTransaction = MagicMock()
        await self.gtrade.remove_expired_transactions.coro(self.gtrade)
        gtrade_queries.removePendingTradeTransaction.assert_called_once_with(str(self.guild.id), 'trx1')
        # userId and trxStr are still empty strings; verify the formatted send
        assertErrorCard(self.channel.send, f"Sorry {utils.idToUserStr('')}, your ")
    # endregion

    # region commonCraft — branch coverage
    async def test_craft_existing_items_no_name_conflict(self):
        # allUserItems non-None but no name collision: the loop runs through without raising
        gtrade_queries.getAllUserItems = MagicMock(return_value = {
            'id1': self._make_item(name = 'shield'),
            'id2': self._make_item(name = 'bow')
        })
        gtrade_queries.createItemChanges = MagicMock(return_value = {'new/item': {}})
        gcoin_queries.performTransaction = MagicMock()
        utils.isUrlImageContentTypeAndStatus200 = AsyncMock(return_value = True)
        await self.craft("sword", 5, "http://good.example/img.png")
        gtrade_queries.createItemChanges.assert_called_once()
        self.ctx.send.assert_called_once_with(f"🔨 {self.author.mention}, you crafted 'sword' for 5.00 GCoin.")
    # endregion

    # region commonItems — branch coverage
    # endregion

    # region commonItem — non-image dataType branch
    # endregion

    # region commonMarket — branch coverage for unmatched trx + empty bucket branches
    # endregion

    # region commonBuy — existingItems branch coverage + error path catches
    async def test_buy_new_request_existing_items_no_conflict(self):
        # existingItems has items but none with matching name → for-loop exits naturally and
        # the buy request proceeds. Covers branches 559->563 and 561->559.
        gtrade_queries.getUserItem = MagicMock(return_value = ('id1', self._make_item(name = 'sword', value = '4.00')))
        gtrade_queries.getPendingTradeTransaction = MagicMock(return_value = None)
        gtrade_queries.getAllUserItems = MagicMock(return_value = {
            'mine1': self._make_item(name = 'shield'),
            'mine2': self._make_item(name = 'bow')
        })
        gcoin_queries.getUserBalance = MagicMock(return_value = Decimal('100.00'))
        gtrade_queries.createPendingTradeTransaction = MagicMock(return_value = 'trx-new')
        await self.gtrade.commonBuy(self.ctx, self.ctx.author, "sword", self.user)
        gtrade_queries.createPendingTradeTransaction.assert_called_once()

    async def test_buy_completion_raises_real_users_error(self):
        # completeTradeTransaction → performTransaction raises EnforceRealUsersError; commonBuy catches it.
        # Covers line 570.
        item = self._make_item(name = 'sword', value = '4.00')
        gtrade_queries.getUserItem = MagicMock(return_value = ('id1', item))
        gtrade_queries.getPendingTradeTransaction = MagicMock(side_effect = [('pending-sell', {}), None])
        self.gtrade.completeTradeTransaction = MagicMock(side_effect = EnforceRealUsersError)
        await self.gtrade.commonBuy(self.ctx, self.ctx.author, "sword", self.user)
        assertErrorCard(self.ctx.send, f'Sorry {self.author.mention}, please specify a valid user.')

    async def test_buy_completion_raises_positive_transactions(self):
        # Covers line 574 (EnforcePositiveTransactions branch in commonBuy).
        item = self._make_item(name = 'sword', value = '4.00')
        gtrade_queries.getUserItem = MagicMock(return_value = ('id1', item))
        gtrade_queries.getPendingTradeTransaction = MagicMock(side_effect = [('pending-sell', {}), None])
        self.gtrade.completeTradeTransaction = MagicMock(side_effect = EnforcePositiveTransactions)
        await self.gtrade.commonBuy(self.ctx, self.ctx.author, "sword", self.user)
        assertErrorCard(self.ctx.send, f'Sorry {self.author.mention}, you can not buy or sell items for non-positive amounts.')
    # endregion

    # region commonSell — error path catches inside the user-specified branch
    async def test_sell_completion_raises_real_users_error(self):
        # Covers line 654.
        item = self._make_item(name = 'sword', value = '4.00')
        gtrade_queries.getUserItem = MagicMock(return_value = ('id1', item))
        # pendingBuyTrx exists, pendingSellTrx None → falls into completeTradeTransaction
        gtrade_queries.getPendingTradeTransaction = MagicMock(side_effect = [('pending-buy', {}), None])
        self.gtrade.completeTradeTransaction = MagicMock(side_effect = EnforceRealUsersError)
        await self.gtrade.commonSell(self.ctx, self.ctx.author, "sword", self.user)
        assertErrorCard(self.ctx.send, f'Sorry {self.author.mention}, please specify a valid user.')

    async def test_sell_completion_raises_positive_transactions(self):
        # Covers line 658.
        item = self._make_item(name = 'sword', value = '4.00')
        gtrade_queries.getUserItem = MagicMock(return_value = ('id1', item))
        gtrade_queries.getPendingTradeTransaction = MagicMock(side_effect = [('pending-buy', {}), None])
        self.gtrade.completeTradeTransaction = MagicMock(side_effect = EnforcePositiveTransactions)
        await self.gtrade.commonSell(self.ctx, self.ctx.author, "sword", self.user)
        assertErrorCard(self.ctx.send, f'Sorry {self.author.mention}, you can not buy or sell items for negative amounts.')

    async def test_sell_completion_raises_insufficient_funds(self):
        # Covers line 660 — userMention is bound in the user-specified branch, so the message
        # interpolation succeeds with the buyer's mention.
        item = self._make_item(name = 'sword', value = '4.00')
        gtrade_queries.getUserItem = MagicMock(return_value = ('id1', item))
        gtrade_queries.getPendingTradeTransaction = MagicMock(side_effect = [('pending-buy', {}), None])
        self.gtrade.completeTradeTransaction = MagicMock(side_effect = EnforceSenderFundsError)
        await self.gtrade.commonSell(self.ctx, self.ctx.author, "sword", self.user)
        assertErrorCard(self.ctx.send, f'Sorry {self.author.mention}, {self.user.mention} has insufficient funds.')
    # endregion

    # region completeTradeTransaction — branch coverage
    def test_completeTradeTransaction_existing_items_no_conflict(self):
        # buyer has items but none with the same name → loop exits naturally, trade proceeds.
        # Covers branches 674->680 and 676->674.
        item = self._make_item(name = 'sword', value = '4.00')
        gtrade_queries.getUserItem = MagicMock(return_value = ('id1', item))
        # buyer (user) has 2 unrelated items
        gtrade_queries.getAllUserItems = MagicMock(return_value = {
            'b1': self._make_item(name = 'shield'),
            'b2': self._make_item(name = 'bow')
        })
        gcoin_queries.performTransaction = MagicMock()
        gtrade_queries.removeRelatedPendingTradeTransactionsChanges = MagicMock(return_value = {})
        gtrade_queries.createItemChanges = MagicMock(return_value = {'new/item': {}})
        gtrade_queries.removeItemChanges = MagicMock(return_value = {})
        self.gtrade.completeTradeTransaction(
            self.guild.id, self.date, 'pending-id', ('id1', item),
            {'id': self.user.id, 'name': self.user.name},
            {'id': self.author.id, 'name': self.author.name}
        )
        gcoin_queries.performTransaction.assert_called_once()
        gtrade_queries.createItemChanges.assert_called_once()
        gtrade_queries.removeItemChanges.assert_called_once_with(self.user.id, 'id1')
    # endregion

    # region setup
    def test_setup_adds_cog(self):
        from GBotDiscord.src.gtrade import gtrade_cog
        fake_client = MagicMock()
        gtrade_cog.setup(fake_client)
        fake_client.add_cog.assert_called_once()
        self.assertIsInstance(fake_client.add_cog.call_args.args[0], GTrade)
    # endregion

    #region the /gtrade cards
    def pressOn(self, user = None, guild = 'default'):
        interaction = Mock(spec = nextcord.Interaction)
        interaction.user = user or self.author
        interaction.guild = self.guild if guild == 'default' else guild
        interaction.channel = Mock(id = 88888, send = AsyncMock())
        answered = []
        interaction.response = Mock(defer = AsyncMock(side_effect = lambda **kwargs: answered.append(True)), send_modal = AsyncMock(), edit_message = AsyncMock(), is_done = Mock(side_effect = lambda: bool(answered)))
        interaction.send = AsyncMock(return_value = Mock(edit = AsyncMock()))
        interaction.edit_original_message = AsyncMock()
        return interaction

    def cardSetup(self, items = None, pending = None):
        isolation.restorePagination()
        self.ownItems = items if items is not None else {
            'i1': self._make_item(name = 'shield', value = '6.75'),
            'i2': self._make_item(name = 'sword', value = '10.00')}
        gtrade_queries.getAllUserItems = MagicMock(side_effect = lambda userId: self.ownItems)
        gtrade_queries.getAllServerPendingTradeTransactions = MagicMock(return_value = pending)
        gtrade_queries.getUserItem = MagicMock(side_effect = lambda userId, name: next(((itemId, item) for itemId, item in self.ownItems.items() if item['name'] == name), None))
        patcher = patch.object(gtrade_cog.predicates, 'recheck', AsyncMock())
        self.recheck = patcher.start()
        self.addCleanup(patcher.stop)

    async def openOwn(self, context = None, owner = None):
        context = context or self.pressOn()
        await self.gtrade.openItems(context, self.author, owner)
        return context.send.await_args.kwargs['view'], context.send.await_args.kwargs['embed'], context

    def action(self, picker, label):
        return next(action for action in picker.actions if action.label == label)

    async def test_the_command_opens_your_items_privately(self):
        with patch.object(self.gtrade, 'openItems', AsyncMock()) as openItems:
            interaction = self.pressOn()
            await self.gtrade.gtradeSlash(interaction)
            openItems.assert_awaited_once_with(interaction, interaction.user)
        self.ctx.message = Mock()
        with patch.object(gtrade_cog.pagination, 'openPrivately', AsyncMock()) as openPrivately:
            await self.gtrade.gtrade.callback(self.gtrade, self.ctx)
        openPrivately.assert_awaited_once_with(self.ctx, '🏪', 'Your items', self.gtrade.openItems, feature = 'toggle_gtrade')

    async def test_your_items_most_valuable_first_with_what_is_for_sale(self):
        self.cardSetup(pending = {'t1': {'trxType': 'market', 'sellerId': str(self.author.id), 'item': {'name': 'shield', 'value': '6.75'}}})
        picker, embed, context = await self.openOwn()
        self.assertTrue(context.send.await_args.kwargs['ephemeral'])
        self.assertEqual(embed.title, '🏪 Your items · 2 of 100')
        self.assertEqual(picker.source.entries, ['**1.** 🖼️ **sword** · `10.00 GCoin`', '**2.** 🖼️ **shield** · `6.75 GCoin` · 🏷️ for sale'])
        self.assertEqual(picker.choices[1], {'label': 'shield', 'description': '6.75 GCoin · for sale', 'emoji': '🖼️'})
        self.assertIn('Apps → Craft item', embed.fields[0].value)
        self.assertEqual([(action.label, action.row) for action in picker.actions], [('Show', 2), ('Sell', 2), ('Rename', 2), ('Destroy', 2), ('Craft', 3), ('Market', 3)])
        for row in picker.to_components():
            self.assertLessEqual(len(row['components']), 5)

    async def test_no_items_yet_and_no_selling_in_a_private_message(self):
        self.cardSetup(items = {})
        picker, embed, _ = await self.openOwn(self.pressOn(guild = None))
        self.assertIn('Press ⚒️ **Craft**', embed.description)
        self.assertEqual([action.label for action in picker.actions], ['Show', 'Rename', 'Destroy', 'Craft'])

    async def test_show_puts_the_item_in_the_channel(self):
        self.cardSetup()
        picker, _, _ = await self.openOwn()
        interaction = self.pressOn()
        await self.action(picker, 'Show').callback(picker, interaction, 0)
        self.recheck.assert_awaited_with(interaction, feature = 'toggle_gtrade', privateMessagesAllowed = True)
        embed = interaction.channel.send.await_args.kwargs['embed']
        self.assertEqual(embed.title, '🖼️ sword')
        self.assertEqual(embed.description, f'Owned by {self.author.mention}')
        self.assertIn("'sword' is shown in the channel", interaction.edit_original_message.await_args.kwargs['embed'].fields[-1].value)
        # gone by the time it was pressed
        self.ownItems = {}
        await self.action(picker, 'Show').callback(picker, self.pressOn(), 0)
        self.assertEqual(picker.source.entries, [])

    async def test_rename_and_destroy_and_craft_from_the_card(self):
        self.cardSetup()
        picker, _, _ = await self.openOwn()
        with patch.object(self.gtrade, 'commonRename', AsyncMock()) as commonRename:
            interaction = self.pressOn()
            await self.action(picker, 'Rename').callback(picker, interaction, 1)
            form = interaction.response.send_modal.await_args.args[0]
            self.assertEqual(form.inputs[0].default_value, 'shield')
            submitted = self.pressOn()
            await form.onSubmit(submitted, ['buckler'])
        reply, author, old, new = commonRename.await_args.args
        self.assertIsInstance(reply, pagination.CardReply)
        self.assertEqual((author, old, new), (self.author, 'shield', 'buckler'))
        with patch.object(self.gtrade, 'destroyUnderLock', AsyncMock(return_value = '💥 gone')) as destroyUnderLock:
            interaction = self.pressOn()
            await self.action(picker, 'Destroy').callback(picker, interaction, 0)
        destroyUnderLock.assert_awaited_once_with(self.author, 'sword')
        self.assertEqual(interaction.edit_original_message.await_args.kwargs['embed'].fields[-1].value, '💥 gone')
        self.assertEqual(self.action(picker, 'Destroy').confirm, 'Destroy for good')
        with patch.object(self.gtrade, 'commonCraft', AsyncMock()) as commonCraft:
            interaction = self.pressOn()
            await self.action(picker, 'Craft').callback(picker, interaction, None)
            form = interaction.response.send_modal.await_args.args[0]
            self.assertEqual([box.label for box in form.inputs], ['Name', 'Value in GCoin', 'Image link'])
            await form.onSubmit(self.pressOn(), ['hammer', '25', 'https://x/h.png'])
        self.assertEqual(commonCraft.await_args.args[1:], (self.author, 'hammer', '25', None, 'https://x/h.png'))

    async def test_sell_offers_the_market_or_someone(self):
        self.cardSetup()
        picker, _, _ = await self.openOwn()
        gtrade_queries.getPendingTradeTransaction = MagicMock(return_value = None)
        interaction = self.pressOn()
        await self.action(picker, 'Sell').callback(picker, interaction, 0)
        kwargs = interaction.send.await_args.kwargs
        self.assertTrue(kwargs['ephemeral'])
        self.assertEqual(kwargs['embed'].title, "🏷️ Sell 'sword'")
        sale = kwargs['view']
        market = next(item for item in sale.children if getattr(item, 'label', None) == 'The market')
        someone = next(item for item in sale.children if isinstance(item, nextcord.ui.UserSelect))
        with patch.object(self.gtrade, 'commonSell', AsyncMock()) as commonSell:
            pressed = self.pressOn()
            await market.callback(pressed)
            self.assertEqual(commonSell.await_args.args[1:], (self.author, 'sword', None))
            self.assertEqual(pressed.edit_original_message.await_args.kwargs['content'], '🏷️ Done, in the channel.')
            # a second click, or the picker after it, does nothing more
            again = self.pressOn()
            await market.callback(again)
            with patch.object(nextcord.ui.UserSelect, 'values', new_callable = unittest.mock.PropertyMock, return_value = [self.user]):
                await someone.callback(again)
            commonSell.assert_awaited_once()
            self.assertEqual(again.response.defer.await_count, 2)
        # already listed, so the same button takes it down
        gtrade_queries.getPendingTradeTransaction = MagicMock(return_value = ('t1', {}))
        await self.gtrade.openSale(self.pressOn(), self.author, 'sword')

    async def test_selling_to_someone(self):
        self.cardSetup()
        gtrade_queries.getPendingTradeTransaction = MagicMock(return_value = ('t1', {}))
        interaction = self.pressOn()
        await self.gtrade.openSale(interaction, self.author, 'sword')
        sale = interaction.send.await_args.kwargs['view']
        self.assertEqual(sale.children[0].label, 'Take off the market')
        picked = []
        async def sold(reply, author, item, member):
            picked.append(member)
            await reply.send(content = '🤝 asked')
        with patch.object(self.gtrade, 'commonSell', AsyncMock(side_effect = sold)):
            pressed = self.pressOn()
            with patch.object(nextcord.ui.UserSelect, 'values', new_callable = unittest.mock.PropertyMock, return_value = [self.user]):
                await sale.children[1].callback(pressed)
        self.assertEqual(picked, [self.user])
        self.assertEqual(pressed.edit_original_message.await_args.kwargs['content'], '🤝 asked')

    async def test_someone_elses_items_can_be_shown_or_asked_for(self):
        self.cardSetup()
        picker, embed, _ = await self.openOwn(owner = self.user)
        self.assertEqual(embed.title, f"🏪 {self.user.display_name}'s items · 2")
        self.assertEqual([action.label for action in picker.actions], ['Show', 'Ask to buy'])
        with patch.object(self.gtrade, 'commonBuy', AsyncMock()) as commonBuy:
            interaction = self.pressOn()
            await self.action(picker, 'Ask to buy').callback(picker, interaction, 1)
        self.assertEqual(commonBuy.await_args.args[1:], (self.author, 'shield', self.user))
        self.assertEqual(interaction.edit_original_message.await_args.kwargs['embed'].fields[-1].value, '🤝 Asked in the channel.')
        self.ownItems = {}
        _, embed, _ = await self.openOwn(owner = self.user)
        self.assertIn("doesn't have any items yet", embed.description)

    async def test_right_click_view_items(self):
        with patch.object(self.gtrade, 'openItems', AsyncMock()) as openItems:
            interaction = self.pressOn()
            await self.gtrade.viewItems(interaction, self.user)
            openItems.assert_awaited_once_with(interaction, interaction.user, self.user)
            bot = Mock(bot = True)
            interaction = self.pressOn()
            await self.gtrade.viewItems(interaction, bot)
        openItems.assert_awaited_once()
        self.assertIn("bots don't have items", interaction.send.await_args.kwargs['embed'].description)

    async def test_right_click_craft_item_from_an_upload(self):
        interaction = self.pressOn()
        await self.gtrade.craftItem(interaction, Mock(attachments = [Mock(content_type = 'text/plain')], embeds = [], content = 'no link here'))
        self.assertIn('no image to craft from', interaction.send.await_args.kwargs['embed'].description)
        interaction.response.send_modal.assert_not_awaited()
        image = self.image()
        interaction = self.pressOn()
        await self.gtrade.craftItem(interaction, Mock(attachments = [Mock(content_type = None), image], embeds = [], content = ''))
        form = interaction.response.send_modal.await_args.args[0]
        self.assertEqual([box.label for box in form.inputs], ['Name', 'Value in GCoin'])
        async def crafted(reply, author, name, value, image, imageUrl):
            await reply.send(content = '🔨 crafted it')
        with patch.object(self.gtrade, 'commonCraft', AsyncMock(side_effect = crafted)) as commonCraft, patch.object(gtrade_cog.predicates, 'recheck', AsyncMock()):
            submitted = self.pressOn()
            await form.onSubmit(submitted, ['hammer', '25'])
            submitted.response.defer.assert_awaited_once_with(ephemeral = True)
            self.assertEqual(commonCraft.await_args.args[1:], (submitted.user, 'hammer', '25', image, None))
            submitted.send.assert_awaited_once_with('🔨 crafted it', ephemeral = True)
            commonCraft.side_effect = None
            await form.onSubmit(submitted, ['hammer', '25'])
        submitted.send.assert_awaited_with('🔨 Crafted.', ephemeral = True)

    def test_what_a_message_can_be_crafted_from(self):
        image = Mock(content_type = 'image/png')
        self.assertEqual(gtrade_cog.imageIn(Mock(attachments = [image], embeds = [], content = 'https://x/y.png')), (image, None))
        embedded = Mock(image = Mock(url = None), thumbnail = Mock(url = 'https://cdn/thumb.jpg'))
        bare = Mock(image = Mock(url = None), thumbnail = Mock(url = None))
        self.assertEqual(gtrade_cog.imageIn(Mock(attachments = [], embeds = [bare, embedded], content = '')), (None, 'https://cdn/thumb.jpg'))
        self.assertEqual(gtrade_cog.imageIn(Mock(attachments = [], embeds = [], content = 'look https://t3.ftcdn.net/a.jpg nice')), (None, 'https://t3.ftcdn.net/a.jpg'))
        self.assertEqual(gtrade_cog.imageIn(Mock(attachments = [], embeds = [], content = None)), (None, None))

    async def test_right_click_craft_from_a_link(self):
        interaction = self.pressOn()
        await self.gtrade.craftItem(interaction, Mock(attachments = [], embeds = [], content = 'https://t3.ftcdn.net/a.jpg'))
        form = interaction.response.send_modal.await_args.args[0]
        with patch.object(self.gtrade, 'commonCraft', AsyncMock()) as commonCraft, patch.object(gtrade_cog.predicates, 'recheck', AsyncMock()):
            await form.onSubmit(self.pressOn(), ['cat', '5'])
        self.assertEqual(commonCraft.await_args.args[4:], (None, 'https://t3.ftcdn.net/a.jpg'))

    async def test_a_craft_from_a_card_still_posts_its_upload_in_the_channel(self):
        reply = pagination.CardReply(self.pressOn())
        await self.gtrade.announce(reply, 'hello', file = 'f')
        reply.channel.send.assert_awaited_once_with('hello', file = 'f')
        await self.gtrade.announce(self.ctx, 'hello')
        self.ctx.send.assert_awaited_once_with('hello')

    async def test_the_market_lists_what_others_sell_and_what_waits_on_you(self):
        await self.openTheMarket()

    async def openTheMarket(self):
        pending = {
            't1': {'trxType': 'market', 'sellerId': str(self.user.id), 'item': self._make_item(name = 'crown', value = '50')},
            't2': {'trxType': 'market', 'sellerId': str(self.author.id), 'item': self._make_item(name = 'mine', value = '1')},
            't3': {'trxType': 'market', 'sellerId': '777', 'item': self._make_item(name = 'Axe', value = '2')},
            't4': {'trxType': 'buy', 'sellerId': str(self.author.id), 'buyerId': str(self.user.id), 'item': {'name': 'shield', 'value': '6.75'}},
            't5': {'trxType': 'sell', 'sellerId': str(self.user.id), 'buyerId': str(self.author.id), 'item': {'name': 'gem', 'value': '3'}},
            't6': {'trxType': 'sell', 'sellerId': str(self.author.id), 'buyerId': str(self.user.id), 'item': {'name': 'x', 'value': '3'}}}
        self.cardSetup(pending = pending)
        self.guild.get_member = MagicMock(side_effect = lambda userId: {self.author.id: self.author, self.user.id: self.user}.get(userId))
        self.user.display_name = 'Sam'
        interaction = self.pressOn()
        await self.gtrade.openMarket(interaction, self.author)
        kwargs = interaction.send.await_args.kwargs
        picker = kwargs['view']
        self.assertTrue(kwargs['ephemeral'])
        self.assertEqual(picker.source.entries, ['**1.** 🖼️ **Axe** · `2.00 GCoin` · by Unknown user', '**2.** 🖼️ **crown** · `50.00 GCoin` · by Sam'])
        self.assertEqual(kwargs['embed'].fields[0].name, 'Waiting on you')
        self.assertEqual(kwargs['embed'].fields[0].value, 'Sam wants to buy your **shield** for 6.75 GCoin\nSam wants to sell you **gem** for 3.00 GCoin\nAnswer with the buttons on the request.')
        return picker

    async def test_buying_from_the_market(self):
        picker = await self.openTheMarket()
        gtrade_queries.getPendingTradeTransaction = MagicMock(return_value = ('t1', {}))
        with patch.object(self.gtrade, 'buyUnderLock', AsyncMock()) as commonBuy:
            interaction = self.pressOn()
            await self.action(picker, 'Buy').callback(picker, interaction, 1)
            self.assertEqual(commonBuy.await_args.args[1:], (self.author, 'crown', self.user))
            self.assertEqual(interaction.edit_original_message.await_args.kwargs['embed'].fields[-1].value, "🎉 You bought 'crown'.")
            # a listing that ended, or a seller who left, is refused rather than turned into a request
            gtrade_queries.getPendingTradeTransaction = MagicMock(return_value = None)
            await self.action(picker, 'Buy').callback(picker, interaction, 1)
            await self.action(picker, 'Buy').callback(picker, interaction, 0)
        commonBuy.assert_awaited_once()
        self.assertEqual(interaction.edit_original_message.await_args.kwargs['embed'].fields[-1].value, "❌ 'Axe' is no longer for sale.")

    async def test_showing_from_the_market(self):
        picker = await self.openTheMarket()
        interaction = self.pressOn()
        await self.action(picker, 'Show').callback(picker, interaction, 0)
        embed = interaction.channel.send.await_args.kwargs['embed']
        self.assertEqual(embed.description, 'Owned by a former member')
        self.assertIsNone(embed.thumbnail.url)

    async def test_an_empty_market(self):
        self.cardSetup(pending = None)
        self.guild.icon = None
        interaction = self.pressOn()
        await self.gtrade.openMarket(interaction, self.author)
        embed = interaction.send.await_args.kwargs['embed']
        self.assertIn('Nothing is for sale here', embed.description)
        self.assertEqual(embed.fields, [])

    async def test_market_from_your_items(self):
        self.cardSetup()
        picker, _, _ = await self.openOwn()
        with patch.object(self.gtrade, 'openMarket', AsyncMock()) as openMarket:
            interaction = self.pressOn()
            await self.action(picker, 'Market').callback(picker, interaction, None)
        openMarket.assert_awaited_once_with(interaction, self.author)

    async def test_the_item_card(self):
        embed = self.gtrade.itemEmbed(self.author, self._make_item(name = 'sword', value = '5'))
        self.assertEqual({field.name for field in embed.fields}, {'Value', 'Date Obtained', 'Date Created', 'Original Value', 'Original Name', 'Original Creator', 'Original Server'})
        self.assertEqual(embed.thumbnail.url, 'avatar url')
        self.author.avatar = None
        self.assertIsNone(self.gtrade.itemEmbed(self.author, self._make_item()).thumbnail.url)
    #endregion

if __name__ == '__main__':
    unittest.main()
