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
from GBotDiscord.src.exceptions import NotSubscribed, AccessEnded
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
# ✖️ Close has no label, which nextcord keeps as MISSING
CLOSE = nextcord.utils.MISSING

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
        for cog in (Agent, Config, GCoin, GTrade, Help, Hype, Music, Patreon, Storms, WhoDis):
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

    def press(self, guild = 'default'):
        interaction = Mock(spec = nextcord.Interaction)
        interaction.guild = self.guild if guild == 'default' else guild
        interaction.user = self.author
        interaction.response = Mock(defer = AsyncMock(), edit_message = AsyncMock())
        interaction.send = AsyncMock(return_value = Mock(edit = AsyncMock()))
        interaction.data = {}
        return interaction

    async def openHelp(self, guild = 'default', feature = None):
        interaction = self.press(guild)
        await help_cog.openHelp(self.client, interaction, self.author, feature)
        kwargs = interaction.send.await_args.kwargs
        return kwargs['embed'], kwargs.get('view'), interaction

    def labels(self, view):
        return [item.label for item in view.children if isinstance(item, nextcord.ui.Button)]

    #region the front door
    def test_every_feature_names_a_real_command_toggle_and_cog(self):
        for feature in FEATURES:
            with self.subTest(feature = feature.name):
                self.assertIsInstance(self.client.get_command(feature.command), commands.Command)
                self.assertIsNotNone(self.client.get_cog(feature.cog))
                if feature.toggle is not None:
                    self.assertIn(feature.toggle, strings.FEATURE_NAMES)
        self.assertIs(help_cog.featureNamed('music'), help_cog.featureNamed('Music'))
        self.assertIsNone(help_cog.featureNamed('nothing'))

    async def test_an_admin_sees_every_feature_with_a_button_for_each(self):
        embed, view, interaction = await self.openHelp()
        self.assertTrue(interaction.send.await_args.kwargs['ephemeral'])
        self.assertEqual(embed.color, BRAND_COLOR)
        self.assertEqual(self._fieldNames(embed), [feature.heading for feature in FEATURES])
        self.assertEqual(self._field(embed, '🎵 Music'), f'`/music` {strings.MUSIC_BRIEF}')
        self.assertEqual(self.labels(view), [feature.name for feature in FEATURES] + ['Ranking', CLOSE])
        select = next(item for item in view.children if isinstance(item, nextcord.ui.Select))
        self.assertEqual([option.value for option in select.options], [feature.name for feature in FEATURES])
        for row in view.to_components():
            self.assertLessEqual(len(row['components']), 5)

    async def test_members_are_not_offered_admin_features(self):
        self._isAdmin(False)
        embed, view, _ = await self.openHelp()
        self.assertNotIn('⚙️ Config', self._fieldNames(embed))
        self.assertNotIn('Hype', self.labels(view))
        self.assertNotIn('Agent', self.labels(view))
        # except the agent's memories, where members may use them
        self.agentConfig = {'memoryAccess': 'everyone'}
        _, view, _ = await self.openHelp()
        self.assertIn('Agent', self.labels(view))
        self.off = {'toggle_agent'}
        _, view, _ = await self.openHelp()
        self.assertNotIn('Agent', self.labels(view))

    async def test_features_turned_off_are_listed_but_not_opened(self):
        self.off = {'toggle_music', 'toggle_gtrade'}
        embed, view, _ = await self.openHelp()
        self.assertEqual(self._field(embed, 'Turned off here'), 'GTrade, Music\nAn admin can turn these on in `/config`.')
        self.assertNotIn('Music', self.labels(view))
        # still explained in the dropdown, as someone may want to ask an admin for it
        select = next(item for item in view.children if isinstance(item, nextcord.ui.Select))
        self.assertIn('Music', [option.value for option in select.options])

    async def test_prefix_commands_off_and_the_patreon_server(self):
        self.off = {'toggle_legacy_prefix_commands'}
        self.guild.id = GBotPropertiesManager.PATREON_GUILD_ID
        embed, _, _ = await self.openHelp()
        self.assertIn('⭐ Patreon', self._fieldNames(embed))
        self.assertIn('Turned off here, so use the slash commands', self._field(embed, 'Prefix commands'))

    async def test_in_a_private_message_only_what_works_there(self):
        embed, view, _ = await self.openHelp(guild = None)
        self.assertEqual(self.labels(view), ['GCoin', 'GTrade', 'Who Dis', 'Ranking', CLOSE])
        self.assertNotIn('Turned off here', self._fieldNames(embed))

    async def test_someone_not_subscribed_is_told_how_to_be(self):
        with patch('GBotDiscord.src.help.help_cog.predicates.ensureSubscribed', AsyncMock(side_effect = NotSubscribed('x'))):
            embed, view, _ = await self.openHelp()
        # the same red refusal as every other command
        self.assertEqual(embed.color, ERROR_COLOR)
        self.assertIn('https://patreon.example', embed.description)
        self.assertEqual(view.children[0].url, 'https://patreon.example')

    async def test_a_server_whose_trial_ended_is_told_so(self):
        with patch('GBotDiscord.src.help.help_cog.predicates.ensureSubscribed', AsyncMock(side_effect = AccessEnded('x', 77))):
            embed, view, _ = await self.openHelp()
        self.assertEqual(embed.color, ERROR_COLOR)
        self.assertIn("GBot's free trial in this server has ended. To keep GBot, subscribe on Patreon", embed.description)
        self.assertIn('`77`', embed.description)
        self.assertEqual(view.children[0].url, 'https://patreon.example')

    async def test_nothing_to_show_has_no_dropdown(self):
        card = help_cog.HelpCard(self.client, None, [], [])
        await card.render(self.author)
        # only ✖️ Close, which every card has
        self.assertEqual(self.labels(card), [CLOSE])
        self.assertEqual(len(card.children), 1)
    #endregion

    #region a feature's page
    async def test_picking_a_feature_shows_how_it_works_with_back_and_open(self):
        _, view, _ = await self.openHelp()
        select = next(item for item in view.children if isinstance(item, nextcord.ui.Select))
        interaction = self.press()
        interaction.data = {'values': ['Music']}
        await select.callback(interaction)
        embed = interaction.response.edit_message.await_args.kwargs['embed']
        self.assertEqual(embed.title, '🎵 Music')
        self.assertEqual(embed.footer.text, 'GBot 8.0 • Music')
        self.assertEqual(self._field(embed, '📖 How it works'), 'How Music works.')
        self.assertEqual(self._field(embed, '/music [search]'), f'{strings.MUSIC_BRIEF}\n`![music|m] [search...]`')
        self.assertEqual(self.labels(view), ['Back', 'Open Music', CLOSE])
        await view.children[0].callback(interaction)
        self.assertEqual(interaction.response.edit_message.await_args.kwargs['embed'].title, strings.HELP_TITLE)

    async def test_a_feature_page_without_prefix_commands_or_turned_off(self):
        self.off = {'toggle_legacy_prefix_commands', 'toggle_music'}
        embed, view, _ = await self.openHelp(feature = 'Music')
        self.assertEqual(embed.color, WARNING_COLOR)
        self.assertIn('`/config`', embed.description)
        self.assertEqual(self._field(embed, '/music [search]'), strings.MUSIC_BRIEF)
        self.assertEqual(self.labels(view), ['Back', CLOSE])

    async def test_a_feature_page_in_a_private_message_uses_the_default_prefix(self):
        embed, _, _ = await self.openHelp(guild = None, feature = 'GCoin')
        self.assertIn('`.[gcoin|gc] [user]`', self._field(embed, '/gcoin [user]'))
        embed = help_cog.featureEmbed(self.client, help_cog.featureNamed('Config'), None)
        self.assertEqual(self._field(embed, '/config'), f'{strings.CONFIG_BRIEF}\n`.[config|c]`')
    #endregion

    #region opening a feature's card
    async def test_a_button_opens_the_features_card_checked_as_its_command(self):
        _, view, _ = await self.openHelp()
        buttons = {item.label: item for item in view.children if isinstance(item, nextcord.ui.Button)}
        expectations = {
            'Agent': ('Agent', 'openCard', 'toggle_agent', False, False),
            'Config': ('Config', 'openCard', None, True, False),
            'GCoin': ('GCoin', 'commonWallet', 'toggle_gcoin', False, True),
            'GTrade': ('GTrade', 'openItems', 'toggle_gtrade', False, True),
            'Hype': ('Hype', 'openCard', 'toggle_hype', True, False),
            'Music': ('Music', 'commonMusic', 'toggle_music', False, False),
            'Storms': ('Storms', 'commonStatus', 'toggle_storms', False, False),
            'Who Dis': ('WhoDis', 'openCard', 'toggle_who_dis', False, True)}
        for label, (cogName, method, toggle, admin, inPrivate) in expectations.items():
            with self.subTest(feature = label), patch.object(self.client.get_cog(cogName), method, AsyncMock()) as opener, patch('GBotDiscord.src.help.help_cog.predicates.recheck', AsyncMock()) as recheck:
                interaction = self.press()
                await buttons[label].callback(interaction)
                interaction.response.defer.assert_awaited_once_with(ephemeral = True)
                recheck.assert_awaited_once_with(interaction, feature = toggle, admin = admin, privateMessagesAllowed = inPrivate)
                opener.assert_awaited_once()
                self.assertIs(opener.await_args.args[0], interaction)

    async def test_the_ranking_has_a_button_of_its_own_while_gcoin_is_on(self):
        _, view, _ = await self.openHelp()
        ranking = next(item for item in view.children if getattr(item, 'label', None) == 'Ranking')
        with patch.object(self.client.get_cog('GCoin'), 'openRanking', AsyncMock()) as openRanking, patch('GBotDiscord.src.help.help_cog.predicates.recheck', AsyncMock()) as recheck:
            interaction = self.press()
            await ranking.callback(interaction)
        interaction.response.defer.assert_awaited_once_with(ephemeral = True)
        recheck.assert_awaited_once_with(interaction, feature = 'toggle_gcoin', privateMessagesAllowed = True)
        openRanking.assert_awaited_once_with(interaction)
        self.off = {'toggle_gcoin'}
        _, view, _ = await self.openHelp()
        self.assertNotIn('Ranking', self.labels(view))
    #endregion

    #region the prefix command
    def _helpCommand(self):
        command = GBotHelpCommand()
        ctx = Mock(spec = Context)
        ctx.bot = self.client
        ctx.guild = self.guild
        ctx.author = self.author
        ctx.send = AsyncMock(return_value = Mock(edit = AsyncMock()))
        command.context = ctx
        return command, ctx

    async def test_dot_help_opens_the_front_door_or_a_features_page(self):
        command, ctx = self._helpCommand()
        await command.send_bot_help(None)
        self.assertEqual(ctx.send.await_args.kwargs['embed'].title, strings.HELP_TITLE)
        # public, as a prefix command can't reply privately; its buttons open cards privately
        self.assertNotIn('ephemeral', ctx.send.await_args.kwargs)
        await command.send_command_help(self.client.get_command('music'))
        self.assertEqual(ctx.send.await_args.kwargs['embed'].title, '🎵 Music')
        await command.send_cog_help(self.client.get_cog('Storms'))
        self.assertEqual(ctx.send.await_args.kwargs['embed'].title, '🌧️ Storms')
        await command.send_cog_help(self.client.get_cog('Patreon'))
        self.assertEqual(ctx.send.await_args.kwargs['embed'].title, strings.HELP_TITLE)
        await command.send_command_help(self.client.get_command('patreon'))
        self.assertEqual(ctx.send.await_args.kwargs['embed'].title, strings.HELP_TITLE)

    async def test_unknown_command_is_an_error_card(self):
        command, ctx = self._helpCommand()
        await command.send_error_message('No command called "nope" found.')
        embed = ctx.send.await_args.kwargs['embed']
        self.assertEqual(embed.color, ERROR_COLOR)
        self.assertIn('/help', embed.description)

    async def test_the_slash_command(self):
        cog = self.client.get_cog('Help')
        with patch.object(help_cog, 'openHelp', AsyncMock()) as openHelp:
            interaction = self.press()
            await cog.helpSlash(interaction, 'Music')
        openHelp.assert_awaited_once_with(self.client, interaction, interaction.user, 'Music')

    def test_setup_replaces_the_help_command(self):
        client = MagicMock()
        help_cog.setup(client)
        self.assertIsInstance(client.help_command, GBotHelpCommand)
        client.add_cog.assert_called_once()
    #endregion

if __name__ == '__main__':
    unittest.main()
