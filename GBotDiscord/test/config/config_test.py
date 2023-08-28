#region IMPORTS
import unittest
from unittest.mock import MagicMock, Mock, AsyncMock
import nextcord
from nextcord.ext import commands
from nextcord.ext.commands.context import Context

from GBotDiscord.test.utils import SideEffectBuilder
from GBotDiscord.src import utils
from GBotDiscord.src import pagination
from GBotDiscord.src.config import config_queries
from GBotDiscord.src.config.config_cog import Config
from GBotDiscord.src.properties import GBotPropertiesManager
from GBotDiscord.src.firebase import GBotFirebaseService
#endregion

# to run this test suite:
#   - execute the following command from the GBot directory: python -m unittest GBotDiscord/test/config/config_test.py
#   - or use the "Python: Current File" run configuration to run config_test.py
#   - or use the "Python: Current File" run configuration to run tests.py to run all test suites
class TestConfig(unittest.IsolatedAsyncioTestCase):

    @classmethod
    def setUpClass(self):
        print("\nExecuting config unit tests...\n")

    @classmethod
    def tearDownClass(self):
        print("\n\nCompleted config unit tests.\n")

    def setUp(self):
        GBotPropertiesManager.GBOT_VERSION = "7.0"

        self.icon = Mock()
        self.icon.url = "icon url"

        self.guild = Mock()
        self.guild.id = 12345
        self.guild.name = "guild name"
        self.guild.icon = self.icon

        self.ctx: Context = Mock()
        self.ctx.guild = self.guild

        self.interaction: nextcord.Interaction = Mock()
        self.interaction.guild = self.guild

        self.client: nextcord.Client = commands.Bot()
        self.client.change_presence = AsyncMock()

        self.config: Config = Config(self.client)
        self.config.presence_activities.append(nextcord.Game(f'GBot {GBotPropertiesManager.GBOT_VERSION}'))
        self.config.presence_activities.append(nextcord.Activity(type = nextcord.ActivityType.listening, name = " slash commands"))
        self.config.presence_activities.append(nextcord.Activity(type = nextcord.ActivityType.watching, name = " user messages"))

    async def test_on_guild_join(self):
        defaultConfig = {
            "version": "7.0",
            "prefix": ".",
            "toggle_music": False,
            "toggle_gcoin": False,
            "toggle_gtrade": False,
            "toggle_hype": False,
            "toggle_storms": False,
            "toggle_who_dis": False,
            "toggle_legacy_prefix_commands": False
        }

        GBotFirebaseService.set = MagicMock()
        await self.config.on_guild_join(self.guild)
        GBotFirebaseService.set.assert_called_once_with(["servers", self.guild.id], defaultConfig)

    async def test_on_guild_remove(self):
        GBotFirebaseService.remove = MagicMock()
        await self.config.on_guild_remove(self.guild)
        GBotFirebaseService.remove.assert_called_once_with(["servers", self.guild.id])

    async def test_on_ready(self):
        utils.filterGuildsForInstance = MagicMock(return_value = {
            "012345678910111213": {
                "version": "1.0"
            }
        })
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
        GBotFirebaseService.set.assert_any_call(["servers", "012345678910111213", "version"], "7.0")
        GBotFirebaseService.set.assert_any_call(["servers", "012345678910111213", "toggle_music"], False)
        GBotFirebaseService.set.assert_any_call(["servers", "012345678910111213", "toggle_gcoin"], False)
        GBotFirebaseService.set.assert_any_call(["servers", "012345678910111213", "toggle_gtrade"], False)
        GBotFirebaseService.set.assert_any_call(["servers", "012345678910111213", "toggle_hype"], False)
        GBotFirebaseService.set.assert_any_call(["servers", "012345678910111213", "toggle_storms"], False)
        GBotFirebaseService.set.assert_any_call(["servers", "012345678910111213", "toggle_who_dis"], False)
        GBotFirebaseService.set.assert_any_call(["servers", "012345678910111213", "toggle_legacy_prefix_commands"], False)

    async def test_loop_presence(self):
        await self.config.loop_presence()
        self.assertEqual(1, self.config.presence_index)
        self.assertEqual(1, self.client.change_presence.await_count)

        await self.config.loop_presence()
        self.assertEqual(2, self.config.presence_index)
        self.assertEqual(2, self.client.change_presence.await_count)

        await self.config.loop_presence()
        self.assertEqual(0, self.config.presence_index)
        self.assertEqual(3, self.client.change_presence.await_count)

    async def test_config(self):
        fields = [
            ("\u200b", "\u200b"),
            ("Prefix", "`.`"),
            ("Music Functionality", "`False`"),
            ("GCoin Functionality", "`True`"),
            ("GTrade Functionality", "`True`"),
            ("Hype Functionality", "`True`"),
            ("Storms Functionality", "`False`"),
            ("Who Dis Functionality", "`False`"),
            ("Legacy Prefix Commands", "`False`"),
            ("\u200b", "\u200b"),
            ("Admin Role", "<@&012345678910111213>"),
            ("Who Dis Role", "<@&012345678910111213>"),
            ("Admin Channel", "<#012345678910111213>"),
            ("Storms Channel","<#012345678910111213>")
        ]

        config_queries.getAllServerValues = MagicMock(return_value = {
            "channel_admin": "012345678910111213",
            "channel_storms": "012345678910111213",
            "prefix": ".",
            "role_admin": "012345678910111213",
            "role_who_dis": "012345678910111213",
            "toggle_gcoin": True,
            "toggle_gtrade": True,
            "toggle_hype": True,
            "toggle_music": False,
            "toggle_storms": False,
            "toggle_who_dis": False,
            "toggle_legacy_prefix_commands": False,
            "version": "7.0"
        })
        pagination.FieldPageSource.__init__ = MagicMock(return_value = None)
        try:
            await self.config.config(self.config, self.ctx)
        except:
            pagination.FieldPageSource.__init__.assert_called_once_with(fields, "icon url", "GBot Configuration", nextcord.Color.blue(), False, 9)

    async def test_config_slash(self):
        fields = [
            ("\u200b", "\u200b"),
            ("Prefix", "`.`"),
            ("Music Functionality", "`False`"),
            ("GCoin Functionality", "`True`"),
            ("GTrade Functionality", "`True`"),
            ("Hype Functionality", "`True`"),
            ("Storms Functionality", "`False`"),
            ("Who Dis Functionality", "`False`"),
            ("Legacy Prefix Commands", "`False`"),
            ("\u200b", "\u200b"),
            ("Admin Role", "<@&012345678910111213>"),
            ("Who Dis Role", "<@&012345678910111213>"),
            ("Admin Channel", "<#012345678910111213>"),
            ("Storms Channel","<#012345678910111213>")
        ]

        config_queries.getAllServerValues = MagicMock(return_value = {
            "channel_admin": "012345678910111213",
            "channel_storms": "012345678910111213",
            "prefix": ".",
            "role_admin": "012345678910111213",
            "role_who_dis": "012345678910111213",
            "toggle_gcoin": True,
            "toggle_gtrade": True,
            "toggle_hype": True,
            "toggle_music": False,
            "toggle_storms": False,
            "toggle_who_dis": False,
            "toggle_legacy_prefix_commands": False,
            "version": "7.0"
        })
        pagination.FieldPageSource.__init__ = MagicMock(return_value = None)
        try:
            await self.config.configSlash(self.interaction)
        except:
            pagination.FieldPageSource.__init__.assert_called_once_with(fields, "icon url", "GBot Configuration", nextcord.Color.blue(), False, 9)

    async def test_prefix(self):
        GBotFirebaseService.set = MagicMock()
        self.ctx.send = AsyncMock()
        await self.config.prefix(self.config, self.ctx, ".")
        GBotFirebaseService.set.assert_called_once_with(["servers", self.guild.id, "prefix"], ".")
        self.ctx.send.assert_called_once_with(f'Prefix set to: .')

    async def test_prefix_slash(self):
        GBotFirebaseService.set = MagicMock()
        self.interaction.send = AsyncMock()
        await self.config.prefixSlash(self.interaction, ".")
        GBotFirebaseService.set.assert_called_once_with(["servers", self.guild.id, "prefix"], ".")
        self.interaction.send.assert_called_once_with(f'Prefix set to: .')

    async def test_role(self):
        role = Mock()
        role.id = 12345
        role.mention = "role mention"

        GBotFirebaseService.set = MagicMock()
        self.ctx.send = AsyncMock()
        await self.config.role(self.config, self.ctx, "admin", role)
        GBotFirebaseService.set.assert_called_once_with(["servers", self.guild.id, "role_admin"], "12345")
        self.ctx.send.assert_called_once_with(f'Admin role set to: {role.mention}')

    async def test_role_slash(self):
        role = Mock()
        role.id = 12345
        role.mention = "role mention"

        GBotFirebaseService.set = MagicMock()
        self.interaction.send = AsyncMock()
        await self.config.roleSlash(self.interaction, "admin", role)
        GBotFirebaseService.set.assert_called_once_with(["servers", self.guild.id, "role_admin"], "12345")
        self.interaction.send.assert_called_once_with(f'Admin role set to: {role.mention}')

    async def test_channel(self):
        channel = Mock()
        channel.id = 12345
        channel.mention = "channel mention"

        GBotFirebaseService.set = MagicMock()
        self.ctx.send = AsyncMock()
        await self.config.channel(self.config, self.ctx, "admin", channel)
        GBotFirebaseService.set.assert_called_once_with(["servers", self.guild.id, "channel_admin"], "12345")
        self.ctx.send.assert_called_once_with(f'Admin channel set to: {channel.mention}')

        GBotFirebaseService.set = MagicMock()
        self.ctx.send = AsyncMock()
        await self.config.channel(self.config, self.ctx, "storms", channel)
        GBotFirebaseService.set.assert_called_once_with(["servers", self.guild.id, "channel_storms"], "12345")
        self.ctx.send.assert_called_once_with(f'Storms channel set to: {channel.mention}')

    async def test_channel_slash(self):
        channel = Mock()
        channel.id = 12345
        channel.mention = "channel mention"

        GBotFirebaseService.set = MagicMock()
        self.interaction.send = AsyncMock()
        await self.config.channelSlash(self.interaction, "admin", channel)
        GBotFirebaseService.set.assert_called_once_with(["servers", self.guild.id, "channel_admin"], "12345")
        self.interaction.send.assert_called_once_with(f'Admin channel set to: {channel.mention}')

        GBotFirebaseService.set = MagicMock()
        self.interaction.send = AsyncMock()
        await self.config.channelSlash(self.interaction, "storms", channel)
        GBotFirebaseService.set.assert_called_once_with(["servers", self.guild.id, "channel_storms"], "12345")
        self.interaction.send.assert_called_once_with(f'Storms channel set to: {channel.mention}')

    async def test_toggle(self):
        # turn off gcoin when gtrade and storms are on
        configuredSideEffects = SideEffectBuilder(1, {
            'toggle_gcoin': True,
            'toggle_gtrade': True,
            'toggle_storms': True,
        })
        config_queries.getServerValue = MagicMock(side_effect = configuredSideEffects.side_effect)
        GBotFirebaseService.set = MagicMock()
        self.ctx.send = AsyncMock()
        await self.config.toggle(self.config, self.ctx, "gcoin")
        GBotFirebaseService.set.assert_any_call(["servers", self.guild.id, "toggle_gcoin"], False)
        GBotFirebaseService.set.assert_any_call(["servers", self.guild.id, "toggle_gtrade"], False)
        GBotFirebaseService.set.assert_any_call(["servers", self.guild.id, "toggle_storms"], False)
        self.ctx.send.assert_called_once_with(f'All GCoin functionality has been disabled. Dependents disabled: GTrade Storms')

        # turn on gtrade when gcoin is off
        configuredSideEffects = SideEffectBuilder(1, {
            'toggle_gcoin': False,
            'toggle_gtrade': False,
        })
        config_queries.getServerValue = MagicMock(side_effect = configuredSideEffects.side_effect)
        GBotFirebaseService.set = MagicMock()
        self.ctx.send = AsyncMock()
        await self.config.toggle(self.config, self.ctx, "gtrade")
        GBotFirebaseService.set.assert_any_call(["servers", self.guild.id, "toggle_gcoin"], True)
        GBotFirebaseService.set.assert_any_call(["servers", self.guild.id, "toggle_gtrade"], True)
        self.ctx.send.assert_called_once_with(f'All GTrade functionality has been enabled. Dependencies enabled: GCoin')

        # turn on storms when gcoin is off
        configuredSideEffects = SideEffectBuilder(1, {
            'toggle_gcoin': False,
            'toggle_storms': False,
        })
        config_queries.getServerValue = MagicMock(side_effect = configuredSideEffects.side_effect)
        GBotFirebaseService.set = MagicMock()
        self.ctx.send = AsyncMock()
        await self.config.toggle(self.config, self.ctx, "storms")
        GBotFirebaseService.set.assert_any_call(["servers", self.guild.id, "toggle_gcoin"], True)
        GBotFirebaseService.set.assert_any_call(["servers", self.guild.id, "toggle_storms"], True)
        self.ctx.send.assert_called_once_with(f'All Storms functionality has been enabled. Dependencies enabled: GCoin')

    async def test_toggle_slash(self):
        # turn off gcoin when gtrade and storms are on
        configuredSideEffects = SideEffectBuilder(1, {
            'toggle_gcoin': True,
            'toggle_gtrade': True,
            'toggle_storms': True,
        })
        config_queries.getServerValue = MagicMock(side_effect = configuredSideEffects.side_effect)
        GBotFirebaseService.set = MagicMock()
        self.interaction.send = AsyncMock()
        await self.config.toggleSlash(self.interaction, "gcoin")
        GBotFirebaseService.set.assert_any_call(["servers", self.guild.id, "toggle_gcoin"], False)
        GBotFirebaseService.set.assert_any_call(["servers", self.guild.id, "toggle_gtrade"], False)
        GBotFirebaseService.set.assert_any_call(["servers", self.guild.id, "toggle_storms"], False)
        self.interaction.send.assert_called_once_with(f'All GCoin functionality has been disabled. Dependents disabled: GTrade Storms')

        # turn on gtrade when gcoin is off
        configuredSideEffects = SideEffectBuilder(1, {
            'toggle_gcoin': False,
            'toggle_gtrade': False,
        })
        config_queries.getServerValue = MagicMock(side_effect = configuredSideEffects.side_effect)
        GBotFirebaseService.set = MagicMock()
        self.interaction.send = AsyncMock()
        await self.config.toggleSlash(self.interaction, "gtrade")
        GBotFirebaseService.set.assert_any_call(["servers", self.guild.id, "toggle_gcoin"], True)
        GBotFirebaseService.set.assert_any_call(["servers", self.guild.id, "toggle_gtrade"], True)
        self.interaction.send.assert_called_once_with(f'All GTrade functionality has been enabled. Dependencies enabled: GCoin')

        # turn on storms when gcoin is off
        configuredSideEffects = SideEffectBuilder(1, {
            'toggle_gcoin': False,
            'toggle_storms': False,
        })
        config_queries.getServerValue = MagicMock(side_effect = configuredSideEffects.side_effect)
        GBotFirebaseService.set = MagicMock()
        self.interaction.send = AsyncMock()
        await self.config.toggleSlash(self.interaction, "storms")
        GBotFirebaseService.set.assert_any_call(["servers", self.guild.id, "toggle_gcoin"], True)
        GBotFirebaseService.set.assert_any_call(["servers", self.guild.id, "toggle_storms"], True)
        self.interaction.send.assert_called_once_with(f'All Storms functionality has been enabled. Dependencies enabled: GCoin')

if __name__ == "__main__":
    unittest.main()