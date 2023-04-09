#region IMPORTS
import unittest
from unittest.mock import MagicMock, Mock, AsyncMock
import nextcord
from nextcord.ext import commands
from nextcord.ext.commands.context import Context

from GBotDiscord.src.patreon import patreon_queries
from GBotDiscord.src.patreon.patreon_cog import Patreon
from GBotDiscord.src.properties import GBotPropertiesManager
from GBotDiscord.src.firebase import GBotFirebaseService
#endregion

# to run this test suite:
#   - execute the following command from the GBot directory: python -m unittest GBotDiscord/test/patreon/patreon_test.py
#   - or use the "Python: Current File" run configuration to run patreon_test.py
#   - or use the "Python: Current File" run configuration to run tests.py to run all test suites
class TestPatreon(unittest.IsolatedAsyncioTestCase):

    @classmethod
    def setUpClass(self):
        print('\nExecuting patreon unit tests...\n')

    @classmethod
    def tearDownClass(self):
        print('\n\nCompleted patreon unit tests.\n')

    def setUp(self):
        GBotPropertiesManager.PATREON_GUILD_ID = 10
        GBotPropertiesManager.PATRON_ROLE_ID = 50
        GBotPropertiesManager.PATREON_IGNORE_GUILDS = [11,12,13]

        patreon_queries.getAllPatrons = MagicMock(return_value = [])

        self.role = Mock()
        self.role.id = 50

        self.author = Mock()
        self.author.id = 54321
        self.author.roles = []

        self.guild1: nextcord.Guild = Mock()
        self.guild1.id = 10
        self.guild1.fetch_member = AsyncMock()
        self.guild1.fetch_member.return_value = self.author

        self.guild2: nextcord.Guild = Mock()
        self.guild2.id = 9
        self.guild2.leave = AsyncMock()

        self.guild3: nextcord.Guild = Mock()
        self.guild3.id = 12
        self.guild3.leave = AsyncMock()

        self.guild4: nextcord.Guild = Mock()
        self.guild4.id = 14
        self.guild4.leave = AsyncMock()

        self.ctx: Context = Mock()
        self.ctx.guild = self.guild1
        self.ctx.author = self.author

        self.client: nextcord.Client = commands.Bot()
        self.client.fetch_guild = AsyncMock()
        self.client.fetch_guild.return_value = self.guild1

        self.patreon: Patreon = Patreon(self.client)

    async def test_patreon_validation_ignore_subscribed_guilds(self):
        patreon_queries.getAllPatrons = MagicMock(side_effect = [
            {
                "1000": {
                    "serverId": "9"
                }
            },
            {
                "1000": {
                    "serverId": "9"
                }
            }
        ])
        self.author.roles = [self.role]
        GBotFirebaseService.remove = MagicMock()
        self.patreon.getAllGuilds = MagicMock()
        self.patreon.getAllGuilds.return_value = [self.guild2]
        await self.patreon.patreon_validation()
        GBotFirebaseService.remove.assert_not_called()
        self.guild2.leave.assert_not_called()

    async def test_patreon_validation_ignore_ignored_guilds(self):
        patreon_queries.getAllPatrons = MagicMock(side_effect = [
            {
                "1000": {
                    "serverId": "12"
                }
            },
            {}
        ])
        GBotFirebaseService.remove = MagicMock()
        self.patreon.getAllGuilds = MagicMock()
        self.patreon.getAllGuilds.return_value = [self.guild3]
        await self.patreon.patreon_validation()
        GBotFirebaseService.remove.assert_not_called()
        self.guild3.leave.assert_not_called()

    async def test_patreon_validation_remove_unsubscribed_guilds(self):
        patreon_queries.getAllPatrons = MagicMock(side_effect = [
            {
                "1000": {
                    "serverId": "14"
                }
            },
            {}
        ])
        GBotFirebaseService.remove = MagicMock()
        self.patreon.getAllGuilds = MagicMock()
        self.patreon.getAllGuilds.return_value = [self.guild4]
        await self.patreon.patreon_validation()
        GBotFirebaseService.remove.assert_called_once_with(["patreon_members", '1000'])
        self.guild4.leave.assert_called_once()

    async def test_patreon(self):
        GBotFirebaseService.set = MagicMock()
        self.ctx.send = AsyncMock()
        await self.patreon.patreon(self.patreon, self.ctx, self.guild1.id)
        GBotFirebaseService.set.assert_any_call(["patreon_members", self.author.id, "serverId"], str(self.guild1.id))
        self.ctx.send.assert_called_once_with('GBot is now accessible in the specified server. Thank you for subscribing and enjoy!')

if __name__ == '__main__':
    unittest.main()