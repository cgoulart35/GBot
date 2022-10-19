#region IMPORTS
import unittest
from unittest.mock import MagicMock, Mock
import nextcord
from nextcord.ext import commands
from nextcord.ext.commands.context import Context

from GBotDiscord import pagination
from GBotDiscord.config import config_queries
from GBotDiscord.config.config_cog import Config
from GBotDiscord.properties import GBotPropertiesManager
from GBotDiscord.firebase import GBotFirebaseService
#endregion

# to run this test suite:
#   - execute the following command from the GBot directory: python -m unittest GBotDiscord/config/config_test.py
#   - or use the "Python: Current File" run configuration to run config_test.py
#   - or use the "Python: Current File" run configuration to run tests.py to run all test suites
class TestConfig(unittest.IsolatedAsyncioTestCase):

    @classmethod
    def setUpClass(self):
        print("\nExecuting config unit tests...\n")

        GBotPropertiesManager.GBOT_VERSION = "5.0"
        self.client: nextcord.Client = commands.Bot()
        self.config: Config = Config(self.client)

        self.icon = Mock()
        self.icon.url = "test"

        self.guild = Mock()
        self.guild.id = 12345
        self.guild.name = "test"
        self.guild.icon = self.icon

        self.ctx: Context = Mock()
        self.ctx.guild = self.guild

    @classmethod
    def tearDownClass(self):
        print("\n\nCompleted config unit tests.\n")

    async def test_on_guild_join(self):
        defaultConfig = {
            "version": "5.0",
            "prefix": ".",
            "toggle_music": False,
            "toggle_gcoin": False,
            "toggle_gtrade": False,
            "toggle_hype": False,
            "toggle_storms": False
        }

        GBotFirebaseService.set = MagicMock()
        await self.config.on_guild_join(self.guild)
        GBotFirebaseService.set.assert_called_once_with(["servers", self.guild.id], defaultConfig)

    async def test_on_guild_remove(self):
        GBotFirebaseService.remove = MagicMock()
        await self.config.on_guild_remove(self.guild)
        GBotFirebaseService.remove.assert_called_once_with(["servers", self.guild.id])

    async def test_on_ready(self):
        config_queries.getAllServers = MagicMock(return_value = {
            "012345678910111213": {
                "version": "1.0"
            }
        })
        config_queries.getAllServerValues = MagicMock(return_value = {
                "version": "1.0"
        })

        GBotFirebaseService.set = MagicMock()
        await self.config.on_ready()
        GBotFirebaseService.set.assert_any_call(["servers", "012345678910111213", "version"], "5.0")
        GBotFirebaseService.set.assert_any_call(["servers", "012345678910111213", "toggle_music"], False)
        GBotFirebaseService.set.assert_any_call(["servers", "012345678910111213", "toggle_gcoin"], False)
        GBotFirebaseService.set.assert_any_call(["servers", "012345678910111213", "toggle_gtrade"], False)
        GBotFirebaseService.set.assert_any_call(["servers", "012345678910111213", "toggle_hype"], False)
        GBotFirebaseService.set.assert_any_call(["servers", "012345678910111213", "toggle_storms"], False)

    async def test_config(self):
        config_queries.getAllServerValues = MagicMock(return_value = {
            "channel_admin": "012345678910111213",
            "channel_storms": "012345678910111213",
            "prefix": ".",
            "role_admin": "012345678910111213",
            "toggle_gcoin": True,
            "toggle_gtrade": True,
            "toggle_hype": True,
            "toggle_music": False,
            "toggle_storms": False,
            "version": "5.0"
        })

        fields = [
            ("\u200b", "\u200b"),
            ("Prefix", "`.`"),
            ("Music Functionality", "`False`"),
            ("GCoin Functionality", "`True`"),
            ("GTrade Functionality", "`True`"),
            ("Hype Functionality", "`True`"),
            ("Storms Functionality", "`False`"),
            ("\u200b", "\u200b"),
            ("Admin Role", "<@&012345678910111213>"),
            ("Admin Channel", "<#012345678910111213>"),
            ("Storms Channel","<#012345678910111213>")
        ]

        pagination.FieldPageSource.__init__ = MagicMock(return_value = None)
        try:
            await self.config.config(self.config, self.ctx)
        except:
            pagination.FieldPageSource.__init__.assert_called_once_with(fields, "test", "GBot Configuration", nextcord.Color.blue(), False, 7)        

    async def test_prefix(self):
        GBotFirebaseService.set = MagicMock()
        try:
            await self.config.prefix(self.config, self.ctx, ".")
        except:
            GBotFirebaseService.set.assert_called_once_with(["servers", self.guild.id, "prefix"], ".") 

    async def test_role(self):
        role = Mock()
        role.id = "012345678910111213"

        GBotFirebaseService.set = MagicMock()
        try:
            await self.config.role(self.config, self.ctx, "admin", role)
        except:
            GBotFirebaseService.set.assert_called_once_with(["servers", self.guild.id, "role_admin"], "012345678910111213") 

    async def test_channel(self):
        channel = Mock()
        channel.id = "012345678910111213"

        GBotFirebaseService.set = MagicMock()
        try:
            await self.config.channel(self.config, self.ctx, "admin", channel)
        except:
            GBotFirebaseService.set.assert_called_once_with(["servers", self.guild.id, "channel_admin"], "012345678910111213") 

        GBotFirebaseService.set = MagicMock()
        try:
            await self.config.channel(self.config, self.ctx, "storms", channel)
        except:
            GBotFirebaseService.set.assert_called_once_with(["servers", self.guild.id, "channel_storms"], "012345678910111213") 

    async def test_toggle(self):
        # turn off gcoin when gtrade and storms are on
        config_queries.getServerValue = MagicMock(args = ['gcoin'], return_value = True)
        config_queries.getServerValue = MagicMock(args = ['gtrade'], return_value = True)
        config_queries.getServerValue = MagicMock(args = ['storms'], return_value = True)
        GBotFirebaseService.set = MagicMock()
        try:
            await self.config.toggle(self.config, self.ctx, "gcoin")
        except:
            GBotFirebaseService.set.assert_any_call(["servers", self.guild.id, "toggle_gcoin"], False)
            GBotFirebaseService.set.assert_any_call(["servers", self.guild.id, "toggle_gtrade"], False)
            GBotFirebaseService.set.assert_any_call(["servers", self.guild.id, "toggle_storms"], False)

        # turn on gtrade when gcoin is off
        config_queries.getServerValue = MagicMock(args = ['gcoin'], return_value = False)
        config_queries.getServerValue = MagicMock(args = ['gtrade'], return_value = False)
        GBotFirebaseService.set = MagicMock()
        try:
            await self.config.toggle(self.config, self.ctx, "gtrade")
        except:
            GBotFirebaseService.set.assert_any_call(["servers", self.guild.id, "toggle_gcoin"], True)
            GBotFirebaseService.set.assert_any_call(["servers", self.guild.id, "toggle_gtrade"], True)

        # turn on storms when gcoin is off
        config_queries.getServerValue = MagicMock(args = ['gcoin'], return_value = False)
        config_queries.getServerValue = MagicMock(args = ['storms'], return_value = False)
        GBotFirebaseService.set = MagicMock()
        try:
            await self.config.toggle(self.config, self.ctx, "storms")
        except:
            GBotFirebaseService.set.assert_any_call(["servers", self.guild.id, "toggle_gcoin"], True)
            GBotFirebaseService.set.assert_any_call(["servers", self.guild.id, "toggle_storms"], True) 

if __name__ == "__main__":
    unittest.main()