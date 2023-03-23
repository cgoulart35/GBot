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

        self.user1 = Mock()
        self.user1.id = 12345
        self.user1.name = "user1 name"
        self.user1.mention = "<@!012345678910111213>"
        self.user1.bot = False

        self.user2 = Mock()
        self.user2.id = 13542
        self.user2.name = "user2 name"
        self.user2.mention = "<@!131211109876543210>"
        self.user2.bot = False

        self.author = Mock()
        self.author.id = 54321
        self.author.name = "author name"
        self.author.mention = "<@!012345678910111213>"

        self.icon = Mock()
        self.icon.url = "icon url"

        self.guild = Mock()
        self.guild.id = 12345
        self.guild.name = "guild name"
        self.guild.icon = self.icon
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
        self.ctx.send.assert_called_once_with(f'{self.author.name}, you sent {self.user1.mention} 10.00 GCoin.')

    async def test_wallets_no_users(self):
        self.guild.fetch_members.return_value = AsyncIter([])
        self.ctx.send = AsyncMock()
        await self.gcoin.wallets(self.gcoin, self.ctx)
        self.ctx.send.assert_called_once_with(f'Sorry {self.author.mention}, no users have any positive balances.')

    async def test_wallets_no_positive_balances(self):
        gcoin_queries.getUserBalance = MagicMock(return_value = Decimal('0.00'))
        self.ctx.send = AsyncMock()
        await self.gcoin.wallets(self.gcoin, self.ctx)
        self.ctx.send.assert_called_once_with(f'Sorry {self.author.mention}, no users have any positive balances.')

    async def test_wallets_with_balances(self):
        configuredSideEffects = SideEffectBuilder(0, {
            self.user1.id: Decimal('150.00'),
            self.user2.id: Decimal('500.00'),
        })
        gcoin_queries.getUserBalance = MagicMock(side_effect = configuredSideEffects.side_effect)

        fields = [
            ("1.) user2 name", "`500.00 GCoin`"),
            ("2.) user1 name", "`150.00 GCoin`")
        ]

        pagination.FieldPageSource.__init__ = MagicMock(return_value = None)
        try:
            await self.gcoin.wallets(self.gcoin, self.ctx)
        except:
            pagination.FieldPageSource.__init__.assert_called_once_with(fields, "icon url", "User Wallets", nextcord.Color.yellow(), False, 10)

    async def test_wallet(self):
        pass

    async def test_history(self):
        pass

if __name__ == '__main__':
    unittest.main()