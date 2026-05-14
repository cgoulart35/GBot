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

    async def test_on_ready_no_upgrade_needed(self):
        # server already at current version - upgradeServerValues should not be called
        utils.filterGuildsForInstance = MagicMock(return_value = {
            "012345678910111213": {"version": "7.0"}
        })
        config_queries.upgradeServerValues = MagicMock()
        await self.config.on_ready()
        config_queries.upgradeServerValues.assert_not_called()

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

    async def test_config_empty_optional_fields(self):
        # roles and channels not in serverConfig - all show as `empty`
        config_queries.getAllServerValues = MagicMock(return_value = {
            "prefix": ".",
            "toggle_music": False,
            "toggle_gcoin": False,
            "toggle_gtrade": False,
            "toggle_hype": False,
            "toggle_storms": False,
            "toggle_who_dis": False,
            "toggle_legacy_prefix_commands": False,
            "version": "7.0"
        })
        pagination.FieldPageSource.__init__ = MagicMock(return_value = None)
        try:
            await self.config.config(self.config, self.ctx)
        except:
            actual_fields = pagination.FieldPageSource.__init__.call_args.args[0]
            # find each optional row and verify it shows '`empty`'
            field_map = dict(actual_fields)
            self.assertEqual(field_map["Admin Role"], "`empty`")
            self.assertEqual(field_map["Who Dis Role"], "`empty`")
            self.assertEqual(field_map["Admin Channel"], "`empty`")
            self.assertEqual(field_map["Storms Channel"], "`empty`")

    async def test_config_no_guild_icon(self):
        self.guild.icon = None
        config_queries.getAllServerValues = MagicMock(return_value = {
            "prefix": ".",
            "toggle_music": False, "toggle_gcoin": False, "toggle_gtrade": False,
            "toggle_hype": False, "toggle_storms": False, "toggle_who_dis": False,
            "toggle_legacy_prefix_commands": False, "version": "7.0"
        })
        pagination.FieldPageSource.__init__ = MagicMock(return_value = None)
        try:
            await self.config.config(self.config, self.ctx)
        except:
            # second positional arg (thumbnailUrl) should be None when guild.icon is None
            self.assertIsNone(pagination.FieldPageSource.__init__.call_args.args[1])

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

    async def test_role_who_dis_spellings(self):
        # all three text spellings for who_dis map to the same db field
        role = Mock()
        role.id = 12345
        role.mention = "role mention"
        for spelling in ('who dis', 'whoDis', 'whodis'):
            with self.subTest(spelling = spelling):
                GBotFirebaseService.set = MagicMock()
                self.ctx.send = AsyncMock()
                await self.config.role(self.config, self.ctx, spelling, role)
                GBotFirebaseService.set.assert_called_once_with(["servers", self.guild.id, "role_who_dis"], "12345")
                self.ctx.send.assert_called_once_with(f'Who Dis role set to: {role.mention}')

    async def test_role_bad_argument(self):
        from nextcord.ext.commands.errors import BadArgument
        role = Mock()
        with self.assertRaises(BadArgument):
            await self.config.role(self.config, self.ctx, "nonsense", role)

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

    async def test_channel_bad_argument(self):
        from nextcord.ext.commands.errors import BadArgument
        channel = Mock()
        with self.assertRaises(BadArgument):
            await self.config.channel(self.config, self.ctx, "nonsense", channel)

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

    async def test_toggle_all_feature_type_variants(self):
        # every feature_type spelling (text + slash emoji) maps to the correct db field
        cases = [
            ('music', 'toggle_music'),
            ('🎵 Music', 'toggle_music'),
            ('hype', 'toggle_hype'),
            ('↩ Hype', 'toggle_hype'),
            ('legacy prefix commands', 'toggle_legacy_prefix_commands'),
            ('⚙ Legacy Prefix Commands', 'toggle_legacy_prefix_commands'),
            ('whoDis', 'toggle_who_dis'),
            ('whodis', 'toggle_who_dis'),
            ('who dis', 'toggle_who_dis'),
            ('❓ Who Dis', 'toggle_who_dis'),
            ('🏪 GTrade', 'toggle_gtrade'),
            ('💰 GCoin', 'toggle_gcoin'),
            ('⚡ Storms', 'toggle_storms'),
        ]
        for feature_type, expected_db_switch in cases:
            with self.subTest(feature_type = feature_type):
                # current state is False everywhere so toggle turns it ON
                config_queries.getServerValue = MagicMock(return_value = False)
                GBotFirebaseService.set = MagicMock()
                self.ctx.send = AsyncMock()
                await self.config.toggle(self.config, self.ctx, feature_type)
                GBotFirebaseService.set.assert_any_call(["servers", self.guild.id, expected_db_switch], True)

    async def test_toggle_bad_argument(self):
        from nextcord.ext.commands.errors import BadArgument
        with self.assertRaises(BadArgument):
            await self.config.toggle(self.config, self.ctx, "nonsense")

    async def test_toggle_music_off_disconnects_voice(self):
        # toggling music OFF via the 'music' text spelling tears down any active voice client
        config_queries.getServerValue = MagicMock(return_value = True)  # currently enabled
        GBotFirebaseService.set = MagicMock()
        self.ctx.send = AsyncMock()
        music_cog = Mock()
        music_cog.disconnectAndClearQueue = AsyncMock()
        self.client.get_cog = MagicMock(return_value = music_cog)
        await self.config.toggle(self.config, self.ctx, 'music')
        music_cog.disconnectAndClearQueue.assert_called_once_with(str(self.guild.id))

    async def test_toggle_music_off_via_slash_emoji_skips_disconnect_BUG(self):
        # BUG: commonToggle's disconnect check on line 339 reads `if feature_type == 'music':`,
        # which only matches the prefix spelling — '🎵 Music' from the slash bypasses it.
        # Result: voice client stays connected after a slash toggle-off. When this is fixed
        # (likely to `if dbSwitch == 'toggle_music':`), flip the assertion to assert_called_once.
        config_queries.getServerValue = MagicMock(return_value = True)
        GBotFirebaseService.set = MagicMock()
        self.interaction.send = AsyncMock()
        music_cog = Mock()
        music_cog.disconnectAndClearQueue = AsyncMock()
        self.client.get_cog = MagicMock(return_value = music_cog)
        await self.config.toggleSlash(self.interaction, '🎵 Music')
        music_cog.disconnectAndClearQueue.assert_not_called()

    async def test_toggle_dependency_already_enabled_skipped(self):
        # turning gtrade ON when gcoin is already ON — the cog should NOT re-set gcoin
        configuredSideEffects = SideEffectBuilder(1, {
            'toggle_gtrade': False,  # currently off, turning on
            'toggle_gcoin': True,    # dependency already on
        })
        config_queries.getServerValue = MagicMock(side_effect = configuredSideEffects.side_effect)
        GBotFirebaseService.set = MagicMock()
        self.ctx.send = AsyncMock()
        await self.config.toggle(self.config, self.ctx, "gtrade")
        set_calls = [call.args for call in GBotFirebaseService.set.call_args_list]
        self.assertIn((["servers", self.guild.id, "toggle_gtrade"], True), set_calls)
        self.assertNotIn((["servers", self.guild.id, "toggle_gcoin"], True), set_calls)
        # no 'Dependencies enabled:' suffix since nothing needed enabling
        self.ctx.send.assert_called_once_with('All GTrade functionality has been enabled.')

    async def test_toggle_dependent_already_disabled_skipped(self):
        # turning gcoin OFF when both dependents (gtrade, storms) are already off — no cascade
        # NOTE on a SEPARATE bug: gcoin's dependentsDbSwitches list omits 'toggle_who_dis',
        # so toggling gcoin off does not cascade-disable Who Dis even though Who Dis declares
        # gcoin as a dependency (line 301). When fixed, add toggle_who_dis to the side_effect
        # map and assert it gets disabled.
        configuredSideEffects = SideEffectBuilder(1, {
            'toggle_gcoin': True,    # currently on, turning off
            'toggle_gtrade': False,  # dependent already off
            'toggle_storms': False,  # dependent already off
        })
        config_queries.getServerValue = MagicMock(side_effect = configuredSideEffects.side_effect)
        GBotFirebaseService.set = MagicMock()
        self.ctx.send = AsyncMock()
        await self.config.toggle(self.config, self.ctx, "gcoin")
        set_calls = [call.args for call in GBotFirebaseService.set.call_args_list]
        self.assertIn((["servers", self.guild.id, "toggle_gcoin"], False), set_calls)
        self.assertNotIn((["servers", self.guild.id, "toggle_gtrade"], False), set_calls)
        self.assertNotIn((["servers", self.guild.id, "toggle_storms"], False), set_calls)
        self.ctx.send.assert_called_once_with('All GCoin functionality has been disabled.')

    def test_setup_adds_cog(self):
        from GBotDiscord.src.config import config_cog
        client = MagicMock()
        config_cog.setup(client)
        client.add_cog.assert_called_once()
        addedCog = client.add_cog.call_args[0][0]
        self.assertIsInstance(addedCog, Config)

if __name__ == "__main__":
    unittest.main()