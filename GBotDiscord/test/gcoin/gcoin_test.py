#region IMPORTS
import unittest
from unittest.mock import MagicMock, Mock, AsyncMock, patch
import nextcord
from nextcord.ext import commands
from nextcord.ext.commands.context import Context
from datetime import datetime
from decimal import Decimal

from GBotDiscord.test.utils import AsyncIter, SideEffectBuilder
from GBotDiscord.src import pagination
from GBotDiscord.src.config import config_queries
from GBotDiscord.src.gcoin import gcoin_queries
from GBotDiscord.src.gcoin.gcoin_cog import GCoin
from GBotDiscord.src.firebase import GBotFirebaseService
#endregion

# to run this test suite:
#   - execute the following command from the GBot directory: python -m unittest GBotDiscord/test/gcoin/gcoin_test.py
#   - or use the "Python: Current File" run configuration to run gcoin_test.py
#   - or use the "Python: Current File" run configuration to run tests.py to run all test suites
class TestGCoin(unittest.IsolatedAsyncioTestCase):

    @classmethod
    def setUpClass(self):
        print('\nExecuting gcoin unit tests...\n')

    @classmethod
    def tearDownClass(self):
        print('\n\nCompleted gcoin unit tests.\n')

    def setUp(self):
        self.client: nextcord.Client = commands.Bot()
        self.gcoin: GCoin = GCoin(self.client)

        self.avatar = Mock()
        self.avatar.url = "avatar url"

        self.role = Mock()
        self.role.id = 10

        self.user1 = Mock()
        self.user1.id = 12345
        self.user1.name = "user1 name"
        self.user1.mention = "<@!012345678910111213>"
        self.user1.bot = False
        self.user1.avatar = self.avatar

        self.user2 = Mock()
        self.user2.id = 13542
        self.user2.name = "user2 name"
        self.user2.mention = "<@!131211109876543210>"
        self.user2.bot = False

        self.author = Mock()
        self.author.id = 54321
        self.author.name = "author name"
        self.author.mention = "<@!012345678910111213>"
        self.author.avatar = self.avatar
        self.author.roles = [self.role]

        self.icon = Mock()
        self.icon.url = "icon url"

        self.guild = Mock()
        self.guild.id = 12345
        self.guild.name = "guild name"
        self.guild.icon = self.icon
        self.guild.owner_id = 0
        self.guild.fetch_members = MagicMock()
        self.guild.fetch_members.return_value = AsyncIter([self.user1, self.user2])

        self.ctx: Context = Mock()
        self.ctx.guild = self.guild
        self.ctx.author = self.author

        self.date = datetime.now().strftime("%m/%d/%y %I:%M:%S %p")
        with patch('GBotDiscord.src.gcoin.gcoin_cog.datetime') as mock_date:
            mock_date.now.return_value = self.date

    async def test_send_user_is_bot_error(self):
        self.user1.bot = True
        self.ctx.send = AsyncMock()
        await self.gcoin.send(self.gcoin, self.ctx, self.user1, 10)
        self.ctx.send.assert_called_once_with(f'Sorry {self.author.mention}, please specify a user in this guild.')

    async def test_send_user_not_in_guild_error(self):
        self.guild.fetch_members.return_value = AsyncIter([])
        self.ctx.send = AsyncMock()
        await self.gcoin.send(self.gcoin, self.ctx, self.user1, 10)
        self.ctx.send.assert_called_once_with(f'Sorry {self.author.mention}, please specify a user in this guild.')

    async def test_send_real_user_error(self):
        self.user1.id = None
        self.ctx.send = AsyncMock()
        await self.gcoin.send(self.gcoin, self.ctx, self.user1, 10)
        self.ctx.send.assert_called_once_with(f'Sorry {self.author.mention}, please specify a valid user.')

    async def test_send_send_yourself_error(self):
        self.user1.id = self.author.id
        self.ctx.send = AsyncMock()
        await self.gcoin.send(self.gcoin, self.ctx, self.user1, 10)
        self.ctx.send.assert_called_once_with(f'Sorry {self.author.mention}, you can not send GCoin to yourself.')

    async def test_send_positive_transaction_error(self):
        self.ctx.send = AsyncMock()
        await self.gcoin.send(self.gcoin, self.ctx, self.user1, -10)
        self.ctx.send.assert_called_once_with(f'Sorry {self.author.mention}, you can not send a non-positive amount.')

    async def test_send_insufficient_funds_error(self):
        gcoin_queries.getUserBalance = MagicMock(return_value = Decimal('9.00'))
        self.ctx.send = AsyncMock()
        await self.gcoin.send(self.gcoin, self.ctx, self.user1, 10)
        self.ctx.send.assert_called_once_with(f'Sorry {self.author.mention}, you have insufficient funds.')

    async def test_send_invalid_amount_error(self):
        self.ctx.send = AsyncMock()
        await self.gcoin.send(self.gcoin, self.ctx, self.user1, "ten")
        self.ctx.send.assert_called_once_with(f'Sorry {self.author.mention}, please enter a valid amount.')

    async def test_send_success(self):
        gcoin_queries.getUserBalance = MagicMock(return_value = Decimal('11.00'))
        GBotFirebaseService.set = MagicMock()
        GBotFirebaseService.push = MagicMock()
        self.ctx.send = AsyncMock()
        await self.gcoin.send(self.gcoin, self.ctx, self.user1, 10)
        GBotFirebaseService.set.assert_any_call(["gcoin", self.user1.id, "balance"], "21.00")
        GBotFirebaseService.set.assert_any_call(["gcoin", self.author.id, "balance"], "1.00")
        GBotFirebaseService.push.assert_any_call(["gcoin", self.user1.id, "history"], {'gcoin': f'+10.00', 'other': self.author.name, 'date': self.date, 'memo': 'received'})
        GBotFirebaseService.push.assert_any_call(["gcoin", self.author.id, "history"], {'gcoin': f'-10.00', 'other': self.user1.name, 'date': self.date, 'memo': 'sent'})
        self.ctx.send.assert_called_once_with(f'{self.author.mention}, you sent {self.user1.mention} 10.00 GCoin.')

    async def test_wallets_no_users(self):
        self.guild.fetch_members.return_value = AsyncIter([])
        gcoin_queries.getAllUserBalances = MagicMock(return_value = {})
        self.ctx.send = AsyncMock()
        await self.gcoin.wallets(self.gcoin, self.ctx)
        self.ctx.send.assert_called_once_with(f'Sorry {self.author.mention}, no users have any positive balances.')

    async def test_wallets_no_positive_balances(self):
        # users exist but all have a 0 balance in the bulk-fetched dict
        gcoin_queries.getAllUserBalances = MagicMock(return_value = {
            str(self.user1.id): {'balance': '0.00'},
            str(self.user2.id): {'balance': '0.00'},
        })
        self.ctx.send = AsyncMock()
        await self.gcoin.wallets(self.gcoin, self.ctx)
        self.ctx.send.assert_called_once_with(f'Sorry {self.author.mention}, no users have any positive balances.')

    async def test_wallets_with_balances(self):
        fields = [
            ("1.) user2 name", "`500.00 GCoin`"),
            ("2.) user1 name", "`150.00 GCoin`")
        ]
        gcoin_queries.getAllUserBalances = MagicMock(return_value = {
            str(self.user1.id): {'balance': '150.00'},
            str(self.user2.id): {'balance': '500.00'},
        })
        pagination.FieldPageSource.__init__ = MagicMock(return_value = None)
        try:
            await self.gcoin.wallets(self.gcoin, self.ctx)
        except:
            pagination.FieldPageSource.__init__.assert_called_once_with(fields, self.icon.url, "User Wallets", nextcord.Color.yellow(), False, 10)

    async def test_wallets_member_not_in_db_balance_falls_back_to_zero(self):
        # user1 has a balance row, user2 does not — user2's balance defaults to 0 and is filtered out
        gcoin_queries.getAllUserBalances = MagicMock(return_value = {
            str(self.user1.id): {'balance': '100.00'}
        })
        pagination.FieldPageSource.__init__ = MagicMock(return_value = None)
        try:
            await self.gcoin.wallets(self.gcoin, self.ctx)
        except:
            pagination.FieldPageSource.__init__.assert_called_once_with([("1.) user1 name", "`100.00 GCoin`")], self.icon.url, "User Wallets", nextcord.Color.yellow(), False, 10)

    async def test_wallets_no_guild_icon(self):
        self.guild.icon = None
        gcoin_queries.getAllUserBalances = MagicMock(return_value = {
            str(self.user1.id): {'balance': '100.00'}
        })
        pagination.FieldPageSource.__init__ = MagicMock(return_value = None)
        try:
            await self.gcoin.wallets(self.gcoin, self.ctx)
        except:
            # second positional arg (thumbnailUrl) should be None when guild.icon is None
            self.assertIsNone(pagination.FieldPageSource.__init__.call_args.args[1])

    async def test_wallets_defers_for_interaction(self):
        interaction = Mock(spec = nextcord.Interaction)
        interaction.guild = self.guild
        interaction.response = Mock()
        interaction.response.defer = AsyncMock()
        interaction.send = AsyncMock()
        self.guild.fetch_members.return_value = AsyncIter([])
        gcoin_queries.getAllUserBalances = MagicMock(return_value = {})
        await self.gcoin.commonWallets(interaction, self.author)
        interaction.response.defer.assert_called_once()

    async def test_wallet_private_message_user_specified(self):
        self.ctx.guild = None
        self.ctx.send = AsyncMock()
        await self.gcoin.wallet(self.gcoin, self.ctx, self.user1)
        self.ctx.send.assert_called_once_with(f"Sorry {self.author.mention}, please use this command on other users in a server.")

    async def test_wallet_server_user_specified_not_in_guild(self):
        self.guild.fetch_members.return_value = AsyncIter([])
        self.ctx.send = AsyncMock()
        await self.gcoin.wallet(self.gcoin, self.ctx, self.user1)
        self.ctx.send.assert_called_once_with(f"Sorry {self.author.mention}, please specify a user in this guild.")

    async def test_wallet_server_user_specified_bot(self):
        self.user1.bot = True
        self.ctx.send = AsyncMock()
        await self.gcoin.wallet(self.gcoin, self.ctx, self.user1)
        self.ctx.send.assert_called_once_with(f"Sorry {self.author.mention}, please specify a user in this guild.")

    async def test_wallet_private_message_no_user_specified(self):
        expectedEmbed = nextcord.Embed(color = nextcord.Color.yellow(), title = f"{self.author.name}'s Wallet")
        expectedEmbed.add_field(name = 'Wallet', value = f"`{Decimal('5.00')}`", inline = False)
        expectedEmbed.set_thumbnail(url = self.avatar.url)

        self.ctx.guild = None
        gcoin_queries.getUserBalance = MagicMock(return_value = Decimal('5.00'))
        self.ctx.send = AsyncMock()
        await self.gcoin.wallet(self.gcoin, self.ctx)
        actualEmbed = self.ctx.send.call_args[1]["embed"]
        self.assertEqual(expectedEmbed.color, actualEmbed.color)
        self.assertEqual(expectedEmbed.title, actualEmbed.title)
        self.assertEqual(expectedEmbed.thumbnail.url, actualEmbed.thumbnail.url)
        self.assertEqual(expectedEmbed.fields[0].inline, actualEmbed.fields[0].inline)
        self.assertEqual(expectedEmbed.fields[0].name, actualEmbed.fields[0].name)
        self.assertEqual(expectedEmbed.fields[0].value, actualEmbed.fields[0].value)

    async def test_wallet_server_user_specified(self):
        expectedEmbed = nextcord.Embed(color = nextcord.Color.yellow(), title = f"{self.user1.name}'s Wallet")
        expectedEmbed.add_field(name = 'Wallet', value = f"`{Decimal('5.00')}`", inline = False)
        expectedEmbed.set_thumbnail(url = self.avatar.url)

        gcoin_queries.getUserBalance = MagicMock(return_value = Decimal('5.00'))
        self.ctx.send = AsyncMock()
        await self.gcoin.wallet(self.gcoin, self.ctx, self.user1)
        actualEmbed = self.ctx.send.call_args[1]["embed"]
        self.assertEqual(expectedEmbed.color, actualEmbed.color)
        self.assertEqual(expectedEmbed.title, actualEmbed.title)
        self.assertEqual(expectedEmbed.thumbnail.url, actualEmbed.thumbnail.url)
        self.assertEqual(expectedEmbed.fields[0].inline, actualEmbed.fields[0].inline)
        self.assertEqual(expectedEmbed.fields[0].name, actualEmbed.fields[0].name)
        self.assertEqual(expectedEmbed.fields[0].value, actualEmbed.fields[0].value)

    async def test_wallet_server_no_user_specified(self):
        expectedEmbed = nextcord.Embed(color = nextcord.Color.yellow(), title = f"{self.author.name}'s Wallet")
        expectedEmbed.add_field(name = 'Wallet', value = f"`{Decimal('5.00')}`", inline = False)
        expectedEmbed.set_thumbnail(url = self.avatar.url)

        gcoin_queries.getUserBalance = MagicMock(return_value = Decimal('5.00'))
        self.ctx.send = AsyncMock()
        await self.gcoin.wallet(self.gcoin, self.ctx)
        actualEmbed = self.ctx.send.call_args[1]["embed"]
        self.assertEqual(expectedEmbed.color, actualEmbed.color)
        self.assertEqual(expectedEmbed.title, actualEmbed.title)
        self.assertEqual(expectedEmbed.thumbnail.url, actualEmbed.thumbnail.url)
        self.assertEqual(expectedEmbed.fields[0].inline, actualEmbed.fields[0].inline)
        self.assertEqual(expectedEmbed.fields[0].name, actualEmbed.fields[0].name)
        self.assertEqual(expectedEmbed.fields[0].value, actualEmbed.fields[0].value)

    async def test_wallet_server_user_specified_no_avatar(self):
        self.user1.avatar = None
        gcoin_queries.getUserBalance = MagicMock(return_value = Decimal('5.00'))
        self.ctx.send = AsyncMock()
        await self.gcoin.wallet(self.gcoin, self.ctx, self.user1)
        actualEmbed = self.ctx.send.call_args[1]["embed"]
        # no set_thumbnail call means embed.thumbnail.url is None
        self.assertIsNone(actualEmbed.thumbnail.url)

    async def test_wallet_server_no_user_specified_no_avatar(self):
        self.author.avatar = None
        gcoin_queries.getUserBalance = MagicMock(return_value = Decimal('5.00'))
        self.ctx.send = AsyncMock()
        await self.gcoin.wallet(self.gcoin, self.ctx)
        actualEmbed = self.ctx.send.call_args[1]["embed"]
        self.assertIsNone(actualEmbed.thumbnail.url)

    async def test_history_private_message_user_specified(self):
        self.ctx.guild = None
        self.ctx.send = AsyncMock()
        await self.gcoin.history(self.gcoin, self.ctx, self.user1)
        self.ctx.send.assert_called_once_with(f"Sorry {self.author.mention}, please use this command on other users in a server as an admin.")

    async def test_history_server_user_specified_not_in_guild(self):
        self.guild.fetch_members.return_value = AsyncIter([])
        self.ctx.send = AsyncMock()
        await self.gcoin.history(self.gcoin, self.ctx, self.user1)
        self.ctx.send.assert_called_once_with(f"Sorry {self.author.mention}, please specify a user in this guild.")

    async def test_history_server_user_specified_bot(self):
        self.user1.bot = True
        self.ctx.send = AsyncMock()
        await self.gcoin.history(self.gcoin, self.ctx, self.user1)
        self.ctx.send.assert_called_once_with(f"Sorry {self.author.mention}, please specify a user in this guild.")

    async def test_history_server_user_specified_and_author_not_admin(self):
        config_queries.getServerValue = MagicMock(return_value = '5')
        self.ctx.send = AsyncMock()
        await self.gcoin.history(self.gcoin, self.ctx, self.user1)
        self.ctx.send.assert_called_once_with(f"Sorry {self.author.mention}, you need to be an admin to view other user's history.")

    async def test_history_server_user_specified_and_no_history(self):
        config_queries.getServerValue = MagicMock(return_value = '10')
        gcoin_queries.getUserTransactionHistory = MagicMock(return_value = None)
        self.ctx.send = AsyncMock()
        await self.gcoin.history(self.gcoin, self.ctx, self.user1)
        self.ctx.send.assert_called_once_with(f'Sorry {self.author.mention}, {self.user1.mention} has no transaction history.')

    async def test_history_server_no_user_specified_and_no_history(self):
        gcoin_queries.getUserTransactionHistory = MagicMock(return_value = None)
        self.ctx.send = AsyncMock()
        await self.gcoin.history(self.gcoin, self.ctx)
        self.ctx.send.assert_called_once_with(f'Sorry {self.author.mention}, you have no transaction history.')

    async def test_history_private_message_no_user_specified_and_no_history(self):
        self.ctx.guild = None
        gcoin_queries.getUserTransactionHistory = MagicMock(return_value = None)
        self.ctx.send = AsyncMock()
        await self.gcoin.history(self.gcoin, self.ctx)
        self.ctx.send.assert_called_once_with(f'Sorry {self.author.mention}, you have no transaction history.')

    async def test_history_server_user_specified_with_history(self):
        fields = [
            ("1.) user2 (sent)", "`03/26/23 02:50 PM`\n`-10.00 GCoin`"),
            ("2.) Halo (Participation)", "`03/26/22 10:00 PM`\n`+0.50 GCoin`")
        ]

        config_queries.getServerValue = MagicMock(return_value = '10')
        gcoin_queries.getUserTransactionHistory = MagicMock(return_value = {
                "trx1": {
                    "date": "03/26/22 10:00:07 PM",
                    "gcoin": "+0.50",
                    "memo": "Participation",
                    "other": "Halo"
                },
                "trx2": {
                    "date": "03/26/23 02:50:00 PM",
                    "gcoin": "-10.00",
                    "memo": "sent",
                    "other": "user2"
                }
        })
        pagination.FieldPageSource.__init__ = MagicMock(return_value = None)
        try:
            await self.gcoin.history(self.gcoin, self.ctx, self.user1)
        except:
            pagination.FieldPageSource.__init__.assert_called_once_with(fields, self.avatar.url, f"{self.user1.name}'s Transactions", nextcord.Color.yellow(), False, 10)

    async def test_history_server_no_user_specified_with_history(self):
        fields = [
            ("1.) user2 (sent)", "`03/26/23 02:50 PM`\n`-10.00 GCoin`"),
            ("2.) Halo (Participation)", "`03/26/22 10:00 PM`\n`+0.50 GCoin`")
        ]

        gcoin_queries.getUserTransactionHistory = MagicMock(return_value = {
                "trx1": {
                    "date": "03/26/22 10:00:07 PM",
                    "gcoin": "+0.50",
                    "memo": "Participation",
                    "other": "Halo"
                },
                "trx2": {
                    "date": "03/26/23 02:50:00 PM",
                    "gcoin": "-10.00",
                    "memo": "sent",
                    "other": "user2"
                }
        })
        pagination.FieldPageSource.__init__ = MagicMock(return_value = None)
        try:
            await self.gcoin.history(self.gcoin, self.ctx)
        except:
            pagination.FieldPageSource.__init__.assert_called_once_with(fields, self.avatar.url, f"{self.author.name}'s Transactions", nextcord.Color.yellow(), False, 10)

    async def test_history_private_message_no_user_specified_with_history(self):
        fields = [
            ("1.) user2 (sent)", "`03/26/23 02:50 PM`\n`-10.00 GCoin`"),
            ("2.) Halo (Participation)", "`03/26/22 10:00 PM`\n`+0.50 GCoin`")
        ]

        self.ctx.guild = None
        gcoin_queries.getUserTransactionHistory = MagicMock(return_value = {
                "trx1": {
                    "date": "03/26/22 10:00:07 PM",
                    "gcoin": "+0.50",
                    "memo": "Participation",
                    "other": "Halo"
                },
                "trx2": {
                    "date": "03/26/23 02:50:00 PM",
                    "gcoin": "-10.00",
                    "memo": "sent",
                    "other": "user2"
                }
        })
        pagination.FieldPageSource.__init__ = MagicMock(return_value = None)
        try:
            await self.gcoin.history(self.gcoin, self.ctx)
        except:
            pagination.FieldPageSource.__init__.assert_called_once_with(fields, self.avatar.url, f"{self.author.name}'s Transactions", nextcord.Color.yellow(), False, 10)

    async def test_history_defers_for_interaction(self):
        interaction = Mock(spec = nextcord.Interaction)
        interaction.guild = self.guild
        interaction.response = Mock()
        interaction.response.defer = AsyncMock()
        interaction.send = AsyncMock()
        gcoin_queries.getUserTransactionHistory = MagicMock(return_value = None)
        await self.gcoin.commonHistory(interaction, self.author, None)
        interaction.response.defer.assert_called_once()

    async def test_history_server_user_specified_no_avatar(self):
        # user.avatar is None branch in the user-specified path
        self.user1.avatar = None
        config_queries.getServerValue = MagicMock(return_value = '10')  # author has admin role
        gcoin_queries.getUserTransactionHistory = MagicMock(return_value = {
            "trx1": {"date": "03/26/22 10:00:07 PM", "gcoin": "+0.50", "memo": "received", "other": "Halo"}
        })
        pagination.FieldPageSource.__init__ = MagicMock(return_value = None)
        try:
            await self.gcoin.history(self.gcoin, self.ctx, self.user1)
        except:
            # thumbnailUrl (second positional arg) should be None when user has no avatar
            self.assertIsNone(pagination.FieldPageSource.__init__.call_args.args[1])

    async def test_history_server_no_user_specified_no_avatar(self):
        # author.avatar is None branch in the no-user path
        self.author.avatar = None
        gcoin_queries.getUserTransactionHistory = MagicMock(return_value = {
            "trx1": {"date": "03/26/22 10:00:07 PM", "gcoin": "+0.50", "memo": "received", "other": "Halo"}
        })
        pagination.FieldPageSource.__init__ = MagicMock(return_value = None)
        try:
            await self.gcoin.history(self.gcoin, self.ctx)
        except:
            self.assertIsNone(pagination.FieldPageSource.__init__.call_args.args[1])

    async def test_history_loop_exhausts_range_before_history(self):
        # set NUM_TRX_HISTORY_TO_DISPLAY=1 so range(1) exhausts before history's break — exercises
        # the "for loop exits naturally" branch at line 225 (vs. break at i == len(sortedHistory)).
        self.gcoin.NUM_TRX_HISTORY_TO_DISPLAY = 1
        gcoin_queries.getUserTransactionHistory = MagicMock(return_value = {
            "trx1": {"date": "03/26/22 10:00:07 PM", "gcoin": "+0.50", "memo": "a", "other": "Halo"},
            "trx2": {"date": "03/26/23 02:50:00 PM", "gcoin": "-10.00", "memo": "b", "other": "user2"},
        })
        pagination.FieldPageSource.__init__ = MagicMock(return_value = None)
        try:
            await self.gcoin.history(self.gcoin, self.ctx)
        except:
            # only one entry shown — the loop range ran out first
            self.assertEqual(len(pagination.FieldPageSource.__init__.call_args.args[0]), 1)

    async def test_sendSlash_delegates_to_commonSend(self):
        self.gcoin.commonSend = AsyncMock()
        interaction = Mock(spec = nextcord.Interaction)
        interaction.user = self.author
        await self.gcoin.sendSlash(interaction, self.user1, 10)
        self.gcoin.commonSend.assert_awaited_once_with(interaction, self.author, self.user1, Decimal('10'))

    async def test_walletsSlash_delegates_to_commonWallets(self):
        self.gcoin.commonWallets = AsyncMock()
        interaction = Mock(spec = nextcord.Interaction)
        interaction.user = self.author
        await self.gcoin.walletsSlash(interaction)
        self.gcoin.commonWallets.assert_awaited_once_with(interaction, self.author)

    async def test_walletSlash_delegates_to_commonWallet(self):
        self.gcoin.commonWallet = AsyncMock()
        interaction = Mock(spec = nextcord.Interaction)
        interaction.user = self.author
        await self.gcoin.walletSlash(interaction, self.user1)
        self.gcoin.commonWallet.assert_awaited_once_with(interaction, self.author, self.user1)

    async def test_historySlash_delegates_to_commonHistory(self):
        self.gcoin.commonHistory = AsyncMock()
        interaction = Mock(spec = nextcord.Interaction)
        interaction.user = self.author
        await self.gcoin.historySlash(interaction, self.user1)
        self.gcoin.commonHistory.assert_awaited_once_with(interaction, self.author, self.user1)

    def test_setup_adds_cog(self):
        from GBotDiscord.src.gcoin import gcoin_cog
        client = MagicMock()
        gcoin_cog.setup(client)
        client.add_cog.assert_called_once()
        addedCog = client.add_cog.call_args[0][0]
        self.assertIsInstance(addedCog, GCoin)

if __name__ == '__main__':
    unittest.main()