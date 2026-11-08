#region IMPORTS
import unittest
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import nextcord
from nextcord.ext import commands
from nextcord.ext.commands.context import Context

from GBotDiscord.src import strings
from GBotDiscord.src.agent import agent_queries
from GBotDiscord.src.help import guides
from GBotDiscord.src.config import config_queries
from GBotDiscord.src.config.config_cog import Config
from GBotDiscord.src.exceptions import NotSubscribed
from GBotDiscord.src.gcoin.gcoin_cog import GCoin
from GBotDiscord.src.gtrade.gtrade_cog import GTrade
from GBotDiscord.src.help import help_cog
from GBotDiscord.src.agent.agent_cog import Agent
from GBotDiscord.src.help.help_cog import FEATURES, GBotHelpCommand, Help
from GBotDiscord.src.hype.hype_cog import Hype
from GBotDiscord.src.music.music_cog import Music
from GBotDiscord.src.patreon.patreon_cog import Patreon
from GBotDiscord.src.presentation import BRAND_COLOR, ERROR_COLOR, WARNING_COLOR
from GBotDiscord.src.properties import GBotPropertiesManager
from GBotDiscord.src.storms.storms_cog import Storms
from GBotDiscord.src.whodis.whodis_cog import WhoDis
#endregion

# to run this test suite:
#   - execute the following command from the GBot directory: python -m unittest GBotDiscord/test/help/help_test.py
#   - or use the "Python: Current File" run configuration to run help_test.py
#   - or use the "Python: Current File" run configuration to run tests.py to run all test suites
class TestHelp(unittest.IsolatedAsyncioTestCase):

    @classmethod
    def setUpClass(self):
        print('\nExecuting help unit tests...\n')

    @classmethod
    def tearDownClass(self):
        print('\n\nCompleted help unit tests.\n')

    agentConfig = {}

    def setUp(self):
        GBotPropertiesManager.SLASH_COMMAND_TEST_GUILDS = []
        GBotPropertiesManager.GBOT_VERSION = '8.0'
        GBotPropertiesManager.PATREON_GUILD_ID = 10
        GBotPropertiesManager.PATREON_URL = 'https://patreon.example'
        self.client = commands.Bot(command_prefix = '.', intents = nextcord.Intents.all())
        for cog in (Agent, Config, GCoin, GTrade, Hype, Music, Patreon, Storms, WhoDis):
            self.client.add_cog(cog(self.client))
        self.guild = Mock()
        self.guild.id = 99
        self.author = Mock()
        self.off = set()
        self.values = {'prefix': '!'}
        def serverValue(serverId, key):
            if key in self.values:
                return self.values[key]
            return key not in self.off
        patches = [
            patch.object(config_queries, 'getServerValue', side_effect = serverValue),
            patch.object(agent_queries, 'getServerConfig', side_effect = lambda serverId: self.agentConfig),
            patch.object(guides, 'guideFor', side_effect = lambda name: f'How {name} works.'),
            patch('GBotDiscord.src.help.help_cog.predicates.ensureSubscribed', new = AsyncMock()),
            patch('GBotDiscord.src.help.help_cog.utils.isUserAdminOrOwner', return_value = True),
        ]
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    def _isAdmin(self, value):
        patcher = patch('GBotDiscord.src.help.help_cog.utils.isUserAdminOrOwner', return_value = value)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _fieldNames(self, embed):
        return [field.name for field in embed.fields]

    def _field(self, embed, name):
        return next(field for field in embed.fields if field.name == name).value

    #region overview
    def test_every_feature_names_a_real_command_and_toggle(self):
        # a group of commands, or, for a feature with only one, that command
        for feature in FEATURES:
            with self.subTest(feature = feature.name):
                self.assertIsNotNone(self.client.get_command(feature.group))
                self.assertEqual(isinstance(self.client.get_command(feature.group), commands.Group), feature.name not in ('Hype', 'Config', 'Agent'))
                if feature.toggle is not None:
                    self.assertIn(feature.toggle, strings.FEATURE_NAMES)

    async def test_overview_lists_every_feature_for_an_admin(self):
        embed = await help_cog.overviewEmbed(self.client, self.guild, self.author)
        self.assertEqual(embed.color, BRAND_COLOR)
        self.assertEqual(self._fieldNames(embed), [feature.heading for feature in FEATURES])
        self.assertIn('`play`', self._field(embed, '🎵 Music'))

    # the point of owning help: stock help listed commands the caller would then be refused
    async def test_overview_moves_a_turned_off_feature_out_of_the_list(self):
        self.off = {'toggle_gtrade', 'toggle_music'}
        embed = await help_cog.overviewEmbed(self.client, self.guild, self.author)
        names = self._fieldNames(embed)
        self.assertNotIn('🎵 Music', names)
        self.assertNotIn('🏪 GTrade', names)
        turnedOff = self._field(embed, 'Turned off here')
        self.assertIn('GTrade, Music', turnedOff)
        self.assertIn('`/config`', turnedOff)

    async def test_overview_hides_admin_features_from_everyone_else(self):
        self._isAdmin(False)
        self.off = {'toggle_hype'}
        embed = await help_cog.overviewEmbed(self.client, self.guild, self.author)
        names = self._fieldNames(embed)
        self.assertNotIn('⚙️ Config', names)
        self.assertNotIn('↩️ Hype', names)
        # not reported as off either, as there is nothing they could do with it
        self.assertNotIn('Turned off here', names)

    async def test_a_feature_with_one_command_lists_just_that_command(self):
        hype = next(feature for feature in FEATURES if feature.name == 'Hype')
        overview = await help_cog.overviewEmbed(self.client, self.guild, self.author)
        self.assertEqual(self._field(overview, hype.heading), '`/hype`')
        detail = help_cog.featureEmbed(self.client, hype, self.guild)
        self.assertEqual([field.name for field in detail.fields][1:], ['/hype'])
        self.assertIn('[hype|hy]', detail.fields[1].value)

    async def test_feature_detail_starts_with_how_it_works(self):
        music = next(feature for feature in FEATURES if feature.name == 'Music')
        embed = help_cog.featureEmbed(self.client, music, self.guild)
        self.assertEqual((embed.fields[0].name, embed.fields[0].value), ('📖 How it works', 'How Music works.'))

    async def test_overview_offers_members_agent_memory_only_when_they_can_use_it(self):
        self._isAdmin(False)
        agent = '🤖 Agent'
        self.assertNotIn(agent, self._fieldNames(await help_cog.overviewEmbed(self.client, self.guild, self.author)))
        self.agentConfig = {'memoryAccess': 'everyone'}
        embed = await help_cog.overviewEmbed(self.client, self.guild, self.author)
        field = next(field for field in embed.fields if field.name == agent)
        self.assertEqual(field.value, '`/agent` Your memories')
        self.off = {'toggle_agent'}
        self.assertNotIn(agent, self._fieldNames(await help_cog.overviewEmbed(self.client, self.guild, self.author)))

    async def test_overview_in_a_private_message_has_no_server_features(self):
        embed = await help_cog.overviewEmbed(self.client, None, self.author)
        names = self._fieldNames(embed)
        self.assertIn('💰 GCoin', names)
        self.assertNotIn('⚙️ Config', names)
        self.assertNotIn('Turned off here', names)
        self.assertNotIn('Prefix commands', names)

    async def test_overview_mentions_when_prefix_commands_are_off(self):
        self.off = {'toggle_legacy_prefix_commands'}
        embed = await help_cog.overviewEmbed(self.client, self.guild, self.author)
        self.assertIn('slash commands', self._field(embed, 'Prefix commands'))

    async def test_overview_offers_patreon_only_in_the_patreon_server(self):
        self.assertNotIn('⭐ Patreon', self._fieldNames(await help_cog.overviewEmbed(self.client, self.guild, self.author)))
        self.guild.id = 10
        self.assertIn('⭐ Patreon', self._fieldNames(await help_cog.overviewEmbed(self.client, self.guild, self.author)))

    async def test_overview_when_not_subscribed_says_how_to_subscribe(self):
        with patch('GBotDiscord.src.help.help_cog.predicates.ensureSubscribed', new = AsyncMock(side_effect = NotSubscribed('x'))):
            embed = await help_cog.overviewEmbed(self.client, self.guild, self.author)
        self.assertEqual(embed.color, WARNING_COLOR)
        self.assertIn('https://patreon.example', embed.description)
        self.assertEqual(embed.fields, [])
    #endregion

    #region feature and command detail
    def test_feature_detail_shows_slash_and_prefix_forms(self):
        music = next(feature for feature in FEATURES if feature.name == 'Music')
        embed = help_cog.featureEmbed(self.client, music, self.guild)
        self.assertEqual(embed.footer.text, 'GBot 8.0 • Music')
        value = self._field(embed, '/music play')
        self.assertIn(strings.MUSIC_PLAY_BRIEF, value)
        # the server's own prefix and every alias, in the form the README documents
        self.assertIn('`![music|m] [play|p] [args...]`', value)

    def test_feature_detail_leaves_out_prefix_forms_when_they_are_off(self):
        self.off = {'toggle_legacy_prefix_commands'}
        music = next(feature for feature in FEATURES if feature.name == 'Music')
        value = self._field(help_cog.featureEmbed(self.client, music, self.guild), '/music play')
        self.assertEqual(value, strings.MUSIC_PLAY_BRIEF)

    def test_feature_detail_says_when_it_is_off(self):
        self.off = {'toggle_music'}
        music = next(feature for feature in FEATURES if feature.name == 'Music')
        embed = help_cog.featureEmbed(self.client, music, self.guild)
        self.assertEqual(embed.color, WARNING_COLOR)
        self.assertIn('`/config`', embed.description)

    def test_feature_detail_in_a_private_message_uses_the_default_prefix(self):
        gcoin = next(feature for feature in FEATURES if feature.name == 'GCoin')
        self.assertIn('`.[gcoin|gc]', self._field(help_cog.featureEmbed(self.client, gcoin, None), '/gcoin wallet'))

    def test_command_detail_for_a_subcommand(self):
        embed = help_cog.commandEmbed(self.client.get_command('music play'), self.guild)
        self.assertEqual(embed.title, '/music play')
        self.assertEqual(embed.description, strings.MUSIC_PLAY_DESCRIPTION)
        self.assertEqual(embed.footer.text, 'GBot 8.0 • Music')
        self.assertEqual(self._field(embed, 'Prefix command'), '`![music|m] [play|p] [args...]`')

    def test_command_detail_for_a_top_level_command_without_prefix_commands(self):
        self.off = {'toggle_legacy_prefix_commands'}
        embed = help_cog.commandEmbed(self.client.get_command('patreon'), self.guild)
        self.assertEqual(embed.title, '/patreon')
        self.assertEqual(embed.fields, [])

    def test_describeCommand_handles_a_command_without_a_brief_or_arguments(self):
        command = Mock(brief = None, aliases = [], signature = '')
        command.name = 'x'
        command.parent = None
        self.assertEqual(help_cog.describeCommand(command, '.', True), '\n`.[x]`')
        command.brief = 'no dash'
        self.assertEqual(help_cog.describeCommand(command, '.', False), 'no dash')
    #endregion

    #region GBotHelpCommand
    def _helpCommand(self):
        ctx = Mock(spec = Context)
        ctx.send = AsyncMock()
        ctx.bot = self.client
        ctx.guild = self.guild
        ctx.author = self.author
        command = GBotHelpCommand()
        command.context = ctx
        return command, ctx

    async def test_bot_help_sends_the_overview(self):
        command, ctx = self._helpCommand()
        await command.send_bot_help({})
        self.assertEqual(ctx.send.await_args.kwargs['embed'].title, strings.HELP_TITLE)

    # .config, and every other bare group, answers with this through ctx.send_help
    async def test_group_help_sends_the_feature_detail(self):
        command, ctx = self._helpCommand()
        await command.send_group_help(self.client.get_command('config'))
        self.assertEqual(ctx.send.await_args.kwargs['embed'].title, '⚙️ Config')

    async def test_cog_help_sends_the_feature_detail(self):
        command, ctx = self._helpCommand()
        await command.send_cog_help(self.client.get_cog('Music'))
        self.assertEqual(ctx.send.await_args.kwargs['embed'].title, '🎵 Music')

    async def test_cog_help_for_a_cog_without_a_feature_falls_back_to_the_overview(self):
        command, ctx = self._helpCommand()
        await command.send_cog_help(self.client.get_cog('Patreon'))
        self.assertEqual(ctx.send.await_args.kwargs['embed'].title, strings.HELP_TITLE)

    async def test_command_help_sends_the_command_detail(self):
        command, ctx = self._helpCommand()
        await command.send_command_help(self.client.get_command('music play'))
        self.assertEqual(ctx.send.await_args.kwargs['embed'].title, '/music play')

    async def test_unknown_command_is_an_error_card(self):
        command, ctx = self._helpCommand()
        await command.send_error_message('No command called "x" found.')
        embed = ctx.send.await_args.kwargs['embed']
        self.assertEqual(embed.color, ERROR_COLOR)
        self.assertIn('`/help`', embed.description)
    #endregion

    #region Help cog
    def _interaction(self, guild = None):
        interaction = Mock(spec = nextcord.Interaction)
        interaction.send = AsyncMock()
        interaction.guild = guild
        interaction.user = self.author
        return interaction

    async def test_slash_help_is_private_overview_by_default(self):
        cog = Help(self.client)
        interaction = self._interaction(self.guild)
        await cog.helpSlash(interaction, None)
        kwargs = interaction.send.await_args.kwargs
        self.assertTrue(kwargs['ephemeral'])
        self.assertEqual(kwargs['embed'].title, strings.HELP_TITLE)

    async def test_slash_help_for_a_feature(self):
        cog = Help(self.client)
        interaction = self._interaction(self.guild)
        await cog.helpSlash(interaction, 'GCoin')
        self.assertEqual(interaction.send.await_args.kwargs['embed'].title, '💰 GCoin')

    def test_setup_replaces_the_stock_help_and_adds_the_cog(self):
        client = MagicMock()
        help_cog.setup(client)
        self.assertIsInstance(client.help_command, GBotHelpCommand)
        self.assertIsInstance(client.add_cog.call_args.args[0], Help)
    #endregion
