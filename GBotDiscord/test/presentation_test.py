#region IMPORTS
import inspect
import unittest
from decimal import Decimal, InvalidOperation
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import nextcord
from nextcord.ext.commands import BadArgument, CommandNotFound, MissingRequiredArgument
from nextcord.ext.commands.context import Context
from nextcord.ext.commands.errors import ArgumentParsingError, CommandInvokeError, CommandOnCooldown
from nextcord.ext.commands.cooldowns import BucketType, Cooldown

from GBotDiscord.src import presentation
from GBotDiscord.src.exceptions import CustomCommandOnCooldown, FeatureNotEnabledForGuild, LegacyPrefixCommandsNotEnabledForGuild, MessageAuthorNotAdmin, MessageNotSentFromGuild, MessageNotSentFromPrivateMessage, NotAPatron, NotSentFromPatreonGuild, NotSubscribed, AccessEnded
from GBotDiscord.src.properties import GBotPropertiesManager
#endregion

# to run this test suite:
#   - execute the following command from the GBot directory: python -m unittest GBotDiscord/test/presentation_test.py
#   - or use the "Python: Current File" run configuration to run presentation_test.py
#   - or use the "Python: Current File" run configuration to run tests.py to run all test suites
class TestPresentation(unittest.IsolatedAsyncioTestCase):

    @classmethod
    def setUpClass(self):
        print('\nExecuting presentation unit tests...\n')

    @classmethod
    def tearDownClass(self):
        print('\n\nCompleted presentation unit tests.\n')

    def setUp(self):
        GBotPropertiesManager.GBOT_VERSION = '8.0'
        GBotPropertiesManager.PATREON_URL = 'https://patreon.example'
        self.mention = '<@1>'
        self.author = Mock()
        self.author.mention = self.mention
        self.author.send = AsyncMock()
        self.command = Mock()
        self.command.qualified_name = 'config toggle'
        self.command.signature = '<feature_type>'
        self.ctx = Mock(spec = Context)
        self.ctx.send = AsyncMock()
        self.ctx.clean_prefix = '.'
        self.interaction = Mock(spec = nextcord.Interaction)
        self.interaction.send = AsyncMock()

    def _missing(self):
        parameter = Mock(spec = inspect.Parameter)
        parameter.name = 'feature_type'
        return MissingRequiredArgument(parameter)

    #region embeds
    def test_footer_carries_the_version_and_feature(self):
        self.assertEqual(presentation.footerText(), 'GBot 8.0')
        self.assertEqual(presentation.footerText('Music'), 'GBot 8.0 • Music')

    def test_each_embed_has_its_colour_and_footer(self):
        for builder, color in ((presentation.brandEmbed, presentation.BRAND_COLOR),
                               (presentation.errorEmbed, presentation.ERROR_COLOR),
                               (presentation.warningEmbed, presentation.WARNING_COLOR)):
            with self.subTest(builder = builder.__name__):
                embed = builder(title = 'T', description = 'D', feature = 'Music')
                self.assertEqual(embed.color, color)
                self.assertEqual(embed.title, 'T')
                self.assertEqual(embed.description, 'D')
                self.assertEqual(embed.footer.text, 'GBot 8.0 • Music')

    def test_embed_leaves_out_what_it_was_not_given(self):
        embed = presentation.errorEmbed()
        self.assertIsNone(embed.title)
        self.assertIsNone(embed.description)
        self.assertEqual(embed.footer.text, 'GBot 8.0')

    def test_builders_are_keyword_only(self):
        # the positional signature of utils.sendDiscordEmbed is what forced None, None, None (P-3)
        with self.assertRaises(TypeError):
            presentation.brandEmbed('title')
    #endregion

    #region sendReply
    async def test_sendReply_passes_ephemeral_to_a_slash_reply(self):
        embed = presentation.errorEmbed(description = 'x')
        await presentation.sendReply(self.interaction, embed = embed, ephemeral = True)
        self.interaction.send.assert_awaited_once_with(embed = embed, ephemeral = True)

    async def test_sendReply_never_passes_ephemeral_to_a_prefix_reply(self):
        # Context.send has no ephemeral option, and passing one raises
        embed = presentation.errorEmbed(description = 'x')
        await presentation.sendReply(self.ctx, embed = embed, ephemeral = True)
        self.ctx.send.assert_awaited_once_with(embed = embed)

    async def test_sendReply_plain_text(self):
        await presentation.sendReply(self.ctx, content = '⏸️ Paused.')
        self.ctx.send.assert_awaited_once_with(content = '⏸️ Paused.')
        await presentation.sendReply(self.interaction, content = '⏸️ Paused.')
        self.interaction.send.assert_awaited_once_with(content = '⏸️ Paused.', ephemeral = False)
    #endregion

    #region describeCommandError
    def test_every_handled_error_keeps_its_message(self):
        with patch('GBotDiscord.src.presentation.utils.calculateTimeLeftStr', return_value = '5 seconds'):
            custom = CustomCommandOnCooldown(5, False, 'to play again.')
            plain = CustomCommandOnCooldown(5, False, None)
            cases = [
                (CommandOnCooldown(Cooldown(1, 5), 5, BucketType.user), 'please wait 5 seconds to execute this command again.'),
                (custom, 'please wait 5 seconds to play again.'),
                (plain, 'please wait 5 seconds to execute this command again.'),
                (MessageAuthorNotAdmin('x'), 'you need to be an admin to execute this command.'),
                (MessageNotSentFromGuild('x'), 'this command needs to be executed in a server.'),
                (MessageNotSentFromPrivateMessage('x'), 'this command needs to be executed in a private message.'),
                (FeatureNotEnabledForGuild('x', 'Music'), 'Music is turned off in this server. An admin can turn it on in `/config`.'),
                (NotSentFromPatreonGuild('x'), 'this command only works in the GBot Patreon server.'),
                (NotAPatron('x'), 'you need to be a GBot Patron to execute this command.'),
                (NotSubscribed('x'), 'you do not have access to GBot. Please subscribe here: https://patreon.example'),
                (AccessEnded('x', 77, lapsed = True), "This server's GBot subscription has ended. To keep GBot, renew on Patreon, or have someone else subscribe and run `/patreon` with this server's ID, `77`, in the GBot Patreon server."),
                (AccessEnded('x', 77), "GBot's free trial in this server has ended. To keep GBot, subscribe on Patreon, then run `/patreon` with this server's ID, `77`, in the GBot Patreon server."),
            ]
            for error, expected in cases:
                with self.subTest(error = type(error).__name__):
                    self.assertEqual(presentation.describeCommandError(error, self.mention), f'Sorry {self.mention}, {expected}')

    # Deliberate silence: a disabled prefix command says nothing, and neither does a stray ".5" typo.
    def test_silent_errors_stay_silent(self):
        for error in (LegacyPrefixCommandsNotEnabledForGuild('x'), CommandNotFound('x'), ValueError('x')):
            with self.subTest(error = type(error).__name__):
                self.assertIsNone(presentation.describeCommandError(error, self.mention, self.ctx, self.command))

    # P-7: these used to get no reply at all
    def test_missing_prefix_argument_says_what_is_missing_and_the_usage(self):
        message = presentation.describeCommandError(self._missing(), self.mention, self.ctx, self.command)
        self.assertEqual(message, f'Sorry {self.mention}, that command is missing `feature_type`. Usage: `.config toggle <feature_type>`')

    def test_bad_prefix_argument_says_why_and_the_usage(self):
        message = presentation.describeCommandError(BadArgument('position must be a number'), self.mention, self.ctx, self.command)
        self.assertEqual(message, f'Sorry {self.mention}, you provided an invalid argument: position must be a number Usage: `.config toggle <feature_type>`')

    def test_parsing_error_is_still_reported(self):
        message = presentation.describeCommandError(ArgumentParsingError('bad quote'), self.mention, self.ctx, self.command)
        self.assertIn('you provided an invalid argument: bad quote', message)

    # /config toggle raises BadArgument too, where a prefix usage line would make no sense
    def test_bad_slash_argument_has_no_prefix_usage(self):
        message = presentation.describeCommandError(BadArgument('nope'), self.mention, self.interaction, self.command)
        self.assertEqual(message, f'Sorry {self.mention}, you provided an invalid argument: nope')

    def test_usage_of_a_command_with_no_arguments_has_no_trailing_space(self):
        self.command.signature = ''
        self.assertEqual(presentation.usageText(self.ctx, self.command), '.config toggle')
    #endregion

    #region sendError and sendEmbed
    async def test_sendError_is_private_on_slash_by_default(self):
        await presentation.sendError(self.interaction, 'nope', feature = 'Music')
        kwargs = self.interaction.send.await_args.kwargs
        self.assertTrue(kwargs['ephemeral'])
        self.assertEqual(kwargs['embed'].color, presentation.ERROR_COLOR)
        self.assertEqual(kwargs['embed'].footer.text, 'GBot 8.0 • Music')

    # Storms deletes its messages later, and nobody can delete a private reply
    async def test_sendError_can_stay_public_and_returns_the_message(self):
        self.interaction.send.return_value = 'sent'
        self.assertEqual(await presentation.sendError(self.interaction, 'nope', ephemeral = False), 'sent')
        self.assertFalse(self.interaction.send.await_args.kwargs['ephemeral'])

    async def test_sendEmbed_with_and_without_a_thumbnail(self):
        channel = Mock()
        channel.send = AsyncMock(return_value = 'sent')
        self.assertEqual(await presentation.sendEmbed(channel, title = 'Storm', description = 'D', feature = 'Storms'), 'sent')
        embed = channel.send.await_args.kwargs['embed']
        self.assertEqual((embed.title, embed.color), ('Storm', presentation.BRAND_COLOR))
        self.assertIsNone(embed.thumbnail.url)
        await presentation.sendEmbed(channel, title = 'Storm', thumbnailUrl = 'https://x/y.png')
        self.assertEqual(channel.send.await_args.kwargs['embed'].thumbnail.url, 'https://x/y.png')
    #endregion

    #region deferIfSlash
    def test_repeated_text_cannot_ping_a_server_or_role(self):
        # the payload rather than the attributes: leaving users out adds 'roles' back to it
        self.assertEqual(presentation.ALLOWED_MENTIONS.to_dict(), {'parse': ['users'], 'replied_user': True})

    async def test_deferIfSlash_only_defers_an_interaction(self):
        self.interaction.response = Mock(defer = AsyncMock())
        await presentation.deferIfSlash(self.interaction)
        self.interaction.response.defer.assert_awaited_once_with(ephemeral = False)
        # a prefix context has nothing to defer, and no response attribute to fail on
        await presentation.deferIfSlash(self.ctx)
    #endregion

    #region formatGCoin
    def test_formatGCoin(self):
        for amount, expected in ((Decimal('1250'), '1,250.00'), ('1000000.5', '1,000,000.50'), (5, '5.00'), ('0.25', '0.25'), ('-10.00', '-10.00'), ('+0.50', '+0.50')):
            with self.subTest(amount = amount):
                self.assertEqual(presentation.formatGCoin(amount), expected)
    #endregion

    #region parseGCoin
    # GBot shows amounts with commas, so they get typed and pasted back that way
    def test_parseGCoin_accepts_commas_and_spaces(self):
        for text, expected in (('315,175,436,909.41', '315175436909.41'), ('1,000', '1000'), (' 5.5 ', '5.5'), (10, '10'), (Decimal('2.50'), '2.50')):
            with self.subTest(text = text):
                self.assertEqual(presentation.parseGCoin(text), Decimal(expected))

    def test_parseGCoin_rejects_what_is_not_an_amount(self):
        for text in ('abc', '', 'NaN', 'Infinity', '-Infinity', 'sNaN'):
            with self.subTest(text = text):
                with self.assertRaises(InvalidOperation):
                    presentation.parseGCoin(text)
    #endregion

    #region sendWelcome
    def _channel(self, canSend = True, canEmbed = True):
        channel = Mock()
        channel.send = AsyncMock()
        channel.permissions_for = Mock(return_value = Mock(send_messages = canSend, embed_links = canEmbed))
        return channel

    async def test_sendWelcome_lists_the_features_like_help(self):
        channel = Mock(send = AsyncMock())
        channel.permissions_for.return_value = Mock(send_messages = True, embed_links = True)
        await presentation.sendWelcome(Mock(system_channel = channel, text_channels = []))
        embed = channel.send.call_args.kwargs['embed']
        self.assertEqual(embed.title, '👋 Thanks for adding GBot!')
        self.assertEqual(embed.fields[0].value, '🤖 Agent\n💰 GCoin\n🏪 GTrade\n↩️ Hype\n🎵 Music\n🌧️ Storms\n❓ Who Dis')

    async def test_sendWelcome_prefers_the_system_channel(self):
        system = self._channel()
        other = self._channel()
        await presentation.sendWelcome(Mock(system_channel = system, text_channels = [other]))
        self.assertIn('`/config`', system.send.await_args.kwargs['embed'].description)
        self.assertIn('`/help`', system.send.await_args.kwargs['embed'].description)
        other.send.assert_not_awaited()

    async def test_sendWelcome_falls_back_to_the_first_channel_it_can_post_in(self):
        noSend = self._channel(canSend = False)
        noEmbed = self._channel(canEmbed = False)
        usable = self._channel()
        await presentation.sendWelcome(Mock(system_channel = None, text_channels = [noSend, noEmbed, usable]))
        usable.send.assert_awaited_once()
        noSend.send.assert_not_awaited()
        noEmbed.send.assert_not_awaited()

    async def test_sendWelcome_stays_quiet_with_nowhere_to_post(self):
        channel = self._channel(canSend = False)
        await presentation.sendWelcome(Mock(system_channel = channel, text_channels = [channel]))
        channel.send.assert_not_awaited()

    async def test_sendWelcome_on_a_trial_says_when_it_ends_with_the_patreon_button(self):
        from datetime import datetime, timezone
        GBotPropertiesManager.TRIAL_DAYS = 7
        channel = self._channel()
        ends = datetime(2026, 11, 16, tzinfo = timezone.utc)
        await presentation.sendWelcome(Mock(id = 5, system_channel = channel, text_channels = []), ends)
        kwargs = channel.send.await_args.kwargs
        trial = kwargs['embed'].fields[1]
        self.assertEqual(trial.name, '🎁 Free for 7 days')
        self.assertTrue(trial.value.startswith(f'Everything works until <t:{int(ends.timestamp())}:F>. To keep GBot'))
        self.assertIn('`5`', trial.value)
        self.assertEqual(kwargs['view'].children[0].url, 'https://patreon.example')

    async def test_sendWelcome_without_a_trial_has_no_trial_or_button(self):
        channel = self._channel()
        await presentation.sendWelcome(Mock(system_channel = channel, text_channels = []))
        kwargs = channel.send.await_args.kwargs
        self.assertEqual(len(kwargs['embed'].fields), 1)
        self.assertIsNone(kwargs['view'])

    def test_postableChannel_is_where_the_welcome_goes_or_none(self):
        usable = self._channel()
        self.assertIs(presentation.postableChannel(Mock(system_channel = None, text_channels = [self._channel(canSend = False), usable])), usable)
        self.assertIsNone(presentation.postableChannel(Mock(system_channel = None, text_channels = [])))

    async def test_subscribeView_is_a_patreon_link_that_outlives_a_restart(self):
        view = presentation.subscribeView()
        self.assertIsNone(view.timeout)
        button = view.children[0]
        self.assertEqual((button.style, button.label, str(button.emoji), button.url), (nextcord.ButtonStyle.link, 'Subscribe on Patreon', '💳', 'https://patreon.example'))

    # joining a server must never fail over a greeting
    async def test_sendWelcome_logs_a_failure_rather_than_raising(self):
        channel = self._channel()
        channel.send = AsyncMock(side_effect = Exception('Missing Access'))
        with patch('GBotDiscord.src.presentation.logging.getLogger') as getLogger:
            await presentation.sendWelcome(Mock(id = 5, system_channel = channel, text_channels = []))
        getLogger.return_value.error.assert_called_once()
    #endregion

    #region sendCommandError
    async def test_sendCommandError_is_a_private_red_card_on_slash(self):
        await presentation.sendCommandError(self.interaction, self.author, self.command, MessageAuthorNotAdmin('x'))
        kwargs = self.interaction.send.await_args.kwargs
        self.assertTrue(kwargs['ephemeral'])
        self.assertEqual(kwargs['embed'].color, presentation.ERROR_COLOR)
        self.assertIn('admin', kwargs['embed'].description)

    async def test_sendCommandError_is_public_on_prefix(self):
        await presentation.sendCommandError(self.ctx, self.author, self.command, MessageAuthorNotAdmin('x'))
        self.assertNotIn('ephemeral', self.ctx.send.await_args.kwargs)

    async def test_sendCommandError_unwraps_a_slash_invoke_error(self):
        wrapped = nextcord.ApplicationInvokeError(BadArgument('nope'))
        await presentation.sendCommandError(self.interaction, self.author, self.command, wrapped)
        self.assertIn('nope', self.interaction.send.await_args.kwargs['embed'].description)

    # bet with an unparsable amount used to crash into Discord's "application did not respond"
    async def test_sendCommandError_invalid_amount_says_so(self):
        await presentation.sendCommandError(self.interaction, self.author, self.command, nextcord.ApplicationInvokeError(InvalidOperation()))
        self.assertIn('please enter a valid amount', self.interaction.send.await_args.kwargs['embed'].description)

    async def test_sendCommandError_unexpected_crash_is_a_private_generic_card(self):
        await presentation.sendCommandError(self.interaction, self.author, self.command, nextcord.ApplicationInvokeError(KeyError('secret detail')))
        kwargs = self.interaction.send.await_args.kwargs
        self.assertTrue(kwargs['ephemeral'])
        self.assertIn('something went wrong', kwargs['embed'].description)
        self.assertNotIn('secret detail', kwargs['embed'].description)

    async def test_sendCommandError_prefix_crash_also_gets_a_reply(self):
        await presentation.sendCommandError(self.ctx, self.author, self.command, CommandInvokeError(KeyError('x')))
        self.assertIn('something went wrong', self.ctx.send.await_args.kwargs['embed'].description)

    async def test_sendCommandError_silent_error_sends_nothing(self):
        await presentation.sendCommandError(self.ctx, self.author, self.command, LegacyPrefixCommandsNotEnabledForGuild('x'))
        self.ctx.send.assert_not_awaited()
        self.author.send.assert_not_awaited()

    async def test_sendCommandError_private_cooldown_goes_to_the_author(self):
        error = CustomCommandOnCooldown(5, True, None)
        with patch('GBotDiscord.src.presentation.utils.calculateTimeLeftStr', return_value = '5 seconds'):
            await presentation.sendCommandError(self.ctx, self.author, self.command, error)
        self.author.send.assert_awaited_once()
        self.ctx.send.assert_not_awaited()

    async def test_sendCommandError_private_cooldown_on_slash_is_a_private_reply(self):
        error = CustomCommandOnCooldown(5, True, None)
        with patch('GBotDiscord.src.presentation.utils.calculateTimeLeftStr', return_value = '5 seconds'):
            await presentation.sendCommandError(self.interaction, self.author, self.command, error)
        self.assertTrue(self.interaction.send.await_args.kwargs['ephemeral'])
        self.author.send.assert_not_awaited()

    async def test_sendCommandError_public_cooldown_replies_in_place(self):
        error = CustomCommandOnCooldown(5, False, None)
        with patch('GBotDiscord.src.presentation.utils.calculateTimeLeftStr', return_value = '5 seconds'):
            await presentation.sendCommandError(self.ctx, self.author, self.command, error)
        self.ctx.send.assert_awaited_once()
        self.author.send.assert_not_awaited()
    #endregion

    async def test_a_refusal_to_subscribe_carries_the_patreon_button(self):
        await presentation.sendCommandError(self.interaction, self.author, self.command, AccessEnded('x', 77))
        self.assertEqual(self.interaction.send.await_args.kwargs['view'].children[0].url, 'https://patreon.example')
        await presentation.sendInteractionError(self.interaction, NotSubscribed('x'))
        self.assertEqual(self.interaction.send.await_args.kwargs['view'].children[0].url, 'https://patreon.example')
        # and nothing else does
        await presentation.sendCommandError(self.interaction, self.author, self.command, MessageAuthorNotAdmin('x'))
        self.assertNotIn('view', self.interaction.send.await_args.kwargs)

    #region sendInteractionError
    async def test_sendInteractionError_reads_like_the_command_would(self):
        await presentation.sendInteractionError(self.interaction, MessageAuthorNotAdmin('x'))
        kwargs = self.interaction.send.await_args.kwargs
        self.assertTrue(kwargs['ephemeral'])
        self.assertIn('admin', kwargs['embed'].description)

    async def test_sendInteractionError_logs_and_answers_a_crash(self):
        with patch('GBotDiscord.src.presentation.logging.getLogger') as getLogger:
            await presentation.sendInteractionError(self.interaction, KeyError('secret'))
        getLogger.return_value.error.assert_called_once()
        description = self.interaction.send.await_args.kwargs['embed'].description
        self.assertIn('something went wrong', description)
        self.assertNotIn('secret', description)
        # an interaction that has expired can't be answered, which is no reason to fail again
        self.interaction.send.side_effect = nextcord.HTTPException(Mock(status = 404, reason = 'gone'), 'gone')
        await presentation.sendInteractionError(self.interaction, MessageAuthorNotAdmin('x'))
    #endregion
