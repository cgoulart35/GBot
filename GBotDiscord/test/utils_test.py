#region IMPORTS
import logging
import unittest
from decimal import Decimal
from unittest.mock import MagicMock, Mock, AsyncMock, patch

import nextcord
from nextcord.ext import commands
from nextcord.ext.commands.errors import ArgumentParsingError

from GBotDiscord.test.utils import AsyncIter
from GBotDiscord.src import utils
from GBotDiscord.src.config import config_queries
from GBotDiscord.src.properties import GBotPropertiesManager
#endregion

# Snapshot original utils functions at import time. Other test suites monkey-patch
# utils.* (e.g. gtrade_test sets utils.isUrlImageContentTypeAndStatus200) and never
# restore — so we restore in setUp to make TestUtils order-independent.
_ORIGINAL_UTILS_FUNCS = {
    name: getattr(utils, name)
    for name in dir(utils)
    if callable(getattr(utils, name)) and not name.startswith('_')
}


class TestUtils(unittest.IsolatedAsyncioTestCase):

    @classmethod
    def setUpClass(self):
        print('\nExecuting utils unit tests...\n')

    @classmethod
    def tearDownClass(self):
        print('\n\nCompleted utils unit tests.\n')

    def setUp(self):
        for name, fn in _ORIGINAL_UTILS_FUNCS.items():
            setattr(utils, name, fn)
        self.client: nextcord.Client = commands.Bot()
        self._saved_patreon_guild_id = GBotPropertiesManager.PATREON_GUILD_ID
        self._saved_patreon_ignore_guilds = GBotPropertiesManager.PATREON_IGNORE_GUILDS

    def tearDown(self):
        GBotPropertiesManager.PATREON_GUILD_ID = self._saved_patreon_guild_id
        GBotPropertiesManager.PATREON_IGNORE_GUILDS = self._saved_patreon_ignore_guilds

    # region idToUserStr / idToRoleStr / idToChannelStr

    def test_idToUserStr(self):
        self.assertEqual(utils.idToUserStr(123), '<@!123>')

    def test_idToRoleStr(self):
        self.assertEqual(utils.idToRoleStr(456), '<@&456>')

    def test_idToChannelStr(self):
        self.assertEqual(utils.idToChannelStr(789), '<#789>')

    # endregion

    # region idStrArgToInt

    def test_idStrArgToInt_numeric_returns_int(self):
        self.assertEqual(utils.idStrArgToInt('42', 'role'), 42)

    def test_idStrArgToInt_non_numeric_raises(self):
        with self.assertRaises(ArgumentParsingError):
            utils.idStrArgToInt('abc', 'role')

    # endregion

    # region strParamToArgs

    def test_strParamToArgs_single_quoted(self):
        self.assertEqual(utils.strParamToArgs('"abc"'), ['abc'])

    def test_strParamToArgs_two_quoted(self):
        self.assertEqual(utils.strParamToArgs('"a" "b"'), ['a', 'b'])

    def test_strParamToArgs_three_quoted_with_extra_whitespace(self):
        self.assertEqual(utils.strParamToArgs('"a"   "b"   "c"'), ['a', 'b', 'c'])

    def test_strParamToArgs_empty_string(self):
        self.assertEqual(utils.strParamToArgs(''), [])

    def test_strParamToArgs_no_quotes(self):
        self.assertEqual(utils.strParamToArgs('no quotes here'), ['no quotes here'])

    # endregion

    # region emojisParamToArgs

    def test_emojisParamToArgs_single_unicode(self):
        self.assertEqual(utils.emojisParamToArgs('😀'), ['😀'])

    def test_emojisParamToArgs_single_custom(self):
        self.assertEqual(utils.emojisParamToArgs('<:foo:123>'), ['<:foo:123>'])

    def test_emojisParamToArgs_mixed_unicode_and_custom(self):
        self.assertEqual(utils.emojisParamToArgs('😀<:foo:123>'), ['😀', '<:foo:123>'])

    def test_emojisParamToArgs_whitespace_skipped(self):
        self.assertEqual(utils.emojisParamToArgs('  😀  <:foo:123>  '), ['😀', '<:foo:123>'])

    def test_emojisParamToArgs_empty_raises(self):
        with self.assertRaises(ArgumentParsingError):
            utils.emojisParamToArgs('')

    def test_emojisParamToArgs_no_emoji_raises(self):
        with self.assertRaises(ArgumentParsingError):
            utils.emojisParamToArgs('hello')

    # endregion

    # region isUserAdminOrOwner

    def test_isUserAdminOrOwner_owner(self):
        user = Mock()
        user.id = 1
        user.roles = []
        guild = Mock()
        guild.id = 999
        guild.owner_id = 1
        config_queries.getServerValue = MagicMock(return_value = '555')
        self.assertTrue(utils.isUserAdminOrOwner(user, guild))

    def test_isUserAdminOrOwner_admin_role_match(self):
        role = Mock()
        role.id = 555
        user = Mock()
        user.id = 2
        user.roles = [role]
        guild = Mock()
        guild.id = 999
        guild.owner_id = 1
        config_queries.getServerValue = MagicMock(return_value = '555')
        self.assertTrue(utils.isUserAdminOrOwner(user, guild))

    def test_isUserAdminOrOwner_no_match(self):
        user = Mock()
        user.id = 2
        user.roles = []
        guild = Mock()
        guild.id = 999
        guild.owner_id = 1
        config_queries.getServerValue = MagicMock(return_value = '555')
        self.assertFalse(utils.isUserAdminOrOwner(user, guild))

    # endregion

    # region isUserAssignedRole

    def test_isUserAssignedRole_none_role(self):
        user = Mock()
        user.roles = []
        self.assertFalse(utils.isUserAssignedRole(user, None))

    def test_isUserAssignedRole_match(self):
        role = Mock()
        role.id = 42
        user = Mock()
        user.roles = [role]
        self.assertTrue(utils.isUserAssignedRole(user, '42'))

    def test_isUserAssignedRole_no_match(self):
        role = Mock()
        role.id = 1
        user = Mock()
        user.roles = [role]
        self.assertFalse(utils.isUserAssignedRole(user, '99'))

    # endregion

    # region isUserInThisGuildAndNotABot

    async def test_isUserInThisGuildAndNotABot_human_found(self):
        target = Mock(id = 1, bot = False)
        other = Mock(id = 2, bot = False)
        guild = Mock()
        guild.fetch_members = MagicMock(return_value = AsyncIter([other, target]))
        user = Mock(id = 1)
        self.assertTrue(await utils.isUserInThisGuildAndNotABot(user, guild))

    async def test_isUserInThisGuildAndNotABot_bot_found(self):
        bot_member = Mock(id = 1, bot = True)
        guild = Mock()
        guild.fetch_members = MagicMock(return_value = AsyncIter([bot_member]))
        user = Mock(id = 1)
        self.assertFalse(await utils.isUserInThisGuildAndNotABot(user, guild))

    async def test_isUserInThisGuildAndNotABot_not_found(self):
        other = Mock(id = 2, bot = False)
        guild = Mock()
        guild.fetch_members = MagicMock(return_value = AsyncIter([other]))
        user = Mock(id = 1)
        self.assertFalse(await utils.isUserInThisGuildAndNotABot(user, guild))

    # endregion

    # region isUrlImageContentTypeAndStatus200

    async def _runUrlImageCheck(self, response_or_exc):
        mock_client_instance = MagicMock()
        mock_client_instance.__aenter__ = AsyncMock(return_value = mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value = None)
        if isinstance(response_or_exc, Exception):
            mock_client_instance.get = AsyncMock(side_effect = response_or_exc)
        else:
            mock_client_instance.get = AsyncMock(return_value = response_or_exc)
        with patch.object(utils.httpx, 'AsyncClient', return_value = mock_client_instance):
            return await utils.isUrlImageContentTypeAndStatus200('http://example.com/img.png')

    async def test_isUrlImageContentTypeAndStatus200_png_200(self):
        response = Mock(status_code = 200, headers = {'content-type': 'image/png'})
        self.assertTrue(await self._runUrlImageCheck(response))

    async def test_isUrlImageContentTypeAndStatus200_jpeg_200(self):
        response = Mock(status_code = 200, headers = {'content-type': 'image/jpeg'})
        self.assertTrue(await self._runUrlImageCheck(response))

    async def test_isUrlImageContentTypeAndStatus200_wrong_content_type(self):
        response = Mock(status_code = 200, headers = {'content-type': 'text/html'})
        self.assertFalse(await self._runUrlImageCheck(response))

    async def test_isUrlImageContentTypeAndStatus200_500(self):
        response = Mock(status_code = 500, headers = {'content-type': 'image/png'})
        self.assertFalse(await self._runUrlImageCheck(response))

    async def test_isUrlImageContentTypeAndStatus200_get_raises(self):
        self.assertFalse(await self._runUrlImageCheck(RuntimeError('boom')))

    # endregion

    # region calculateTimeLeftStr

    def test_calculateTimeLeftStr_zero(self):
        self.assertEqual(utils.calculateTimeLeftStr(0), '0h 00m 00s')

    def test_calculateTimeLeftStr_under_minute(self):
        self.assertEqual(utils.calculateTimeLeftStr(59), '0h 00m 59s')

    def test_calculateTimeLeftStr_over_hour(self):
        self.assertEqual(utils.calculateTimeLeftStr(3661), '1h 01m 01s')

    # endregion

    # region roundDecimalPlaces

    def test_roundDecimalPlaces_two_places_half_up(self):
        self.assertEqual(utils.roundDecimalPlaces(Decimal('1.005'), 2), Decimal('1.01'))

    def test_roundDecimalPlaces_two_places_pads_zero(self):
        self.assertEqual(utils.roundDecimalPlaces(Decimal('21'), 2), Decimal('21.00'))

    def test_roundDecimalPlaces_zero_places(self):
        self.assertEqual(utils.roundDecimalPlaces(Decimal('21.49'), 0), Decimal('21'))

    def test_roundDecimalPlaces_zero_places_half_up(self):
        self.assertEqual(utils.roundDecimalPlaces(Decimal('21.5'), 0), Decimal('22'))

    # endregion

    # region copyDictWithoutKeys

    def test_copyDictWithoutKeys_excludes_keys(self):
        source = {'a': 1, 'b': 2, 'c': 3}
        result = utils.copyDictWithoutKeys(source, ['b'])
        self.assertEqual(result, {'a': 1, 'c': 3})

    def test_copyDictWithoutKeys_does_not_mutate_original(self):
        source = {'a': 1, 'b': 2}
        utils.copyDictWithoutKeys(source, ['a'])
        self.assertEqual(source, {'a': 1, 'b': 2})

    # endregion

    # region filterGuildsForInstance

    def test_filterGuildsForInstance_keeps_present_drops_orphans(self):
        client = Mock()
        guild1 = Mock(id = 100)
        guild2 = Mock(id = 200)
        client.guilds = [guild1, guild2]
        allServerData = {
            '100': {'prefix': '.'},
            '200': {'prefix': '!'},
            '999': {'prefix': '?'}
        }
        filtered = utils.filterGuildsForInstance(client, allServerData)
        self.assertEqual(filtered, {'100': {'prefix': '.'}, '200': {'prefix': '!'}})

    # endregion

    # region getServerPrefixOrDefault

    def test_getServerPrefixOrDefault_dm(self):
        message = Mock()
        message.guild = None
        self.assertEqual(utils.getServerPrefixOrDefault(message), '.')

    def test_getServerPrefixOrDefault_guild(self):
        message = Mock()
        message.guild = Mock(id = 1)
        config_queries.getServerValue = MagicMock(return_value = '!')
        self.assertEqual(utils.getServerPrefixOrDefault(message), '!')

    # endregion

    # region getGuildsForPatreonToIgnore

    def test_getGuildsForPatreonToIgnore_appends_patreon_guild_id(self):
        GBotPropertiesManager.PATREON_GUILD_ID = '999'
        GBotPropertiesManager.PATREON_IGNORE_GUILDS = ['111', '222']
        result = utils.getGuildsForPatreonToIgnore()
        self.assertIn('999', result)
        self.assertIn('111', result)
        self.assertIn('222', result)

    def test_getGuildsForPatreonToIgnore_does_not_duplicate(self):
        GBotPropertiesManager.PATREON_GUILD_ID = '999'
        GBotPropertiesManager.PATREON_IGNORE_GUILDS = ['999', '111']
        result = utils.getGuildsForPatreonToIgnore()
        self.assertEqual(result.count('999'), 1)

    # endregion

    # region getOnlineAndIdleUsers

    async def test_getOnlineAndIdleUsers_empty(self):
        guild = Mock()
        guild.fetch_members = MagicMock(return_value = AsyncIter([]))
        result = await utils.getOnlineAndIdleUsers(guild)
        self.assertEqual(result, [])

    async def test_getOnlineAndIdleUsers_filters_correctly(self):
        online_user = Mock(id = 1, bot = False, status = nextcord.Status.online)
        idle_user = Mock(id = 2, bot = False, status = nextcord.Status.idle)
        offline_user = Mock(id = 3, bot = False, status = nextcord.Status.offline)
        online_bot = Mock(id = 4, bot = True, status = nextcord.Status.online)

        member_lookup = {1: online_user, 2: idle_user, 3: offline_user, 4: online_bot}
        guild = Mock()
        guild.fetch_members = MagicMock(return_value = AsyncIter([online_user, idle_user, offline_user, online_bot]))
        guild.get_member = MagicMock(side_effect = lambda mid: member_lookup[mid])

        result = await utils.getOnlineAndIdleUsers(guild)
        self.assertEqual(len(result), 2)
        result_ids = [m.id for m in result]
        self.assertIn(1, result_ids)
        self.assertIn(2, result_ids)

    # endregion

    # region getUserIdFromName

    async def test_getUserIdFromName_case_insensitive_match(self):
        m1 = Mock(id = 1)
        m1.name = 'Alice'
        m2 = Mock(id = 2)
        m2.name = 'Bob'
        guild = Mock()
        guild.fetch_members = MagicMock(return_value = AsyncIter([m1, m2]))
        self.assertEqual(await utils.getUserIdFromName(guild, 'alice'), 1)

    async def test_getUserIdFromName_no_match(self):
        m1 = Mock(id = 1)
        m1.name = 'Alice'
        guild = Mock()
        guild.fetch_members = MagicMock(return_value = AsyncIter([m1]))
        self.assertIsNone(await utils.getUserIdFromName(guild, 'charlie'))

    # endregion

    # region askUserQuestion

    async def test_askUserQuestion_sends_and_returns_message(self):
        context = Mock()
        context.channel = Mock(id = 10)
        context.send = AsyncMock()

        author = Mock(id = 5)

        reply_msg = Mock()
        reply_msg.author = author
        reply_msg.channel = context.channel

        self.client.wait_for = AsyncMock(return_value = reply_msg)

        result = await utils.askUserQuestion(self.client, context, author, 'Are you sure?', 30)
        self.assertIs(result, reply_msg)
        context.send.assert_awaited_once_with('Are you sure?')
        self.client.wait_for.assert_awaited_once()
        args, kwargs = self.client.wait_for.call_args
        self.assertEqual(args[0], 'message')
        self.assertEqual(kwargs['timeout'], 30)

    async def test_askUserQuestion_check_matches_author_and_channel(self):
        context = Mock()
        context.channel = Mock(id = 10)
        context.send = AsyncMock()
        author = Mock(id = 5)

        captured = {}
        async def fake_wait_for(event, check, timeout):
            captured['check'] = check
            return Mock()
        self.client.wait_for = fake_wait_for

        await utils.askUserQuestion(self.client, context, author, 'Q', 5)
        check = captured['check']

        matching = Mock(author = author, channel = context.channel)
        wrong_author = Mock(author = Mock(), channel = context.channel)
        wrong_channel = Mock(author = author, channel = Mock())

        self.assertTrue(check(matching))
        self.assertFalse(check(wrong_author))
        self.assertFalse(check(wrong_channel))

    # endregion

    # region sendDiscordEmbed

    async def test_sendDiscordEmbed_bare(self):
        context = Mock()
        context.send = AsyncMock()
        await utils.sendDiscordEmbed(context, 'Title', None, nextcord.Color.blue())
        context.send.assert_awaited_once()
        kwargs = context.send.call_args.kwargs
        embed: nextcord.Embed = kwargs['embed']
        self.assertEqual(embed.title, 'Title')
        self.assertIs(embed.description, None)
        self.assertNotIn('file', kwargs)
        self.assertNotIn('delete_after', kwargs)

    async def test_sendDiscordEmbed_description_thumbnail_deleteAfter(self):
        context = Mock()
        context.send = AsyncMock()
        await utils.sendDiscordEmbed(
            context, 'T', 'desc', nextcord.Color.blue(),
            file = None, fileURL = None, thumbnailUrl = 'http://thumb', deleteAfter = 5
        )
        kwargs = context.send.call_args.kwargs
        embed: nextcord.Embed = kwargs['embed']
        self.assertEqual(embed.description, 'desc')
        self.assertEqual(embed.thumbnail.url, 'http://thumb')
        self.assertEqual(kwargs['delete_after'], 5)
        self.assertNotIn('file', kwargs)

    async def test_sendDiscordEmbed_file_only(self):
        context = Mock()
        context.send = AsyncMock()
        file_mock = Mock(spec = nextcord.File)
        file_mock.filename = 'pic.png'
        await utils.sendDiscordEmbed(
            context, 'T', None, nextcord.Color.blue(),
            file = file_mock, fileURL = None
        )
        kwargs = context.send.call_args.kwargs
        embed: nextcord.Embed = kwargs['embed']
        self.assertEqual(embed.image.url, 'attachment://pic.png')
        self.assertIs(kwargs['file'], file_mock)

    async def test_sendDiscordEmbed_fileURL_only(self):
        context = Mock()
        context.send = AsyncMock()
        await utils.sendDiscordEmbed(
            context, 'T', None, nextcord.Color.blue(),
            file = None, fileURL = 'http://img'
        )
        kwargs = context.send.call_args.kwargs
        embed: nextcord.Embed = kwargs['embed']
        self.assertEqual(embed.image.url, 'http://img')
        self.assertNotIn('file', kwargs)

    async def test_sendDiscordEmbed_file_and_fileURL_resets_file(self):
        context = Mock()
        context.send = AsyncMock()
        file_mock = Mock(spec = nextcord.File)
        file_mock.filename = 'pic.png'
        await utils.sendDiscordEmbed(
            context, 'T', None, nextcord.Color.blue(),
            file = file_mock, fileURL = 'http://img'
        )
        kwargs = context.send.call_args.kwargs
        self.assertNotIn('file', kwargs)

    async def test_sendDiscordEmbed_file_with_deleteAfter(self):
        context = Mock()
        context.send = AsyncMock()
        file_mock = Mock(spec = nextcord.File)
        file_mock.filename = 'pic.png'
        await utils.sendDiscordEmbed(
            context, 'T', None, nextcord.Color.blue(),
            file = file_mock, deleteAfter = 7
        )
        kwargs = context.send.call_args.kwargs
        self.assertIs(kwargs['file'], file_mock)
        self.assertEqual(kwargs['delete_after'], 7)

    # endregion

    # region sendMessageToAdmins

    async def test_sendMessageToAdmins_success(self):
        config_queries.getServerValue = MagicMock(return_value = '101')
        channel = Mock()
        channel.send = AsyncMock()
        client = Mock()
        client.fetch_channel = AsyncMock(return_value = channel)
        logger = Mock(spec = logging.Logger)
        result = await utils.sendMessageToAdmins(client, '999', 'hello', logger)
        self.assertTrue(result)
        channel.send.assert_awaited_once_with('hello')

    async def test_sendMessageToAdmins_fetch_returns_none(self):
        # channelId is non-None so int() succeeds, but fetch_channel returns None
        # → hits the else branch returning False (no exception).
        config_queries.getServerValue = MagicMock(return_value = '101')
        client = Mock()
        client.fetch_channel = AsyncMock(return_value = None)
        logger = Mock(spec = logging.Logger)
        result = await utils.sendMessageToAdmins(client, '999', 'hello', logger)
        self.assertFalse(result)
        logger.error.assert_not_called()

    async def test_sendMessageToAdmins_channel_not_configured(self):
        config_queries.getServerValue = MagicMock(return_value = None)
        client = Mock()
        # fetch_channel(int(None)) raises TypeError → caught by bare except
        client.fetch_channel = AsyncMock(side_effect = TypeError('int() argument'))
        logger = Mock(spec = logging.Logger)
        result = await utils.sendMessageToAdmins(client, '999', 'hello', logger)
        self.assertFalse(result)
        logger.error.assert_called_once()

    async def test_sendMessageToAdmins_fetch_raises(self):
        config_queries.getServerValue = MagicMock(return_value = '101')
        client = Mock()
        client.fetch_channel = AsyncMock(side_effect = RuntimeError('boom'))
        logger = Mock(spec = logging.Logger)
        result = await utils.sendMessageToAdmins(client, '999', 'hello', logger)
        self.assertFalse(result)
        logger.error.assert_called_once()

    # endregion

    # region purgePreviousMessages (<=100 path only; >100 deferred per plan)

    async def test_purgePreviousMessages_all_valid_under_100(self):
        channel = Mock()
        channel.id = 1
        channel.delete_messages = AsyncMock()

        messages = []
        for i in range(5):
            m = Mock(spec = nextcord.Message)
            m.channel = Mock()
            m.channel.id = 1
            m.delete = AsyncMock()
            messages.append(m)

        await utils.purgePreviousMessages(messages, channel)
        channel.delete_messages.assert_awaited_once_with(messages)

    async def test_purgePreviousMessages_filters_partial_interaction_and_wrong_channel(self):
        channel = Mock()
        channel.id = 1
        channel.delete_messages = AsyncMock()

        valid = Mock(spec = nextcord.Message)
        valid.channel = Mock()
        valid.channel.id = 1
        valid.delete = AsyncMock()

        partial = Mock(spec = nextcord.PartialInteractionMessage)
        partial.channel = Mock()
        partial.channel.id = 1
        partial.delete = AsyncMock()

        wrong_channel = Mock(spec = nextcord.Message)
        wrong_channel.channel = Mock()
        wrong_channel.channel.id = 99
        wrong_channel.delete = AsyncMock()

        messages = [valid, partial, wrong_channel]
        await utils.purgePreviousMessages(messages, channel)

        partial.delete.assert_awaited_once()
        wrong_channel.delete.assert_awaited_once()
        valid.delete.assert_not_awaited()
        channel.delete_messages.assert_awaited_once_with([valid])

    async def test_purgePreviousMessages_over_100_chunks(self):
        channel = Mock()
        channel.id = 1
        channel.delete_messages = AsyncMock()

        messages = []
        for i in range(105):
            m = Mock(spec = nextcord.Message)
            m.channel = Mock()
            m.channel.id = 1
            m.delete = AsyncMock()
            messages.append(m)

        await utils.purgePreviousMessages(messages, channel)
        # first chunk of 100 deleted, then remaining 5
        self.assertEqual(channel.delete_messages.call_count, 2)
        self.assertEqual(len(channel.delete_messages.call_args_list[0][0][0]), 100)
        self.assertEqual(len(channel.delete_messages.call_args_list[1][0][0]), 5)

    # endregion

    # region removeRoleFromAllUsers

    async def test_removeRoleFromAllUsers_empty_guild(self):
        role = Mock()
        guild = Mock()
        guild.fetch_members = MagicMock(return_value = AsyncIter([]))
        self.assertTrue(await utils.removeRoleFromAllUsers(guild, role))

    async def test_removeRoleFromAllUsers_success(self):
        role = Mock()
        with_role = Mock()
        with_role.roles = [role]
        with_role.remove_roles = AsyncMock()
        without_role = Mock()
        without_role.roles = []
        without_role.remove_roles = AsyncMock()
        guild = Mock()
        guild.fetch_members = MagicMock(return_value = AsyncIter([with_role, without_role]))
        result = await utils.removeRoleFromAllUsers(guild, role)
        self.assertTrue(result)
        with_role.remove_roles.assert_awaited_once_with(role)
        without_role.remove_roles.assert_not_awaited()

    async def test_removeRoleFromAllUsers_exception_returns_false(self):
        role = Mock()
        guild = Mock()
        guild.fetch_members = MagicMock(side_effect = RuntimeError('boom'))
        result = await utils.removeRoleFromAllUsers(guild, role)
        self.assertFalse(result)

    # endregion

    # region addRoleToUser

    async def test_addRoleToUser_success(self):
        user = Mock()
        user.add_roles = AsyncMock()
        role = Mock()
        result = await utils.addRoleToUser(user, role)
        self.assertTrue(result)
        user.add_roles.assert_awaited_once_with(role)

    async def test_addRoleToUser_exception_returns_false(self):
        user = Mock()
        user.add_roles = AsyncMock(side_effect = RuntimeError('boom'))
        role = Mock()
        result = await utils.addRoleToUser(user, role)
        self.assertFalse(result)

    # endregion

    # region createTempTableImage / deleteTempTableImage

    def test_createTempTableImage(self):
        fig_sentinel = object()
        with patch.object(utils.df2img, 'plot_dataframe', return_value = fig_sentinel) as mock_plot, \
             patch.object(utils.df2img, 'save_dataframe') as mock_save:
            utils.createTempTableImage(
                'out.png',
                [{'A': 1, 'B': 2}, {'A': 3, 'B': 4}],
                ['A', 'B'],
                [100, 100],
                'My Title',
                'white',
                'blue',
            )
        mock_save.assert_called_once_with(fig = fig_sentinel, filename = 'out.png')
        args, kwargs = mock_plot.call_args
        df_arg = args[0]
        self.assertEqual(df_arg.index.name, 'A')
        self.assertEqual(list(df_arg['B']), [2, 4])
        self.assertEqual(kwargs['title']['text'], 'My Title')
        self.assertEqual(kwargs['tbl_header']['font_color'], 'white')
        self.assertEqual(kwargs['tbl_header']['fill_color'], 'blue')
        self.assertEqual(kwargs['col_width'], [100, 100])

    def test_deleteTempTableImage_exists(self):
        with patch.object(utils.os.path, 'exists', return_value = True) as mock_exists, \
             patch.object(utils.os, 'remove') as mock_remove:
            self.assertTrue(utils.deleteTempTableImage('out.png'))
            mock_exists.assert_called_once_with('out.png')
            mock_remove.assert_called_once_with('out.png')

    def test_deleteTempTableImage_missing(self):
        with patch.object(utils.os.path, 'exists', return_value = False) as mock_exists, \
             patch.object(utils.os, 'remove') as mock_remove:
            self.assertFalse(utils.deleteTempTableImage('out.png'))
            mock_exists.assert_called_once_with('out.png')
            mock_remove.assert_not_called()

    # endregion
