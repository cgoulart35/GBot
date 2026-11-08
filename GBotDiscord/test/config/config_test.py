#region IMPORTS
import threading
import unittest
from unittest.mock import MagicMock, Mock, AsyncMock, patch
import nextcord
from nextcord.ext import commands
from nextcord.ext.commands.context import Context

from GBotDiscord.test.utils import SideEffectBuilder
from GBotDiscord.src import utils
from GBotDiscord.src import pagination
from GBotDiscord.src.config import config_queries
from GBotDiscord.src.config import config_cog
from GBotDiscord.src.config.config_cog import Config, ConfigCard
from GBotDiscord.src.properties import GBotPropertiesManager
from GBotDiscord.src.firebase import GBotFirebaseService
from GBotDiscord.src import presentation
#endregion

config_queries_upgrade = config_queries.upgradeServerValues

# to run this test suite:
#   - execute the following command from the GBot directory: python -m unittest GBotDiscord/test/config/config_test.py
#   - or use the "Python: Current File" run configuration to run config_test.py
#   - or use the "Python: Current File" run configuration to run tests.py to run all test suites
def named(name):
    # Mock(name = ...) names the mock itself, so this is how one gets a name attribute
    thing = Mock()
    thing.name = name
    return thing

class TestConfig(unittest.IsolatedAsyncioTestCase):

    @classmethod
    def setUpClass(self):
        print("\nExecuting config unit tests...\n")

    @classmethod
    def tearDownClass(self):
        print("\n\nCompleted config unit tests.\n")

    def setUp(self):
        GBotPropertiesManager.GBOT_VERSION = "8.0"

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
            "version": "8.0",
            "prefix": ".",
            "toggle_music": False,
            "toggle_gcoin": False,
            "toggle_gtrade": False,
            "toggle_hype": False,
            "toggle_storms": False,
            "toggle_who_dis": False,
            "toggle_agent": False,
            "toggle_legacy_prefix_commands": False
        }

        GBotFirebaseService.set = MagicMock()
        with patch('GBotDiscord.src.config.config_cog.presentation.sendWelcome', new = AsyncMock()) as sendWelcome:
            await self.config.on_guild_join(self.guild)
        sendWelcome.assert_awaited_once_with(self.guild)
        GBotFirebaseService.set.assert_called_once_with(["servers", self.guild.id], defaultConfig)

    async def test_on_guild_remove(self):
        GBotFirebaseService.remove = MagicMock()
        await self.config.on_guild_remove(self.guild)
        GBotFirebaseService.remove.assert_any_call(["servers", self.guild.id])
        # a server's reports go with the rest of its data
        GBotFirebaseService.remove.assert_any_call(["reports", self.guild.id])

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
        GBotFirebaseService.set.assert_any_call(["servers", "012345678910111213", "version"], "8.0")
        GBotFirebaseService.set.assert_any_call(["servers", "012345678910111213", "toggle_music"], False)
        GBotFirebaseService.set.assert_any_call(["servers", "012345678910111213", "toggle_gcoin"], False)
        GBotFirebaseService.set.assert_any_call(["servers", "012345678910111213", "toggle_gtrade"], False)
        GBotFirebaseService.set.assert_any_call(["servers", "012345678910111213", "toggle_hype"], False)
        GBotFirebaseService.set.assert_any_call(["servers", "012345678910111213", "toggle_storms"], False)
        GBotFirebaseService.set.assert_any_call(["servers", "012345678910111213", "toggle_who_dis"], False)
        GBotFirebaseService.set.assert_any_call(["servers", "012345678910111213", "toggle_legacy_prefix_commands"], False)

    async def test_on_ready_fills_in_a_server_joined_while_offline_and_nothing_else(self):
        # no join event for these, so without this the server has no config at all. An existing
        # entry must never be touched: it could belong to the other bot sharing the database.
        existing = Mock(id = 1)
        joinedOffline = Mock(id = 2)
        self.config.client = Mock(guilds = [existing, joinedOffline])
        config_queries.getAllServers = MagicMock(return_value = {'1': {'version': '8.0'}})
        utils.filterGuildsForInstance = MagicMock(return_value = {})
        config_queries.initServerValues = MagicMock()
        await self.config.on_ready()
        config_queries.initServerValues.assert_called_once_with(2, GBotPropertiesManager.GBOT_VERSION)

    async def test_on_ready_no_servers_in_the_database_at_all(self):
        self.config.client = Mock(guilds = [])
        config_queries.getAllServers = MagicMock(return_value = None)
        utils.filterGuildsForInstance = MagicMock(return_value = {})
        await self.config.on_ready()
        utils.filterGuildsForInstance.assert_called_once_with(self.config.client, {})

    async def test_on_ready_no_upgrade_needed(self):
        # server already at current version - upgradeServerValues should not be called
        utils.filterGuildsForInstance = MagicMock(return_value = {
            "012345678910111213": {"version": "8.0"}
        })
        config_queries.upgradeServerValues = MagicMock()
        await self.config.on_ready()
        config_queries.upgradeServerValues.assert_not_called()

    async def test_a_server_on_the_last_version_gets_upgraded_with_the_agent_field(self):
        # the reason the agent shipped as 8.1: servers only get new fields when the version goes up
        self.config.client = Mock(guilds = [])
        setServerValue = MagicMock()
        with patch.object(GBotPropertiesManager, 'GBOT_VERSION', '8.1'), \
             patch.object(config_queries, 'getAllServers', MagicMock(return_value = {'5': {'version': '8.0'}})), \
             patch.object(config_queries, 'getAllServerValues', MagicMock(return_value = {'version': '8.0'})), \
             patch.object(config_queries, 'upgradeServerValues', config_queries_upgrade), \
             patch.object(config_queries, 'setServerValue', setServerValue), \
             patch.object(utils, 'filterGuildsForInstance', MagicMock(side_effect = lambda client, servers: servers)):
            await self.config.on_ready()
        setServerValue.assert_any_call('5', 'toggle_agent', False)

    FULL_CONFIG = {
        "channel_admin": "111",
        "channel_storms": "222",
        "prefix": ".",
        "role_admin": "333",
        "role_who_dis": "444",
        "toggle_gcoin": True,
        "toggle_gtrade": True,
        "toggle_hype": True,
        "toggle_music": False,
        "toggle_storms": False,
        "toggle_who_dis": False,
        "toggle_agent": False,
        "toggle_legacy_prefix_commands": False,
        "version": "8.0"
    }

    #region the card
    def press(self, userId = 1):
        interaction = Mock(spec = nextcord.Interaction)
        interaction.guild = self.guild
        interaction.user = Mock(id = userId, mention = f'<@{userId}>')
        interaction.response = Mock(defer = AsyncMock(), send_modal = AsyncMock(), is_done = Mock(return_value = False))
        interaction.edit_original_message = AsyncMock()
        interaction.channel = Mock(send = AsyncMock())
        interaction.send = AsyncMock()
        return interaction

    def card(self, config = None):
        self.guild.get_channel = Mock(side_effect = lambda channelId: named('storms' if channelId == 222 else 'admin'))
        self.guild.get_role = Mock(side_effect = lambda roleId: named('admins'))
        self.patches = [
            patch.object(config_queries, 'getAllServerValues', MagicMock(return_value = dict(config or self.FULL_CONFIG))),
            patch.object(config_cog.predicates, 'recheck', AsyncMock())
        ]
        for started in self.patches:
            started.start()
        self.addCleanup(lambda: [started.stop() for started in self.patches])
        return ConfigCard(self.config, self.guild)

    def labelled(self, view, label):
        return next(item for item in view.children if getattr(item, 'label', None) == label)

    async def test_the_slash_command_opens_the_card_privately(self):
        self.card()
        interaction = self.press()
        await self.config.configSlash(interaction)
        kwargs = interaction.send.await_args.kwargs
        self.assertTrue(kwargs['ephemeral'])
        self.assertEqual(kwargs['embed'].title, '⚙️ GBot Configuration')
        self.assertIsInstance(kwargs['view'], ConfigCard)

    async def test_the_prefix_command_offers_it_privately(self):
        self.ctx.author = Mock(id = 1, display_name = 'Stormer')
        self.ctx.send = AsyncMock()
        with patch.object(config_cog.pagination, 'openPrivately', AsyncMock()) as openPrivately:
            await self.config.config(self.config, self.ctx)
        openPrivately.assert_awaited_once_with(self.ctx, '⚙️', 'GBot settings', self.config.openCard, admin = True)

    async def test_the_card_shows_everything_and_fits_discord(self):
        card = self.card()
        embed = await card.render()
        fields = {field.name: field.value for field in embed.fields}
        self.assertEqual(fields['Channels'], 'Storms: <#222>\nAdmin: <#111>')
        self.assertEqual(fields['Roles'], 'Admin: <@&333>\nWho Dis: <@&444>')
        self.assertEqual(fields['Prefix'], '`.`')
        self.assertEqual(embed.thumbnail.url, 'icon url')
        # green is on, grey is off, in the same order as everywhere else
        toggles = [item for item in card.children if isinstance(item, nextcord.ui.Button)][:8]
        self.assertEqual([item.label for item in toggles], ['Agent', 'GCoin', 'GTrade', 'Hype', 'Music', 'Storms', 'Who Dis', 'Prefix commands'])
        self.assertEqual([item.style for item in toggles[:3]], [nextcord.ButtonStyle.secondary, nextcord.ButtonStyle.success, nextcord.ButtonStyle.success])
        pickers = [item for item in card.children if isinstance(item, nextcord.ui.ChannelSelect)]
        self.assertEqual([picker.placeholder for picker in pickers], ['🌧️ Storms channel: #storms', '🛡️ Admin channel: #admin'])
        self.assertEqual(pickers[0].channel_types, [nextcord.ChannelType.text])
        for row in card.to_components():
            self.assertLessEqual(len(row['components']), 5)

    async def test_a_server_missing_fields_shows_them_off_or_not_set(self):
        card = self.card({'prefix': '!', 'version': '8.0'})
        self.guild.icon = None
        embed = await card.render()
        fields = {field.name: field.value for field in embed.fields}
        self.assertEqual(fields['Channels'], 'Storms: Not set\nAdmin: Not set')
        self.assertIsNone(embed.thumbnail.url)
        self.assertEqual(self.labelled(card, 'Agent').style, nextcord.ButtonStyle.secondary)
        self.guild.get_channel = Mock(return_value = None)
        self.assertEqual(config_cog.channelName(self.guild, '5'), 'Not set')
        self.guild.get_role = Mock(return_value = None)
        self.assertEqual(config_cog.roleName(self.guild, '5'), 'Not set')

    async def test_turning_a_feature_on_also_turns_on_what_it_needs(self):
        card = self.card()
        await card.render()
        values = {'toggle_storms': False, 'toggle_gcoin': False}
        with patch.object(config_queries, 'getServerValue', side_effect = lambda serverId, key: values[key]), \
             patch.object(config_queries, 'setServerValue', side_effect = lambda serverId, key, value: values.__setitem__(key, value)):
            interaction = self.press()
            await self.labelled(card, 'Storms').callback(interaction)
        self.assertEqual(values, {'toggle_storms': True, 'toggle_gcoin': True})
        interaction.response.defer.assert_awaited_once()
        config_cog.predicates.recheck.assert_awaited_with(interaction, admin = True)
        embed = interaction.edit_original_message.await_args.kwargs['embed']
        self.assertEqual(embed.fields[-1].value, '🌧️ **Storms** is now on. Also turned on, as it needs them: GCoin.')

    async def test_turning_gcoin_off_turns_off_what_needs_it(self):
        values = {'toggle_gcoin': True, 'toggle_gtrade': True, 'toggle_storms': False, 'toggle_who_dis': True}
        with patch.object(config_queries, 'getServerValue', side_effect = lambda serverId, key: values[key]), \
             patch.object(config_queries, 'setServerValue', side_effect = lambda serverId, key, value: values.__setitem__(key, value)):
            notice = await self.config.toggleFeature(self.press(), 'toggle_gcoin')
        self.assertEqual(values, {'toggle_gcoin': False, 'toggle_gtrade': False, 'toggle_storms': False, 'toggle_who_dis': False})
        self.assertEqual(notice, '💰 **GCoin** is now off. Also turned off, as they need it: GTrade, Who Dis.')

    async def test_the_toggle_runs_off_the_event_loop_as_one_step(self):
        threads = set()
        def record(*args):
            threads.add(threading.current_thread())
            return True
        with patch.object(config_queries, 'getServerValue', side_effect = record), patch.object(config_queries, 'setServerValue', side_effect = record):
            await self.config.toggleFeature(self.press(), 'toggle_gtrade')
        self.assertEqual(len(threads), 1)
        self.assertNotIn(threading.main_thread(), threads)

    async def test_turning_the_agent_on_says_so_in_public(self):
        interaction = self.press()
        with patch.object(config_queries, 'getServerValue', return_value = False), patch.object(config_queries, 'setServerValue'):
            notice = await self.config.toggleFeature(interaction, 'toggle_agent')
        self.assertEqual(notice, '🤖 **Agent** is now on.')
        interaction.channel.send.assert_awaited_once_with(config_cog.strings.AGENT_NOTICE)

    async def test_turning_music_off_leaves_the_voice_channel(self):
        music = Mock(disconnectAndClearQueue = AsyncMock())
        self.config.client = Mock(get_cog = Mock(return_value = music))
        with patch.object(config_queries, 'getServerValue', return_value = True), patch.object(config_queries, 'setServerValue'):
            notice = await self.config.toggleFeature(self.press(), 'toggle_legacy_prefix_commands')
            self.assertEqual(notice, '⌨️ **Prefix commands** is now off.')
            music.disconnectAndClearQueue.assert_not_awaited()
            await self.config.toggleFeature(self.press(), 'toggle_music')
        music.disconnectAndClearQueue.assert_awaited_once_with(str(self.guild.id))

    async def test_picking_channels_and_roles(self):
        card = self.card()
        await card.render()
        with patch.object(config_queries, 'setServerValue') as setServerValue:
            interaction = self.press()
            await card.channelCallback('channel_storms', 'Storms')(interaction, Mock(id = 9, mention = '<#9>'))
            setServerValue.assert_called_with(self.guild.id, 'channel_storms', '9')
            self.assertEqual(interaction.edit_original_message.await_args.kwargs['embed'].fields[-1].value, '⚙️ Storms channel set to <#9>.')
            interaction = self.press()
            await self.labelled(card, 'Roles').callback(interaction)
            embed = interaction.edit_original_message.await_args.kwargs['embed']
            self.assertEqual(embed.title, '👥 Roles')
            self.assertEqual([item.placeholder for item in card.children if isinstance(item, nextcord.ui.RoleSelect)], ['🛡️ Admin role: @admins', '❓ Who Dis role: @admins'])
            await card.roleCallback('role_who_dis', 'Who Dis')(interaction, Mock(id = 7, mention = '<@&7>'))
            setServerValue.assert_called_with(self.guild.id, 'role_who_dis', '7')
            await self.labelled(card, 'Back').callback(interaction)
        self.assertEqual(interaction.edit_original_message.await_args.kwargs['embed'].title, '⚙️ GBot Configuration')

    async def test_the_prefix_form(self):
        card = self.card()
        await card.render()
        interaction = self.press()
        await self.labelled(card, 'Prefix').callback(interaction)
        form = interaction.response.send_modal.await_args.args[0]
        self.assertEqual(form.inputs[0].default_value, '.')
        with patch.object(config_queries, 'setServerValue') as setServerValue:
            submitted = self.press()
            await card.savePrefix(submitted, ['!'])
            setServerValue.assert_called_once_with(self.guild.id, 'prefix', '!')
            self.assertEqual(submitted.edit_original_message.await_args.kwargs['embed'].fields[-1].value, '⚙️ Prefix set to `!`.')
            await card.savePrefix(submitted, [''])
            setServerValue.assert_called_once()
        self.assertIn('at least one character', submitted.edit_original_message.await_args.kwargs['embed'].fields[-1].value)

    async def test_the_agent_settings_button_opens_the_agent_card(self):
        card = self.card()
        await card.render()
        agent = Mock(openCard = AsyncMock())
        self.config.client = Mock(get_cog = Mock(return_value = agent))
        interaction = self.press()
        interaction.response.is_done = Mock(return_value = True)
        await self.labelled(card, 'Agent settings').callback(interaction)
        interaction.response.defer.assert_not_awaited()
        agent.openCard.assert_awaited_once_with(interaction, interaction.user)

    async def test_looking_up_a_members_reports(self):
        card = self.card()
        await card.render()
        interaction = self.press()
        await self.labelled(card, 'Reports').callback(interaction)
        embed = interaction.edit_original_message.await_args.kwargs['embed']
        self.assertEqual(embed.title, '🚩 Reports')
        member = Mock(id = 5, display_name = 'Sam', mention = '<@5>')
        reports = [{'targetId': '5', 'reporterId': str(n), 'where': '#general', 'when': '2026-11-0{}T12:00:00+00:00'.format(n), 'what': ''} for n in range(1, 8)]
        with patch.object(config_queries, 'getReportsOn', return_value = reports):
            await card.pickMember(interaction, member)
        embed = interaction.edit_original_message.await_args.kwargs['embed']
        self.assertEqual(embed.title, '🚩 Reports on Sam · 7')
        self.assertTrue(embed.footer.text.startswith('Page 1 / 2'))
        arrows = [item for item in card.children if getattr(item, 'emoji', None) is not None and str(item.emoji) in ('◀️', '▶️')]
        self.assertTrue(arrows[0].disabled)
        await arrows[1].callback(interaction)
        self.assertTrue(interaction.edit_original_message.await_args.kwargs['embed'].footer.text.startswith('Page 2 / 2'))
        arrows = [item for item in card.children if getattr(item, 'emoji', None) is not None and str(item.emoji) in ('◀️', '▶️')]
        await arrows[0].callback(interaction)
        self.assertTrue(interaction.edit_original_message.await_args.kwargs['embed'].footer.text.startswith('Page 1 / 2'))
        with patch.object(config_queries, 'getReportsOn', return_value = []):
            await card.pickMember(interaction, member)
        self.assertEqual(interaction.edit_original_message.await_args.kwargs['embed'].description, 'No reports on <@5>.')
    #endregion

    #region reports
    def message(self, authorId, content = 'hi', minute = 0, attachments = (), stickers = ()):
        import datetime
        return Mock(author = Mock(id = authorId), content = content, attachments = list(attachments), stickers = list(stickers), created_at = datetime.datetime(2026, 11, 7, 20, minute, tzinfo = datetime.timezone.utc))

    async def test_nobody_can_report_themselves(self):
        interaction = self.press(5)
        with patch.object(config_cog.presentation, 'sendError', AsyncMock()) as sendError:
            await self.config.reportMember(interaction, Mock(id = 5))
        self.assertIn("can't report yourself", sendError.await_args.args[1])
        interaction.response.send_modal.assert_not_awaited()

    async def test_a_report_asks_what_happened_then_files_it(self):
        interaction = self.press(1)
        target = Mock(id = 5, display_name = 'Sam')
        reported = self.message(5)
        await self.config.reportMessage(interaction, Mock(author = target))
        form = interaction.response.send_modal.await_args.args[0]
        self.assertEqual(form.title, 'Report Sam')
        self.assertFalse(form.inputs[0].required)
        submitted = self.press(1)
        submitted.channel = Mock(mention = '<#3>')
        with patch.object(self.config, 'captureMessages', AsyncMock(return_value = [reported])) as capture, \
             patch.object(self.config, 'fileReport', AsyncMock(return_value = True)) as fileReport:
            form.inputs[0]._inputed_value = 'rude'
            await form.callback(submitted)
            submitted.response.defer.assert_awaited_once_with(ephemeral = True)
            fileReport.assert_awaited_once_with(self.guild, submitted.user, target, '<#3>', [reported], 'rude')
            self.assertEqual(submitted.send.await_args.kwargs['content'], '🚩 Sent to the admins. Thanks for letting them know.')
            fileReport.return_value = False
            await self.config.submitReport(submitted, target, None, '')
        self.assertIn('no admin channel', submitted.send.await_args.kwargs['embed'].description)
        await self.config.reportMember(interaction, target)
        self.assertEqual(interaction.response.send_modal.await_count, 2)

    async def test_capturing_the_reported_message_and_earlier_ones(self):
        from GBotDiscord.test.utils import AsyncIter
        reported = self.message(5, minute = 9)
        history = [self.message(5, minute = 8), self.message(6, minute = 7)] + [self.message(5, minute = m) for m in range(6, 0, -1)]
        channel = Mock(history = Mock(return_value = AsyncIter(history)))
        captured = await self.config.captureMessages(channel, Mock(id = 5), reported)
        self.assertEqual([message.created_at.minute for message in captured], [4, 5, 6, 8, 9])
        channel.history.assert_called_once_with(limit = 100, before = reported)
        # a short channel's history just runs out
        channel = Mock(history = Mock(return_value = AsyncIter([self.message(5, minute = 1)])))
        self.assertEqual(len(await self.config.captureMessages(channel, Mock(id = 5), None)), 1)
        # a channel GBot can't read still files the report, with what it has
        channel.history = Mock(side_effect = nextcord.Forbidden(Mock(status = 403, reason = 'no'), 'no'))
        self.assertEqual(await self.config.captureMessages(channel, Mock(id = 5), None), [])

    async def test_the_captured_text_is_quoted_and_fits(self):
        self.assertEqual(config_cog.capturedText([]), 'None could be captured.')
        messages = [self.message(5, 'x' * 2000), self.message(5, '', attachments = [Mock(url = 'https://cdn/a.png')]), self.message(5, '')]
        text = config_cog.capturedText(messages)
        self.assertLessEqual(len(text), 1024)
        lines = text.split('\n')
        self.assertTrue(lines[0].startswith('> <t:'))
        self.assertTrue(lines[0].endswith('…'))
        self.assertTrue(lines[1].endswith('📎 https://cdn/a.png'))
        self.assertTrue(lines[2].endswith('*(nothing but an embed)*'))

    def adminChannel(self):
        channel = Mock(send = AsyncMock())
        self.guild.get_channel = Mock(return_value = channel)
        return channel

    async def test_filing_posts_the_card_and_keeps_the_report(self):
        channel = self.adminChannel()
        target = Mock(id = 5, display_name = 'Sam', mention = '<@5>')
        with patch.object(config_queries, 'getServerValue', return_value = '111'), \
             patch.object(config_queries, 'addReport', return_value = 'r1') as addReport, \
             patch.object(config_queries, 'getReportsOn', return_value = [{'when': '2000-01-01T00:00:00+00:00'}, {'when': '2999-01-01T00:00:00+00:00'}, {'when': '2999-01-01T00:00:00+00:00'}]):
            self.assertTrue(await self.config.fileReport(self.guild, Mock(id = 1, mention = '<@1>'), target, '<#3>', [], 'rude'))
        report = addReport.call_args.args[1]
        self.assertEqual({key: report[key] for key in ('targetId', 'reporterId', 'where', 'what')}, {'targetId': '5', 'reporterId': '1', 'where': '<#3>', 'what': 'rude'})
        kwargs = channel.send.await_args.kwargs
        embed = kwargs['embed']
        self.assertEqual(embed.title, '🚩 Report: Sam')
        self.assertEqual(embed.color, presentation.WARNING_COLOR)
        self.assertEqual(embed.description, '**Reported:** <@5>\n**By:** <@1> in <#3>\n**What happened:** rude')
        self.assertEqual(embed.fields[1].value, '2nd report on <@5> in the last 30 days.')
        self.assertEqual([item.custom_id for item in kwargs['view'].children], ['report:handled:r1:5', 'report:dismissed:r1:5', 'report:history:5'])
        self.assertTrue(kwargs['view'].is_finished())

    async def test_filing_with_nowhere_to_post(self):
        with patch.object(config_queries, 'getServerValue', return_value = None):
            self.assertFalse(await self.config.fileReport(self.guild, Mock(), Mock(), '#x', [], ''))
        channel = self.adminChannel()
        channel.send.side_effect = nextcord.Forbidden(Mock(status = 403, reason = 'no'), 'no')
        with patch.object(config_queries, 'getServerValue', return_value = '111'), \
             patch.object(config_queries, 'addReport', return_value = 'r1'), \
             patch.object(config_queries, 'getReportsOn', return_value = []), \
             patch.object(GBotFirebaseService, 'remove', MagicMock()) as remove:
            self.assertFalse(await self.config.fileReport(self.guild, Mock(id = 1, mention = '<@1>'), Mock(id = 5, display_name = 'Sam', mention = '<@5>'), '#x', [], ''))
        remove.assert_called_once_with(['reports', self.guild.id, 'r1'])

    def test_ordinals_and_report_lines(self):
        self.assertEqual([presentation.ordinal(n) for n in (1, 2, 3, 4, 11, 12, 13, 21, 22, 103, 111)], ['1st', '2nd', '3rd', '4th', '11th', '12th', '13th', '21st', '22nd', '103rd', '111th'])
        report = {'reporterId': '1', 'where': '#general', 'when': '2026-11-07T12:00:00+00:00', 'what': ''}
        self.assertEqual(config_cog.describeReport(report), '**<t:1794052800:d>** · by <@1> · #general')
        self.assertTrue(config_cog.describeReport(dict(report, outcome = 'handled', outcomeBy = '2', what = 'rude')).endswith(' · ✅ handled by <@2>\n> rude'))
        self.assertTrue(config_cog.describeReport(dict(report, outcome = 'dismissed', outcomeBy = '2')).endswith(' · 🚫 not an issue, said <@2>'))
        # a page of five long ones still fits in one embed
        self.assertTrue(config_cog.describeReport(dict(report, what = 'x' * 1000)).endswith('x…'))
        self.assertLess(len(config_cog.describeReport(dict(report, what = 'x' * 1000))) * 5, 4096)

    def buttonPress(self, customId, userId = 1):
        interaction = self.press(userId)
        interaction.type = nextcord.InteractionType.component
        interaction.data = {'custom_id': customId}
        interaction.message = Mock(edit = AsyncMock(), embeds = [presentation.warningEmbed(title = '🚩 Report: Sam')])
        return interaction

    async def test_an_admin_records_the_outcome_on_the_card(self):
        for outcome, expected, color in (('handled', '✅ Handled by <@1>', presentation.BRAND_COLOR), ('dismissed', '🚫 Not an issue, said <@1>', presentation.WARNING_COLOR)):
            interaction = self.buttonPress(f'report:{outcome}:r1:5')
            with patch.object(config_cog.predicates, 'recheck', AsyncMock()) as recheck, \
                 patch.object(config_queries, 'setReportOutcome', return_value = True) as setReportOutcome:
                await self.config.on_interaction(interaction)
            recheck.assert_awaited_once_with(interaction, admin = True)
            setReportOutcome.assert_called_once_with(self.guild.id, 'r1', outcome, '1')
            kwargs = interaction.message.edit.await_args.kwargs
            self.assertEqual(kwargs['embed'].fields[-1].value, expected)
            self.assertEqual(kwargs['embed'].color, color)
            self.assertEqual([item.custom_id for item in kwargs['view'].children], ['report:history:5'])

    async def test_the_history_button_lists_their_reports_privately(self):
        interaction = self.buttonPress('report:history:5')
        self.guild.get_member = Mock(return_value = Mock(display_name = 'Sam'))
        with patch.object(config_cog.predicates, 'recheck', AsyncMock()), \
             patch.object(config_queries, 'getReportsOn', return_value = [{'reporterId': '1', 'where': '#g', 'when': '2026-11-07T12:00:00+00:00', 'what': ''}]), \
             patch.object(config_cog.pagination, 'startPages', AsyncMock()) as startPages:
            await self.config.on_interaction(interaction)
            interaction.response.defer.assert_awaited_once_with(ephemeral = True)
            pages = startPages.await_args.args[1]
            self.assertEqual(pages.source.title, '🚩 Reports on Sam · 1')
            self.assertTrue(startPages.await_args.kwargs['ephemeral'])
            self.guild.get_member = Mock(return_value = None)
            await self.config.on_interaction(self.buttonPress('report:history:5'))
        self.assertEqual(startPages.await_args.args[1].source.title, '🚩 Reports on a former member · 1')

    async def test_a_report_button_refused_or_not_ours(self):
        interaction = self.buttonPress('report:handled:r1:5', userId = 2)
        with patch.object(config_cog.predicates, 'recheck', AsyncMock(side_effect = config_cog.predicates.MessageAuthorNotAdmin('x'))), \
             patch.object(config_cog.presentation, 'sendInteractionError', AsyncMock()) as sendInteractionError:
            await self.config.on_interaction(interaction)
            sendInteractionError.assert_awaited_once()
            interaction.message.edit.assert_not_awaited()
            # someone else's buttons, and a press of an unknown kind, are left alone
            await self.config.on_interaction(self.buttonPress('gtrade:buy:1'))
            await self.config.on_interaction(self.buttonPress('report:other:1'))
        sendInteractionError.assert_awaited_once()
    #endregion

    def test_setup_adds_cog(self):
        from GBotDiscord.src.config import config_cog
        client = MagicMock()
        config_cog.setup(client)
        client.add_cog.assert_called_once()
        addedCog = client.add_cog.call_args[0][0]
        self.assertIsInstance(addedCog, Config)

if __name__ == "__main__":
    unittest.main()