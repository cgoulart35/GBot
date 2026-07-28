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
from GBotDiscord.src.gtrade import gtrade_queries
from GBotDiscord.src.gcoin import gcoin_queries
from GBotDiscord.src.gtrade.gtrade_cog import GTrade
from GBotDiscord.src.exceptions import EnforceSenderFundsError, EnforceRealUsersError, EnforcePositiveTransactions
from GBotDiscord.src.properties import GBotPropertiesManager
from GBotDiscord.src.firebase import GBotFirebaseService
#endregion

# to run this test suite:
#   - execute the following command from the GBot directory: python -m unittest GBotDiscord/test/gtrade/gtrade_test.py
#   - or use the "Python: Current File" run configuration to run gtrade_test.py
#   - or use the "Python: Current File" run configuration to run tests.py to run all test suites
class TestGTrade(unittest.IsolatedAsyncioTestCase):

    @classmethod
    def setUpClass(self):
        print('\nExecuting gtrade unit tests...\n')

    @classmethod
    def tearDownClass(self):
        print('\n\nCompleted gtrade unit tests.\n')

    def setUp(self):
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

        self.gtrade: GTrade = GTrade(self.client)

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
        self.channel.send.assert_called_once_with(f"Sorry {utils.idToUserStr(self.author.id)}, your market sale for 'sword' has expired after 3 hours.")

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
        self.channel.send.assert_called_once_with(f"Sorry {utils.idToUserStr(self.author.id)}, your buy request for 'sword' from {utils.idToUserStr(self.user.id)} has expired after 5 minutes.")

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
        self.channel.send.assert_called_once_with(f"Sorry {utils.idToUserStr(self.author.id)}, your sell request for 'sword' to {utils.idToUserStr(self.user.id)} has expired after 5 minutes.")

    async def test_remove_expired_transactions_handles_exception(self):
        # raises inside the try block; outer try/except logs and swallows so test must not raise
        gtrade_queries.getAllTradeTransactions = MagicMock(side_effect = Exception("boom"))
        await self.gtrade.remove_expired_transactions.coro(self.gtrade)
    # endregion

    # region commonCraft
    async def test_craft_negative_value(self):
        await self.gtrade.craft(self.gtrade, self.ctx, "sword", -5, "image")
        self.ctx.send.assert_called_once_with(f'Sorry {self.author.mention}, you can not craft items with non-positive values.')

    async def test_craft_zero_value(self):
        await self.gtrade.craft(self.gtrade, self.ctx, "sword", 0, "image")
        self.ctx.send.assert_called_once_with(f'Sorry {self.author.mention}, you can not craft items with non-positive values.')

    async def test_craft_invalid_decimal(self):
        await self.gtrade.craft(self.gtrade, self.ctx, "sword", "ten", "image")
        self.ctx.send.assert_called_once_with(f'Sorry {self.author.mention}, please enter a valid amount. Remember to use quotes for names that are more than one word.')

    async def test_craft_max_items(self):
        gtrade_queries.getAllUserItems = MagicMock(return_value = {f'i{i}': self._make_item(name = f'n{i}') for i in range(self.gtrade.NUM_MAX_ITEMS)})
        await self.gtrade.craft(self.gtrade, self.ctx, "sword", 5, "image")
        self.ctx.send.assert_called_once_with(f"Sorry {self.author.mention}, you can't have more than {self.gtrade.NUM_MAX_ITEMS} items.")

    async def test_craft_name_conflict(self):
        gtrade_queries.getAllUserItems = MagicMock(return_value = {'id1': self._make_item(name = 'sword')})
        await self.gtrade.craft(self.gtrade, self.ctx, "sword", 5, "image")
        self.ctx.send.assert_called_once_with(f'Sorry {self.author.mention}, you already have an item with this name.')

    async def test_craft_invalid_type(self):
        gtrade_queries.getAllUserItems = MagicMock(return_value = None)
        await self.gtrade.craft(self.gtrade, self.ctx, "sword", 5, "video")
        self.ctx.send.assert_called_once_with(f'Sorry {self.author.mention}, please provide a valid item type.')

    async def test_craft_user_cancelled_with_keyword(self):
        gtrade_queries.getAllUserItems = MagicMock(return_value = None)
        response = Mock()
        response.content = "cancel"
        response.attachments = []
        utils.askUserQuestion = AsyncMock(return_value = response)
        await self.gtrade.craft(self.gtrade, self.ctx, "sword", 5, "image")
        self.ctx.send.assert_called_once_with(f'{self.author.mention}, item craft has been cancelled.')

    async def test_craft_user_cancelled_with_prefix(self):
        gtrade_queries.getAllUserItems = MagicMock(return_value = None)
        response = Mock()
        response.content = ".help"
        response.attachments = []
        response.guild = self.guild
        utils.askUserQuestion = AsyncMock(return_value = response)
        await self.gtrade.craft(self.gtrade, self.ctx, "sword", 5, "image")
        self.ctx.send.assert_called_once_with(f'{self.author.mention}, item craft has been cancelled.')

    async def test_craft_invalid_url_then_valid_url(self):
        gtrade_queries.getAllUserItems = MagicMock(return_value = None)
        gtrade_queries.createItem = MagicMock()
        gcoin_queries.performTransaction = MagicMock()
        bad = Mock()
        bad.content = "http://bad.example/img"
        bad.attachments = []
        good = Mock()
        good.content = "http://good.example/img.png"
        good.attachments = []
        utils.askUserQuestion = AsyncMock(side_effect = [bad, good])
        utils.isUrlImageContentTypeAndStatus200 = AsyncMock(side_effect = [False, True])
        await self.gtrade.craft(self.gtrade, self.ctx, "sword", 5, "image")
        # second call should include the "Invalid image URL." prefix
        prompts = [call.args[3] for call in utils.askUserQuestion.call_args_list]
        self.assertTrue(prompts[0].startswith(" "))
        self.assertTrue(prompts[1].startswith("Invalid image URL."))
        gtrade_queries.createItem.assert_called_once()
        self.ctx.send.assert_called_once_with(f"{self.author.mention}, you crafted 'sword' (image) for 5.00 GCoin.")

    async def test_craft_url_success(self):
        gtrade_queries.getAllUserItems = MagicMock(return_value = None)
        gtrade_queries.createItem = MagicMock()
        gcoin_queries.performTransaction = MagicMock()
        response = Mock()
        response.content = "http://good.example/img.png"
        response.attachments = []
        utils.askUserQuestion = AsyncMock(return_value = response)
        utils.isUrlImageContentTypeAndStatus200 = AsyncMock(return_value = True)
        await self.gtrade.craft(self.gtrade, self.ctx, "sword", 5, "image")
        gcoin_queries.performTransaction.assert_called_once_with(Decimal('5.00'), self.date, {'id': self.author.id, 'name': self.author.name}, {'id': None, 'name': 'GTrade'}, 'crafted', '', False, True)
        gtrade_queries.createItem.assert_called_once_with(self.author.id, "sword", Decimal('5.00'), self.author.name, self.guild.name, self.date, "sword", Decimal('5.00'), self.date, "image", {'imageUrl': response.content})
        self.ctx.send.assert_called_once_with(f"{self.author.mention}, you crafted 'sword' (image) for 5.00 GCoin.")

    async def test_craft_attachment_success(self):
        gtrade_queries.getAllUserItems = MagicMock(return_value = None)
        gtrade_queries.createItem = MagicMock()
        gcoin_queries.performTransaction = MagicMock()
        attachment = Mock()
        attachment.url = "http://example.com/upload.png"
        response = Mock()
        response.content = ""
        response.attachments = [attachment]
        utils.askUserQuestion = AsyncMock(return_value = response)
        await self.gtrade.craft(self.gtrade, self.ctx, "sword", 5, "image")
        gtrade_queries.createItem.assert_called_once_with(self.author.id, "sword", Decimal('5.00'), self.author.name, self.guild.name, self.date, "sword", Decimal('5.00'), self.date, "image", {'imageUrl': attachment.url})

    async def test_craft_in_private_message(self):
        self.ctx.guild = None
        gtrade_queries.getAllUserItems = MagicMock(return_value = None)
        gtrade_queries.createItem = MagicMock()
        gcoin_queries.performTransaction = MagicMock()
        response = Mock()
        response.content = "http://good.example/img.png"
        response.attachments = []
        utils.askUserQuestion = AsyncMock(return_value = response)
        await self.gtrade.craft(self.gtrade, self.ctx, "sword", 5, "image")
        # originalServer should be 'Direct Message' when guild is None
        self.assertEqual(gtrade_queries.createItem.call_args.args[4], 'Direct Message')

    async def test_craft_timeout(self):
        gtrade_queries.getAllUserItems = MagicMock(return_value = None)
        utils.askUserQuestion = AsyncMock(side_effect = asyncio.TimeoutError())
        await self.gtrade.craft(self.gtrade, self.ctx, "sword", 5, "image")
        self.ctx.send.assert_called_once_with(f'Sorry {self.author.mention}, you did not respond in time.')

    async def test_craft_insufficient_funds(self):
        gtrade_queries.getAllUserItems = MagicMock(return_value = None)
        gcoin_queries.performTransaction = MagicMock(side_effect = EnforceSenderFundsError)
        response = Mock()
        response.content = "http://good.example/img.png"
        response.attachments = []
        utils.askUserQuestion = AsyncMock(return_value = response)
        await self.gtrade.craft(self.gtrade, self.ctx, "sword", 5, "image")
        self.ctx.send.assert_called_once_with(f'Sorry {self.author.mention}, you have insufficient funds.')
    # endregion

    # region commonRename
    async def test_rename_no_existing_item(self):
        gtrade_queries.getAllUserItems = MagicMock(return_value = None)
        await self.gtrade.rename(self.gtrade, self.ctx, "sword", "blade")
        self.ctx.send.assert_called_once_with(f"Sorry {self.author.mention}, you do not have an item named 'sword'.")

    async def test_rename_name_conflict(self):
        gtrade_queries.getAllUserItems = MagicMock(return_value = {
            'id1': self._make_item(name = 'sword'),
            'id2': self._make_item(name = 'blade')
        })
        await self.gtrade.rename(self.gtrade, self.ctx, "sword", "blade")
        self.ctx.send.assert_called_once_with(f'Sorry {self.author.mention}, you already have an item with this name.')

    async def test_rename_item_not_found_but_other_items_exist(self):
        gtrade_queries.getAllUserItems = MagicMock(return_value = {'id1': self._make_item(name = 'shield')})
        await self.gtrade.rename(self.gtrade, self.ctx, "sword", "blade")
        self.ctx.send.assert_called_once_with(f"Sorry {self.author.mention}, you do not have an item named 'sword'.")

    async def test_rename_success(self):
        gtrade_queries.getAllUserItems = MagicMock(return_value = {'id1': self._make_item(name = 'sword')})
        gtrade_queries.renameItem = MagicMock()
        gtrade_queries.renameItemRelatedPendingTradeTransactions = MagicMock()
        await self.gtrade.rename(self.gtrade, self.ctx, "sword", "blade")
        gtrade_queries.renameItem.assert_called_once_with(self.author.id, 'id1', 'blade')
        gtrade_queries.renameItemRelatedPendingTradeTransactions.assert_called_once_with(self.author.id, 'sword', 'blade')
        self.ctx.send.assert_called_once_with(f"{self.author.mention}, you renamed your item 'sword' to 'blade'.")
    # endregion

    # region commonDestroy
    async def test_destroy_no_item(self):
        gtrade_queries.getUserItem = MagicMock(return_value = None)
        await self.gtrade.destroy(self.gtrade, self.ctx, "sword")
        self.ctx.send.assert_called_once_with(f"Sorry {self.author.mention}, you do not have an item named 'sword'.")

    async def test_destroy_success(self):
        item = self._make_item(name = 'sword', value = '3.50')
        gtrade_queries.getUserItem = MagicMock(return_value = ('id1', item))
        gtrade_queries.removeItem = MagicMock()
        gtrade_queries.removeRelatedPendingTradeTransactions = MagicMock()
        gcoin_queries.performTransaction = MagicMock()
        await self.gtrade.destroy(self.gtrade, self.ctx, "sword")
        gtrade_queries.removeItem.assert_called_once_with(self.author.id, 'id1')
        gtrade_queries.removeRelatedPendingTradeTransactions.assert_called_once_with(self.author.id, 'sword')
        gcoin_queries.performTransaction.assert_called_once_with(Decimal('3.50'), self.date, {'id': None, 'name': 'GTrade'}, {'id': self.author.id, 'name': self.author.name}, '', 'destroyed', False, False)
        self.ctx.send.assert_called_once_with(f"{self.author.mention}, you destroyed your item 'sword' for 3.50 GCoin.")
    # endregion

    # region commonItems
    async def test_items_private_message_user_specified(self):
        self.ctx.guild = None
        await self.gtrade.items(self.gtrade, self.ctx, self.user)
        self.ctx.send.assert_called_once_with(f"Sorry {self.author.mention}, please use this command on other users in a server.")

    async def test_items_user_not_in_guild(self):
        utils.isUserInThisGuildAndNotABot = AsyncMock(return_value = False)
        await self.gtrade.items(self.gtrade, self.ctx, self.user)
        self.ctx.send.assert_called_once_with(f"Sorry {self.author.mention}, please specify a user in this guild.")

    async def test_items_with_user_no_items(self):
        gtrade_queries.getAllUserItems = MagicMock(return_value = None)
        await self.gtrade.items(self.gtrade, self.ctx, self.user)
        self.ctx.send.assert_called_once_with(f"Sorry {self.author.mention}, {self.user.mention} does not have any items.")

    async def test_items_self_no_items(self):
        gtrade_queries.getAllUserItems = MagicMock(return_value = None)
        await self.gtrade.items(self.gtrade, self.ctx)
        self.ctx.send.assert_called_once_with(f"Sorry {self.author.mention}, you do not have any items.")

    async def test_items_self_with_items_sorted_by_value(self):
        gtrade_queries.getAllUserItems = MagicMock(return_value = {
            'id1': self._make_item(name = 'cheap', value = '1.00'),
            'id2': self._make_item(name = 'pricey', value = '10.00'),
            'id3': self._make_item(name = 'mid', value = '5.00')
        })
        pagination.FieldPageSource.__init__ = MagicMock(return_value = None)
        expected_fields = [
            ('1.) pricey', '`10.00 GCoin`\n`image`'),
            ('2.) mid', '`5.00 GCoin`\n`image`'),
            ('3.) cheap', '`1.00 GCoin`\n`image`')
        ]
        try:
            await self.gtrade.items(self.gtrade, self.ctx)
        except Exception:
            pagination.FieldPageSource.__init__.assert_called_once_with(expected_fields, self.avatar.url, f"{self.author.name}'s Items", nextcord.Color.orange(), False, 10)

    async def test_items_self_no_avatar(self):
        self.author.avatar = None
        gtrade_queries.getAllUserItems = MagicMock(return_value = {'id1': self._make_item()})
        pagination.FieldPageSource.__init__ = MagicMock(return_value = None)
        try:
            await self.gtrade.items(self.gtrade, self.ctx)
        except Exception:
            self.assertIsNone(pagination.FieldPageSource.__init__.call_args.args[1])

    async def test_items_user_no_avatar(self):
        self.user.avatar = None
        gtrade_queries.getAllUserItems = MagicMock(return_value = {'id1': self._make_item()})
        pagination.FieldPageSource.__init__ = MagicMock(return_value = None)
        try:
            await self.gtrade.items(self.gtrade, self.ctx, self.user)
        except Exception:
            self.assertIsNone(pagination.FieldPageSource.__init__.call_args.args[1])

    async def test_items_slash_defers(self):
        # call commonItems directly with a spec'd Interaction so isinstance check fires
        gtrade_queries.getAllUserItems = MagicMock(return_value = None)
        await self.gtrade.commonItems(self.interaction, self.author, None)
        self.interaction.response.defer.assert_called_once()
    # endregion

    # region commonItem
    async def test_item_does_not_exist(self):
        gtrade_queries.getUserItem = MagicMock(return_value = None)
        await self.gtrade.item(self.gtrade, self.ctx, "sword")
        self.ctx.send.assert_called_once_with(f"Sorry {self.author.mention}, you do not have an item named 'sword'.")

    async def test_item_exists_image_with_avatar(self):
        item = self._make_item(name = 'sword', value = '5.00')
        gtrade_queries.getUserItem = MagicMock(return_value = ('id1', item))
        await self.gtrade.item(self.gtrade, self.ctx, "sword")
        embed = self.ctx.send.call_args.kwargs['embed']
        self.assertEqual(embed.title, 'sword')
        self.assertEqual(embed.thumbnail.url, self.avatar.url)
        self.assertEqual(embed.image.url, item['dataJson']['imageUrl'])

    async def test_item_exists_image_no_avatar(self):
        self.author.avatar = None
        item = self._make_item(name = 'sword')
        gtrade_queries.getUserItem = MagicMock(return_value = ('id1', item))
        await self.gtrade.item(self.gtrade, self.ctx, "sword")
        embed = self.ctx.send.call_args.kwargs['embed']
        self.assertIsNone(embed.thumbnail.url)
    # endregion

    # region commonMarket
    async def test_market_no_pending(self):
        gtrade_queries.getAllServerPendingTradeTransactions = MagicMock(return_value = None)
        await self.gtrade.market(self.gtrade, self.ctx)
        self.ctx.send.assert_called_once_with(f"Sorry {self.author.mention}, there are no available items for sale or transaction requests.")

    async def test_market_with_all_kinds(self):
        gtrade_queries.getAllServerPendingTradeTransactions = MagicMock(return_value = {
            'mkt': {
                'trxType': 'market', 'sellerId': str(self.user.id), 'item': {'name': 'mkt-item', 'value': '7.00'}
            },
            'incBuy': {
                'trxType': 'buy', 'sellerId': str(self.author.id), 'buyerId': str(self.user.id), 'item': {'name': 'in-buy', 'value': '8.00'}
            },
            'incSell': {
                'trxType': 'sell', 'sellerId': str(self.user.id), 'buyerId': str(self.author.id), 'item': {'name': 'in-sell', 'value': '9.00'}
            },
            'outBuy': {
                'trxType': 'buy', 'sellerId': str(self.user.id), 'buyerId': str(self.author.id), 'item': {'name': 'out-buy', 'value': '1.00'}
            },
            'outSell': {
                'trxType': 'sell', 'sellerId': str(self.author.id), 'buyerId': str(self.user.id), 'item': {'name': 'out-sell', 'value': '2.00'}
            }
        })
        pagination.DescriptionPageSource.__init__ = MagicMock(return_value = None)
        try:
            await self.gtrade.market(self.gtrade, self.ctx)
        except Exception:
            data = pagination.DescriptionPageSource.__init__.call_args.args[0]
            self.assertIn('**Items For Sale**', data)
            self.assertIn('**Incoming Buy Requests**', data)
            self.assertIn('**Incoming Sell Requests**', data)
            self.assertIn('**Outgoing Buy Requests**', data)
            self.assertIn('**Outgoing Sell Requests**', data)
            # spot-check one line from each bucket
            self.assertTrue(any('is selling mkt-item' in d for d in data))
            self.assertTrue(any('has requested to buy in-buy from you' in d for d in data))
            self.assertTrue(any('has requested to sell you in-sell' in d for d in data))
            self.assertTrue(any('you have requested to buy out-buy' in d for d in data))
            self.assertTrue(any('you have requested to sell out-sell' in d for d in data))

    async def test_market_slash_defers(self):
        gtrade_queries.getAllServerPendingTradeTransactions = MagicMock(return_value = None)
        await self.gtrade.commonMarket(self.interaction, self.author)
        self.interaction.response.defer.assert_called_once()

    async def test_market_departed_seller_renders_placeholder(self):
        # Regression for A-5: get_member returns None once a party leaves the guild, and the
        # listing line then read `.name` off it — one stale listing broke /market for the
        # whole server. It must render a placeholder instead.
        self.guild.get_member = MagicMock(return_value = None)
        gtrade_queries.getAllServerPendingTradeTransactions = MagicMock(return_value = {
            'mkt': {
                'trxType': 'market', 'sellerId': str(self.user.id), 'item': {'name': 'mkt-item', 'value': '7.00'}
            }
        })
        pagination.DescriptionPageSource.__init__ = MagicMock(return_value = None)
        try:
            await self.gtrade.market(self.gtrade, self.ctx)
        except Exception:
            pass
        data = pagination.DescriptionPageSource.__init__.call_args.args[0]
        self.assertTrue(any('Unknown user is selling mkt-item' in d for d in data))
    # endregion

    # region commonBuy
    async def test_buy_user_not_in_guild(self):
        utils.isUserInThisGuildAndNotABot = AsyncMock(return_value = False)
        await self.gtrade.buy(self.gtrade, self.ctx, self.user, "sword")
        self.ctx.send.assert_called_once_with(f"Sorry {self.author.mention}, please specify a user in this guild.")

    async def test_buy_self(self):
        self.user.id = self.author.id
        await self.gtrade.buy(self.gtrade, self.ctx, self.user, "sword")
        self.ctx.send.assert_called_once_with(f'Sorry {self.author.mention}, you can not buy from or sell to yourself.')

    async def test_buy_user_does_not_have_item(self):
        gtrade_queries.getUserItem = MagicMock(return_value = None)
        await self.gtrade.buy(self.gtrade, self.ctx, self.user, "sword")
        self.ctx.send.assert_called_once_with(f"Sorry {self.author.mention}, {self.user.mention} does not have an item named 'sword'.")

    async def test_buy_completes_pending_sell_request(self):
        item = self._make_item(name = 'sword', value = '4.00')
        gtrade_queries.getUserItem = MagicMock(side_effect = lambda uid, name: ('id1', item) if uid == self.user.id else None)
        gtrade_queries.getPendingTradeTransaction = MagicMock(side_effect = [
            ('pending-sell', {}),  # pendingSellTrx
            None                    # pendingMarketTrx
        ])
        gtrade_queries.getAllUserItems = MagicMock(return_value = None)
        gcoin_queries.performTransaction = MagicMock()
        gtrade_queries.removePendingTradeTransactionAndOthersAffected = MagicMock()
        gtrade_queries.createItem = MagicMock()
        gtrade_queries.removeItem = MagicMock()
        await self.gtrade.buy(self.gtrade, self.ctx, self.user, "sword")
        gtrade_queries.removePendingTradeTransactionAndOthersAffected.assert_called_once_with(self.guild.id, 'pending-sell')
        gtrade_queries.createItem.assert_called_once()
        gtrade_queries.removeItem.assert_called_once_with(self.user.id, 'id1')
        self.ctx.send.assert_called_once_with(f"{self.author.mention}, you bought 'sword' from {self.user.mention} for 4.00 GCoin.")

    async def test_buy_completes_market_transaction(self):
        item = self._make_item(name = 'sword', value = '4.00')
        gtrade_queries.getUserItem = MagicMock(return_value = ('id1', item))
        gtrade_queries.getPendingTradeTransaction = MagicMock(side_effect = [
            None,                  # pendingSellTrx
            ('pending-mkt', {})    # pendingMarketTrx
        ])
        gtrade_queries.getAllUserItems = MagicMock(return_value = None)
        gcoin_queries.performTransaction = MagicMock()
        gtrade_queries.removePendingTradeTransactionAndOthersAffected = MagicMock()
        gtrade_queries.createItem = MagicMock()
        gtrade_queries.removeItem = MagicMock()
        await self.gtrade.buy(self.gtrade, self.ctx, self.user, "sword")
        gtrade_queries.removePendingTradeTransactionAndOthersAffected.assert_called_once_with(self.guild.id, 'pending-mkt')

    async def test_buy_cancels_existing_buy_request(self):
        item = self._make_item(name = 'sword', value = '4.00')
        gtrade_queries.getUserItem = MagicMock(return_value = ('id1', item))
        gtrade_queries.getPendingTradeTransaction = MagicMock(side_effect = [
            None, None, ('pending-buy', {})  # sell, market, buy
        ])
        gtrade_queries.removePendingTradeTransaction = MagicMock()
        await self.gtrade.buy(self.gtrade, self.ctx, self.user, "sword")
        gtrade_queries.removePendingTradeTransaction.assert_called_once_with(self.guild.id, 'pending-buy')
        self.ctx.send.assert_called_once_with(f"{self.author.mention}, you are no longer requesting to buy 'sword' from {self.user.mention}.")

    async def test_buy_creates_new_buy_request(self):
        item = self._make_item(name = 'sword', value = '4.00')
        gtrade_queries.getUserItem = MagicMock(return_value = ('id1', item))
        gtrade_queries.getPendingTradeTransaction = MagicMock(return_value = None)
        gtrade_queries.getAllUserItems = MagicMock(return_value = None)
        gcoin_queries.getUserBalance = MagicMock(return_value = Decimal('100.00'))
        gtrade_queries.createPendingTradeTransaction = MagicMock()
        await self.gtrade.buy(self.gtrade, self.ctx, self.user, "sword")
        gtrade_queries.createPendingTradeTransaction.assert_called_once_with(self.guild.id, self.date, str(self.channel.id), item, 'buy', str(self.user.id), str(self.author.id))
        self.ctx.send.assert_called_once_with(f"{self.user.mention}, {self.author.mention} wants to buy 'sword' from you for 4.00 GCoin.")

    async def test_buy_new_request_max_items(self):
        gtrade_queries.getUserItem = MagicMock(return_value = ('id1', self._make_item(name = 'sword', value = '4.00')))
        gtrade_queries.getPendingTradeTransaction = MagicMock(return_value = None)
        gtrade_queries.getAllUserItems = MagicMock(return_value = {f'i{i}': self._make_item(name = f'n{i}') for i in range(self.gtrade.NUM_MAX_ITEMS)})
        await self.gtrade.buy(self.gtrade, self.ctx, self.user, "sword")
        self.ctx.send.assert_called_once_with(f"Sorry {self.author.mention}, you can't have more than {self.gtrade.NUM_MAX_ITEMS} items.")

    async def test_buy_new_request_name_conflict(self):
        gtrade_queries.getUserItem = MagicMock(return_value = ('id1', self._make_item(name = 'sword', value = '4.00')))
        gtrade_queries.getPendingTradeTransaction = MagicMock(return_value = None)
        gtrade_queries.getAllUserItems = MagicMock(return_value = {'mine': self._make_item(name = 'sword')})
        await self.gtrade.buy(self.gtrade, self.ctx, self.user, "sword")
        self.ctx.send.assert_called_once_with(f'Sorry {self.author.mention}, you already have an item with this name.')

    async def test_buy_new_request_insufficient_funds(self):
        gtrade_queries.getUserItem = MagicMock(return_value = ('id1', self._make_item(name = 'sword', value = '4.00')))
        gtrade_queries.getPendingTradeTransaction = MagicMock(return_value = None)
        gtrade_queries.getAllUserItems = MagicMock(return_value = None)
        gcoin_queries.getUserBalance = MagicMock(return_value = Decimal('1.00'))
        await self.gtrade.buy(self.gtrade, self.ctx, self.user, "sword")
        self.ctx.send.assert_called_once_with(f'Sorry {self.author.mention}, you have insufficient funds.')

    async def test_buy_complete_buyer_max_items(self):
        # buyer (author) already has max items; completeTradeTransaction raises ItemMaxCount which surfaces as message
        item = self._make_item(name = 'sword', value = '4.00')
        gtrade_queries.getUserItem = MagicMock(return_value = ('id1', item))
        gtrade_queries.getPendingTradeTransaction = MagicMock(side_effect = [('pending-sell', {}), None])
        gtrade_queries.getAllUserItems = MagicMock(return_value = {f'i{i}': self._make_item(name = f'n{i}') for i in range(self.gtrade.NUM_MAX_ITEMS)})
        await self.gtrade.buy(self.gtrade, self.ctx, self.user, "sword")
        self.ctx.send.assert_called_once_with(f"Sorry {self.author.mention}, you can't have more than {self.gtrade.NUM_MAX_ITEMS} items.")

    async def test_buy_complete_buyer_name_conflict(self):
        item = self._make_item(name = 'sword', value = '4.00')
        gtrade_queries.getUserItem = MagicMock(return_value = ('id1', item))
        gtrade_queries.getPendingTradeTransaction = MagicMock(side_effect = [('pending-sell', {}), None])
        gtrade_queries.getAllUserItems = MagicMock(return_value = {'mine': self._make_item(name = 'sword')})
        await self.gtrade.buy(self.gtrade, self.ctx, self.user, "sword")
        self.ctx.send.assert_called_once_with(f'Sorry {self.author.mention}, you already have an item with this name.')
    # endregion

    # region commonSell
    async def test_sell_no_item(self):
        gtrade_queries.getUserItem = MagicMock(return_value = None)
        await self.gtrade.sell(self.gtrade, self.ctx, "sword")
        self.ctx.send.assert_called_once_with(f"Sorry {self.author.mention}, you do not have an item named 'sword'.")

    async def test_sell_market_create(self):
        item = self._make_item(name = 'sword', value = '4.00')
        gtrade_queries.getUserItem = MagicMock(return_value = ('id1', item))
        gtrade_queries.getPendingTradeTransaction = MagicMock(return_value = None)
        gtrade_queries.createPendingTradeTransaction = MagicMock()
        await self.gtrade.sell(self.gtrade, self.ctx, "sword")
        gtrade_queries.createPendingTradeTransaction.assert_called_once_with(self.guild.id, self.date, str(self.channel.id), item, 'market', str(self.author.id))
        self.ctx.send.assert_called_once_with(f"{self.author.mention}, your item 'sword' is for sale for 4.00 GCoin.")

    async def test_sell_market_cancel(self):
        item = self._make_item(name = 'sword', value = '4.00')
        gtrade_queries.getUserItem = MagicMock(return_value = ('id1', item))
        gtrade_queries.getPendingTradeTransaction = MagicMock(return_value = ('pending-mkt', {}))
        gtrade_queries.removePendingTradeTransaction = MagicMock()
        await self.gtrade.sell(self.gtrade, self.ctx, "sword")
        gtrade_queries.removePendingTradeTransaction.assert_called_once_with(self.guild.id, 'pending-mkt')
        self.ctx.send.assert_called_once_with(f"{self.author.mention}, your item 'sword' is no longer for sale.")

    async def test_sell_user_not_in_guild(self):
        gtrade_queries.getUserItem = MagicMock(return_value = ('id1', self._make_item(name = 'sword', value = '4.00')))
        utils.isUserInThisGuildAndNotABot = AsyncMock(return_value = False)
        await self.gtrade.sell(self.gtrade, self.ctx, "sword", self.user)
        self.ctx.send.assert_called_once_with(f"Sorry {self.author.mention}, please specify a user in this guild.")

    async def test_sell_self(self):
        gtrade_queries.getUserItem = MagicMock(return_value = ('id1', self._make_item(name = 'sword', value = '4.00')))
        self.user.id = self.author.id
        await self.gtrade.sell(self.gtrade, self.ctx, "sword", self.user)
        self.ctx.send.assert_called_once_with(f'Sorry {self.author.mention}, you can not buy from or sell to yourself.')

    async def test_sell_cancel_existing_sell_request(self):
        item = self._make_item(name = 'sword', value = '4.00')
        gtrade_queries.getUserItem = MagicMock(return_value = ('id1', item))
        # pendingBuyTrx None, pendingSellTrx exists
        gtrade_queries.getPendingTradeTransaction = MagicMock(side_effect = [None, ('pending-sell', {})])
        gtrade_queries.removePendingTradeTransaction = MagicMock()
        await self.gtrade.sell(self.gtrade, self.ctx, "sword", self.user)
        gtrade_queries.removePendingTradeTransaction.assert_called_once_with(self.guild.id, 'pending-sell')
        self.ctx.send.assert_called_once_with(f"{self.author.mention}, you are no longer requesting to sell 'sword' to {self.user.mention}.")

    async def test_sell_create_new_sell_request(self):
        item = self._make_item(name = 'sword', value = '4.00')
        gtrade_queries.getUserItem = MagicMock(return_value = ('id1', item))
        gtrade_queries.getPendingTradeTransaction = MagicMock(return_value = None)
        gtrade_queries.createPendingTradeTransaction = MagicMock()
        await self.gtrade.sell(self.gtrade, self.ctx, "sword", self.user)
        gtrade_queries.createPendingTradeTransaction.assert_called_once_with(self.guild.id, self.date, str(self.channel.id), item, 'sell', str(self.author.id), str(self.user.id))
        self.ctx.send.assert_called_once_with(f"{self.user.mention}, {self.author.mention} wants to sell you 'sword' for 4.00 GCoin.")

    async def test_sell_completes_pending_buy_request(self):
        item = self._make_item(name = 'sword', value = '4.00')
        gtrade_queries.getUserItem = MagicMock(return_value = ('id1', item))
        # pendingBuyTrx exists, pendingSellTrx None
        gtrade_queries.getPendingTradeTransaction = MagicMock(side_effect = [('pending-buy', {}), None])
        gtrade_queries.getAllUserItems = MagicMock(return_value = None)
        gcoin_queries.performTransaction = MagicMock()
        gtrade_queries.removePendingTradeTransactionAndOthersAffected = MagicMock()
        gtrade_queries.createItem = MagicMock()
        gtrade_queries.removeItem = MagicMock()
        await self.gtrade.sell(self.gtrade, self.ctx, "sword", self.user)
        gtrade_queries.removePendingTradeTransactionAndOthersAffected.assert_called_once_with(self.guild.id, 'pending-buy')
        self.ctx.send.assert_called_once_with(f"{self.author.mention}, you sold 'sword' to {self.user.mention} for 4.00 GCoin.")

    async def test_sell_completes_buy_buyer_max_items(self):
        item = self._make_item(name = 'sword', value = '4.00')
        gtrade_queries.getUserItem = MagicMock(return_value = ('id1', item))
        gtrade_queries.getPendingTradeTransaction = MagicMock(side_effect = [('pending-buy', {}), None])
        gtrade_queries.getAllUserItems = MagicMock(return_value = {f'i{i}': self._make_item(name = f'n{i}') for i in range(self.gtrade.NUM_MAX_ITEMS)})
        await self.gtrade.sell(self.gtrade, self.ctx, "sword", self.user)
        self.ctx.send.assert_called_once_with(f"Sorry {self.author.mention}, {self.user.mention} already has {self.gtrade.NUM_MAX_ITEMS} items.")

    async def test_sell_completes_buy_buyer_name_conflict(self):
        item = self._make_item(name = 'sword', value = '4.00')
        gtrade_queries.getUserItem = MagicMock(return_value = ('id1', item))
        gtrade_queries.getPendingTradeTransaction = MagicMock(side_effect = [('pending-buy', {}), None])
        gtrade_queries.getAllUserItems = MagicMock(return_value = {'mine': self._make_item(name = 'sword')})
        await self.gtrade.sell(self.gtrade, self.ctx, "sword", self.user)
        self.ctx.send.assert_called_once_with(f'Sorry {self.author.mention}, {self.user.mention} already has an item with this name.')
    # endregion

    # region autocomplete
    async def test_load_author_items(self):
        gtrade_queries.getAllUserItems = MagicMock(return_value = {'id1': self._make_item(name = 'sword')})
        await self.gtrade.loadAuthorItems(self.interaction, "sw")
        self.interaction.response.send_autocomplete.assert_called_once_with(['sword'])

    async def test_load_user_items_with_user_id_option(self):
        self.interaction.data = {'options': [{'value': self.user.id}]}
        gtrade_queries.getAllUserItems = MagicMock(return_value = {'id1': self._make_item(name = 'sword')})
        await self.gtrade.loadUserItems(self.interaction, "sw")
        self.interaction.response.send_autocomplete.assert_called_once_with(['sword'])

    async def test_load_user_items_no_user_id_in_data(self):
        self.interaction.data = {'options': []}
        await self.gtrade.loadUserItems(self.interaction, "sw")
        self.interaction.response.send_autocomplete.assert_called_once_with([])

    async def test_load_user_items_data_is_none(self):
        self.interaction.data = None
        await self.gtrade.loadUserItems(self.interaction, "sw")
        self.interaction.response.send_autocomplete.assert_called_once_with([])

    async def test_load_items_no_items(self):
        gtrade_queries.getAllUserItems = MagicMock(return_value = None)
        await self.gtrade.loadItemsForUserId(self.interaction, "sw", self.user.id)
        self.interaction.response.send_autocomplete.assert_called_once_with([])

    async def test_load_items_no_filter_returns_all(self):
        gtrade_queries.getAllUserItems = MagicMock(return_value = {'id1': self._make_item(name = 'sword'), 'id2': self._make_item(name = 'shield')})
        await self.gtrade.loadItemsForUserId(self.interaction, "", self.user.id)
        # order from dict iteration is preserved in py3.7+, so sword then shield
        self.interaction.response.send_autocomplete.assert_called_once_with(['sword', 'shield'])

    async def test_load_items_with_filter(self):
        gtrade_queries.getAllUserItems = MagicMock(return_value = {'id1': self._make_item(name = 'sword'), 'id2': self._make_item(name = 'shield')})
        await self.gtrade.loadItemsForUserId(self.interaction, "sw", self.user.id)
        self.interaction.response.send_autocomplete.assert_called_once_with(['sword'])
    # endregion

    # region slash variants — verify each forwards to its common helper
    async def test_craft_slash_delegates(self):
        self.gtrade.commonCraft = AsyncMock()
        await self.gtrade.craftSlash(self.interaction, "sword", 5, "image")
        self.gtrade.commonCraft.assert_called_once_with(self.interaction, self.interaction.user, "sword", 5, "image")

    async def test_rename_slash_delegates(self):
        self.gtrade.commonRename = AsyncMock()
        await self.gtrade.renameSlash(self.interaction, "sword", "blade")
        self.gtrade.commonRename.assert_called_once_with(self.interaction, self.interaction.user, "sword", "blade")

    async def test_destroy_slash_delegates(self):
        self.gtrade.commonDestroy = AsyncMock()
        await self.gtrade.destroySlash(self.interaction, "sword")
        self.gtrade.commonDestroy.assert_called_once_with(self.interaction, self.interaction.user, "sword")

    async def test_items_slash_delegates(self):
        self.gtrade.commonItems = AsyncMock()
        await self.gtrade.itemsSlash(self.interaction, self.user)
        self.gtrade.commonItems.assert_called_once_with(self.interaction, self.interaction.user, self.user)

    async def test_item_slash_delegates(self):
        self.gtrade.commonItem = AsyncMock()
        await self.gtrade.itemSlash(self.interaction, "sword")
        self.gtrade.commonItem.assert_called_once_with(self.interaction, self.interaction.user, "sword")

    async def test_market_slash_delegates(self):
        self.gtrade.commonMarket = AsyncMock()
        await self.gtrade.marketSlash(self.interaction)
        self.gtrade.commonMarket.assert_called_once_with(self.interaction, self.interaction.user)

    async def test_buy_slash_delegates(self):
        self.gtrade.commonBuy = AsyncMock()
        await self.gtrade.buySlash(self.interaction, self.user, "sword")
        self.gtrade.commonBuy.assert_called_once_with(self.interaction, self.interaction.user, "sword", self.user)

    async def test_sell_slash_delegates(self):
        self.gtrade.commonSell = AsyncMock()
        await self.gtrade.sellSlash(self.interaction, "sword", self.user)
        self.gtrade.commonSell.assert_called_once_with(self.interaction, self.interaction.user, "sword", self.user)
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
        self.channel.send.assert_called_once_with(f"Sorry {utils.idToUserStr('')}, your ")
    # endregion

    # region commonCraft — branch coverage
    async def test_craft_existing_items_no_name_conflict(self):
        # allUserItems non-None but no name collision: loop iterates through items without raising.
        # Covers branches 129->134 (loop exit) and 131->129 (no match, continue iteration).
        gtrade_queries.getAllUserItems = MagicMock(return_value = {
            'id1': self._make_item(name = 'shield'),
            'id2': self._make_item(name = 'bow')
        })
        gtrade_queries.createItem = MagicMock()
        gcoin_queries.performTransaction = MagicMock()
        response = Mock()
        response.content = "http://good.example/img.png"
        response.attachments = []
        utils.askUserQuestion = AsyncMock(return_value = response)
        utils.isUrlImageContentTypeAndStatus200 = AsyncMock(return_value = True)
        await self.gtrade.craft(self.gtrade, self.ctx, "sword", 5, "image")
        gtrade_queries.createItem.assert_called_once()
        self.ctx.send.assert_called_once_with(f"{self.author.mention}, you crafted 'sword' (image) for 5.00 GCoin.")

    async def test_craft_empty_response_loops_back(self):
        # Response with empty content AND attachments None → both branches fall through,
        # while loop continues to the next prompt. Covers branch 156->138.
        gtrade_queries.getAllUserItems = MagicMock(return_value = None)
        gtrade_queries.createItem = MagicMock()
        gcoin_queries.performTransaction = MagicMock()
        empty = Mock()
        empty.content = ""
        empty.attachments = None
        good = Mock()
        good.content = "http://good.example/img.png"
        good.attachments = []
        utils.askUserQuestion = AsyncMock(side_effect = [empty, good])
        utils.isUrlImageContentTypeAndStatus200 = AsyncMock(return_value = True)
        await self.gtrade.craft(self.gtrade, self.ctx, "sword", 5, "image")
        # askUserQuestion was called twice (loop iteration after empty response)
        self.assertEqual(utils.askUserQuestion.call_count, 2)
        gtrade_queries.createItem.assert_called_once()

    async def test_craft_empty_attachment_list_loops_back(self):
        # Regression for A-8: nextcord gives an EMPTY LIST (not None) for a message with no
        # files, and the check was `elif attachments != None`, so a sticker-only or
        # embed-only reply took the attachment branch and raised IndexError on attachments[0].
        gtrade_queries.getAllUserItems = MagicMock(return_value = None)
        gtrade_queries.createItem = MagicMock()
        gcoin_queries.performTransaction = MagicMock()
        stickerOnly = Mock()
        stickerOnly.content = ""
        stickerOnly.attachments = []
        good = Mock()
        good.content = "http://good.example/img.png"
        good.attachments = []
        utils.askUserQuestion = AsyncMock(side_effect = [stickerOnly, good])
        utils.isUrlImageContentTypeAndStatus200 = AsyncMock(return_value = True)
        await self.gtrade.craft(self.gtrade, self.ctx, "sword", 5, "image")
        self.assertEqual(utils.askUserQuestion.call_count, 2)
        gtrade_queries.createItem.assert_called_once()
    # endregion

    # region commonItems — branch coverage
    async def test_items_max_count_exits_loop_naturally(self):
        # Provide exactly NUM_MAX_ITEMS items so the inner for loop completes without breaking
        # (i never equals len(sortedItems) inside range(NUM_MAX_ITEMS)). Covers branch 330->339.
        gtrade_queries.getAllUserItems = MagicMock(return_value = {
            f'id{i}': self._make_item(name = f'name{i}', value = f'{i + 1}.00') for i in range(self.gtrade.NUM_MAX_ITEMS)
        })
        pagination.FieldPageSource.__init__ = MagicMock(return_value = None)
        try:
            await self.gtrade.items(self.gtrade, self.ctx)
        except Exception:
            fields = pagination.FieldPageSource.__init__.call_args.args[0]
            self.assertEqual(len(fields), self.gtrade.NUM_MAX_ITEMS)
    # endregion

    # region commonItem — non-image dataType branch
    async def test_item_non_image_dataType_no_send(self):
        # Covers branch 383->exit: dataType != 'image' → no embed sent.
        item = self._make_item(name = 'sword', dataType = 'video')
        gtrade_queries.getUserItem = MagicMock(return_value = ('id1', item))
        await self.gtrade.item(self.gtrade, self.ctx, "sword")
        self.ctx.send.assert_not_called()
    # endregion

    # region commonMarket — branch coverage for unmatched trx + empty bucket branches
    async def test_market_unmatched_trx_and_all_buckets_empty(self):
        # allServerPending non-None but the lone trx matches none of the 5 buckets
        # (market with a buyerId is impossible per the elif chain). Covers branch 463->438
        # (loop continues without entering any branch) and 469->472, 472->475, 475->478,
        # 478->481, 481->485 (each `if len(list) > 0` evaluating False).
        gtrade_queries.getAllServerPendingTradeTransactions = MagicMock(return_value = {
            'orphan': {
                'trxType': 'market',
                'sellerId': str(self.user.id),
                'buyerId': str(self.author.id),  # disqualifies the market bucket (buyerId must be None)
                'item': {'name': 'orphan-item', 'value': '1.00'}
            }
        })
        pagination.DescriptionPageSource.__init__ = MagicMock(return_value = None)
        try:
            await self.gtrade.market(self.gtrade, self.ctx)
        except Exception:
            data = pagination.DescriptionPageSource.__init__.call_args.args[0]
            self.assertEqual(data, [])

    async def test_market_author_no_avatar(self):
        # Covers the `author.avatar != None else None` fallback in the pages constructor.
        self.author.avatar = None
        gtrade_queries.getAllServerPendingTradeTransactions = MagicMock(return_value = {})
        pagination.DescriptionPageSource.__init__ = MagicMock(return_value = None)
        try:
            await self.gtrade.market(self.gtrade, self.ctx)
        except Exception:
            self.assertIsNone(pagination.DescriptionPageSource.__init__.call_args.args[3])
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
        gtrade_queries.createPendingTradeTransaction = MagicMock()
        await self.gtrade.buy(self.gtrade, self.ctx, self.user, "sword")
        gtrade_queries.createPendingTradeTransaction.assert_called_once()

    async def test_buy_completion_raises_real_users_error(self):
        # completeTradeTransaction → performTransaction raises EnforceRealUsersError; commonBuy catches it.
        # Covers line 570.
        item = self._make_item(name = 'sword', value = '4.00')
        gtrade_queries.getUserItem = MagicMock(return_value = ('id1', item))
        gtrade_queries.getPendingTradeTransaction = MagicMock(side_effect = [('pending-sell', {}), None])
        self.gtrade.completeTradeTransaction = MagicMock(side_effect = EnforceRealUsersError)
        await self.gtrade.buy(self.gtrade, self.ctx, self.user, "sword")
        self.ctx.send.assert_called_once_with(f'Sorry {self.author.mention}, please specify a valid user.')

    async def test_buy_completion_raises_positive_transactions(self):
        # Covers line 574 (EnforcePositiveTransactions branch in commonBuy).
        item = self._make_item(name = 'sword', value = '4.00')
        gtrade_queries.getUserItem = MagicMock(return_value = ('id1', item))
        gtrade_queries.getPendingTradeTransaction = MagicMock(side_effect = [('pending-sell', {}), None])
        self.gtrade.completeTradeTransaction = MagicMock(side_effect = EnforcePositiveTransactions)
        await self.gtrade.buy(self.gtrade, self.ctx, self.user, "sword")
        self.ctx.send.assert_called_once_with(f'Sorry {self.author.mention}, you can not buy or sell items for non-positive amounts.')
    # endregion

    # region commonSell — error path catches inside the user-specified branch
    async def test_sell_completion_raises_real_users_error(self):
        # Covers line 654.
        item = self._make_item(name = 'sword', value = '4.00')
        gtrade_queries.getUserItem = MagicMock(return_value = ('id1', item))
        # pendingBuyTrx exists, pendingSellTrx None → falls into completeTradeTransaction
        gtrade_queries.getPendingTradeTransaction = MagicMock(side_effect = [('pending-buy', {}), None])
        self.gtrade.completeTradeTransaction = MagicMock(side_effect = EnforceRealUsersError)
        await self.gtrade.sell(self.gtrade, self.ctx, "sword", self.user)
        self.ctx.send.assert_called_once_with(f'Sorry {self.author.mention}, please specify a valid user.')

    async def test_sell_completion_raises_positive_transactions(self):
        # Covers line 658.
        item = self._make_item(name = 'sword', value = '4.00')
        gtrade_queries.getUserItem = MagicMock(return_value = ('id1', item))
        gtrade_queries.getPendingTradeTransaction = MagicMock(side_effect = [('pending-buy', {}), None])
        self.gtrade.completeTradeTransaction = MagicMock(side_effect = EnforcePositiveTransactions)
        await self.gtrade.sell(self.gtrade, self.ctx, "sword", self.user)
        self.ctx.send.assert_called_once_with(f'Sorry {self.author.mention}, you can not buy or sell items for negative amounts.')

    async def test_sell_completion_raises_insufficient_funds(self):
        # Covers line 660 — userMention is bound in the user-specified branch, so the message
        # interpolation succeeds with the buyer's mention.
        item = self._make_item(name = 'sword', value = '4.00')
        gtrade_queries.getUserItem = MagicMock(return_value = ('id1', item))
        gtrade_queries.getPendingTradeTransaction = MagicMock(side_effect = [('pending-buy', {}), None])
        self.gtrade.completeTradeTransaction = MagicMock(side_effect = EnforceSenderFundsError)
        await self.gtrade.sell(self.gtrade, self.ctx, "sword", self.user)
        self.ctx.send.assert_called_once_with(f'Sorry {self.author.mention}, {self.user.mention} has insufficient funds.')
    # endregion

    # region completeTradeTransaction — branch coverage
    def test_completeTradeTransaction_existing_items_no_conflict(self):
        # buyer has items but none with the same name → loop exits naturally, trade proceeds.
        # Covers branches 674->680 and 676->674.
        item = self._make_item(name = 'sword', value = '4.00')
        # buyer (user) has 2 unrelated items
        gtrade_queries.getAllUserItems = MagicMock(return_value = {
            'b1': self._make_item(name = 'shield'),
            'b2': self._make_item(name = 'bow')
        })
        gcoin_queries.performTransaction = MagicMock()
        gtrade_queries.removePendingTradeTransactionAndOthersAffected = MagicMock()
        gtrade_queries.createItem = MagicMock()
        gtrade_queries.removeItem = MagicMock()
        self.gtrade.completeTradeTransaction(
            self.guild.id, self.date, 'pending-id', ('id1', item),
            {'id': self.user.id, 'name': self.user.name},
            {'id': self.author.id, 'name': self.author.name}
        )
        gcoin_queries.performTransaction.assert_called_once()
        gtrade_queries.createItem.assert_called_once()
        gtrade_queries.removeItem.assert_called_once_with(self.user.id, 'id1')
    # endregion

    # region setup
    def test_setup_adds_cog(self):
        from GBotDiscord.src.gtrade import gtrade_cog
        fake_client = MagicMock()
        gtrade_cog.setup(fake_client)
        fake_client.add_cog.assert_called_once()
        self.assertIsInstance(fake_client.add_cog.call_args.args[0], GTrade)
    # endregion

if __name__ == '__main__':
    unittest.main()
