#region IMPORTS
from GBotDiscord.src.exceptions import MessageAuthorNotAdmin
import asyncio
import threading
import unittest
from unittest.mock import patch, MagicMock, Mock, AsyncMock
import nextcord
from nextcord.ext import commands
from nextcord.ext.commands.context import Context

from GBotDiscord.src import pagination
from GBotDiscord.test import isolation
from GBotDiscord.src import utils
from GBotDiscord.src.config import config_queries
from GBotDiscord.src.hype import hype_queries
from GBotDiscord.src.hype.hype_cog import Hype, HypeModal
from GBotDiscord.src.properties import GBotPropertiesManager
from GBotDiscord.src.firebase import GBotFirebaseService
from GBotDiscord.test.card_assertions import assertErrorCard
from GBotDiscord.src import presentation
#endregion

# to run this test suite:
#   - execute the following command from the GBot directory: python -m unittest GBotDiscord/test/hype/hype_test.py
#   - or use the "Python: Current File" run configuration to run hype_test.py
#   - or use the "Python: Current File" run configuration to run tests.py to run all test suites
class TestHype(unittest.IsolatedAsyncioTestCase):

    @classmethod
    def setUpClass(self):
        print('\nExecuting hype unit tests...\n')

    @classmethod
    def tearDownClass(self):
        print('\n\nCompleted hype unit tests.\n')

    def setUp(self):
        async def recheck(interaction, feature = None, admin = False):
            if admin and not utils.isUserAdminOrOwner(interaction.user, interaction.guild):
                raise MessageAuthorNotAdmin('x')
        patcher = patch('GBotDiscord.src.hype.hype_cog.predicates.recheck', recheck)
        patcher.start()
        self.addCleanup(patcher.stop)
        # a subscribed server, unless a test says otherwise
        active = patch('GBotDiscord.src.hype.hype_cog.access.isActive', MagicMock(return_value = True))
        self.isActive = active.start()
        self.addCleanup(active.stop)
        isolation.restorePagination()
        GBotPropertiesManager.USER_RESPONSE_TIMEOUT_SECONDS = 300

        self.author = Mock()
        self.author.id = 54321
        self.author.bot = False
        self.author.name = "author name"
        self.author.mention = "<@!012345678910111213>"

        self.icon = Mock()
        self.icon.url = "icon url"

        self.guild: nextcord.Guild = Mock()
        self.guild.id = 10
        self.guild.icon = self.icon

        self.message1 = Mock()
        self.message1.content = "Let's goooo!!!"
        self.message1.guild = self.guild
        self.message1.author = self.author
        self.message1.add_reaction = AsyncMock()
        self.message1.reply = AsyncMock()

        config_queries.getServerValue = MagicMock(return_value = '.')
        hype_queries.getAllServerMatches = MagicMock(return_value = {
            "match1": {
                "regex": r"((.|\n)*)([Ll]+[Ee]+[Tt]+[']?[Ss]+[\s]+[Gg]+[Oo]+)((.|\n)*)",
                "responses": [
                    "Woohoo!"
                ],
                "isReaction": False
            },
            "match2": {
                "regex": r"((.|\n)*)([Ll]+[Ee]+[Tt]+[']?[Ss]+[\s]+[Gg]+[Oo]+)((.|\n)*)",
                "responses": [
                    "👍"
                ],
                "isReaction": True
            },
        })

        self.ctx: Context = Mock()
        self.ctx.guild = self.guild
        self.ctx.author = self.author

        self.interaction: nextcord.Interaction = Mock()
        self.interaction.guild = self.guild
        self.interaction.user = self.author

        self.client: nextcord.Client = commands.Bot()
        self.hype: Hype = Hype(self.client)

    async def test_on_message_private_message(self):
        self.message1.guild = None
        await self.hype.on_message(self.message1)
        self.message1.add_reaction.assert_not_called()
        self.message1.reply.assert_not_called()

    async def test_on_message_bot(self):
        self.message1.author.bot = True
        await self.hype.on_message(self.message1)
        self.message1.add_reaction.assert_not_called()
        self.message1.reply.assert_not_called()

    async def test_on_message_command(self):
        self.message1.content = ".unmatch"
        await self.hype.on_message(self.message1)
        self.message1.add_reaction.assert_not_called()
        self.message1.reply.assert_not_called()

    async def test_on_message_without_match(self):
        self.message1.content = "Hello world!"
        await self.hype.on_message(self.message1)
        self.message1.add_reaction.assert_not_called()
        self.message1.reply.assert_not_called()

    async def test_on_message_lookups_run_off_the_event_loop(self):
        # this runs on every message in every server
        threads = []
        def record(result):
            def lookup(*args):
                threads.append(threading.current_thread())
                return result
            return lookup
        hype_queries.getAllServerMatches = MagicMock(side_effect = record({"match1": {"regex": "nomatch", "responses": ["x"], "isReaction": False}}))
        config_queries.getServerValue = MagicMock(side_effect = record(True))
        with patch('GBotDiscord.src.hype.hype_cog.utils.getServerPrefixOrDefault', new = record('.')):
            await self.hype.on_message(self.message1)
        self.assertEqual(len(threads), 3)
        self.assertTrue(all(thread is not threading.main_thread() for thread in threads))

    async def test_on_message_stops_a_pattern_that_takes_too_long(self):
        # the real library: nested repeats that re would still be running in hours from now
        self.hype.logger = MagicMock()
        self.hype.MATCH_TIMEOUT_SECONDS = 0.05
        hype_queries.getAllServerMatches = MagicMock(return_value = {
            "slow": {"regex": r"(x+x+)+y", "responses": ["never"], "isReaction": False},
            "fine": {"regex": ".*", "responses": ["Woohoo!"], "isReaction": False}
        })
        self.message1.content = "x" * 5000
        await asyncio.wait_for(self.hype.on_message(self.message1), timeout = 10)
        self.hype.logger.error.assert_called_once()
        self.assertIn('took too long', self.hype.logger.error.call_args.args[0])
        self.message1.reply.assert_called_once_with("Woohoo!")

    async def test_on_message_feature_disabled(self):
        # "All Hype functionality has been disabled" has to include the replies themselves
        config_queries.getServerValue = MagicMock(side_effect = lambda serverId, item: False if item == 'toggle_hype' else '.')
        await self.hype.on_message(self.message1)
        self.message1.add_reaction.assert_not_called()
        self.message1.reply.assert_not_called()

    async def test_on_message_stays_quiet_in_a_server_that_is_not_subscribed(self):
        hype_queries.getAllServerMatches = MagicMock(return_value = {"match1": {"regex": ".*", "responses": ["Woohoo!"], "isReaction": False}})
        self.isActive.return_value = False
        await self.hype.on_message(self.message1)
        self.isActive.assert_called_once_with(self.message1.guild.id)
        self.message1.reply.assert_not_called()

    async def test_on_message_match_saved_without_responses(self):
        # the database doesn't store an empty list, so the key is missing altogether
        hype_queries.getAllServerMatches = MagicMock(return_value = {"match1": {"regex": ".*", "isReaction": False}})
        await self.hype.on_message(self.message1)
        self.message1.reply.assert_not_called()

    def test_responses_cannot_format_the_rest_of_the_list(self):
        # the real match that broke the list: the * in this reply italicised the next match's pattern
        self.assertEqual(self.hype.describeResponses(['LETS F*CKING GOOOO!', 'a_b `c`']), 'LETS F\\*CKING GOOOO!, a\\_b \\`c\\`')

    def test_responses_keep_custom_emoji_and_links_working(self):
        url = 'https://media.giphy.com/media/a_b_c/giphy.gif'
        self.assertEqual(self.hype.describeResponse(url), url)
        self.assertEqual(self.hype.describeResponse('<:my_emoji:123>'), '<:my_emoji:123>')
        self.assertEqual(self.hype.describeResponse('<a:my_emoji:123> *hi*'), '<a:my_emoji:123> \\*hi\\*')

    def test_regex_always_stays_in_one_code_span(self):
        self.assertEqual(self.hype.describeRegex('a*`b`*'), '`a*ˋbˋ*`')
        shown = self.hype.describeRegex('x' * 200)
        self.assertEqual(shown, '`' + 'x' * 150 + '…`')

    def test_long_responses_are_cut_between_responses_and_marked(self):
        self.assertEqual(self.hype.describeResponses(['a' * 150, 'b' * 150]), 'a' * 150 + ', ' + 'b' * 24 + '…')
        self.assertEqual(self.hype.describeResponses(['*' * 500]), '\\*' * 100 + '…')
        self.assertEqual(self.hype.describeResponses([]), 'nothing')

    async def test_remove_can_list_a_match_without_responses_or_a_very_long_one(self):
        # either one failing to display would leave every match in the server impossible to remove
        matches = {
            "match1": {"regex": ".*", "isReaction": False},
            "match2": {"regex": ".*", "responses": ["x" * 3000], "isReaction": True}
        }
        _, lines, choices = self.hype.listMatches(matches)
        self.assertEqual(len(lines), 2)
        self.assertIn('nothing', lines[0])
        # a full page of the longest still has to fit in an embed
        self.assertLessEqual(len(lines[1]) * 10, 4096)
        self.assertEqual(choices[0], {'label': '.*', 'description': 'Replies with nothing', 'emoji': '💬'})
        self.assertEqual(choices[1]['emoji'], '😀')

    async def test_on_message_with_matches(self):
        await self.hype.on_message(self.message1)
        self.message1.reply.assert_called_once_with("Woohoo!")
        self.message1.add_reaction.assert_called_once_with("👍")

    # A-17: an invalid regex could be saved, and then raised re.error on *every* message sent in
    # the server. Matches saved before validation existed must be skipped, not fatal.
    async def test_on_message_skips_stored_invalid_regex(self):
        self.hype.logger = MagicMock()
        hype_queries.getAllServerMatches = MagicMock(return_value = {
            "match1": {
                "regex": "([unclosed",
                "responses": ["Woohoo!"],
                "isReaction": False
            },
            "match2": {
                "regex": r"((.|\n)*)([Ll]+[Ee]+[Tt]+[']?[Ss]+[\s]+[Gg]+[Oo]+)((.|\n)*)",
                "responses": ["Ayyy!"],
                "isReaction": False
            }
        })
        await self.hype.on_message(self.message1)
        # the broken match is skipped and logged; the valid one still responds
        self.hype.logger.error.assert_called_once()
        self.assertIn('([unclosed', self.hype.logger.error.call_args[0][0])
        self.message1.reply.assert_called_once_with("Ayyy!")

    # A-17: random.choice(responses) was evaluated before the match test, so a match with an
    # empty response list raised IndexError on every message in the server.
    async def test_on_message_skips_match_with_no_responses(self):
        hype_queries.getAllServerMatches = MagicMock(return_value = {
            "match1": {
                "regex": r"((.|\n)*)([Ll]+[Ee]+[Tt]+[']?[Ss]+[\s]+[Gg]+[Oo]+)((.|\n)*)",
                "responses": [],
                "isReaction": False
            }
        })
        await self.hype.on_message(self.message1)
        self.message1.reply.assert_not_called()
        self.message1.add_reaction.assert_not_called()

    # A-17: the pattern was never compiled before being stored.
    EXPECTED_REGEX = r"((.|\n)*)([Ll]+[Ee]+[Tt]+[']?[Ss]+[\s]+[Gg]+[Oo]+)((.|\n)*)"

    def twoMatches(self):
        return {
            "match1": {"regex": self.EXPECTED_REGEX, "responses": ["Woohoo!"], "isReaction": False},
            "match2": {"regex": self.EXPECTED_REGEX, "responses": ["👍"], "isReaction": True}
        }

    async def openHype(self, context = None, matches = 'two'):
        context = context or self.ctx
        context.send = AsyncMock()
        stored = self.twoMatches() if matches == 'two' else matches
        with patch.object(hype_queries, 'getAllServerMatches', MagicMock(return_value = stored)), patch.object(pagination, 'startPages', AsyncMock()) as start:
            await self.hype.openCard(context, self.author)
        self.started = start
        return start.await_args.args[1]

    def click(self):
        return Mock(response = Mock(edit_message = AsyncMock(), defer = AsyncMock(), send_modal = AsyncMock()))

    def action(self, picker, label):
        return next(action for action in picker.actions if action.label == label)

    def shown(self, interaction):
        embed = interaction.response.edit_message.await_args.kwargs['embed']
        return ' '.join([embed.description or ''] + [field.value for field in embed.fields])

    async def submit(self, picker, label, pattern, text, index = None, admin = True, stored = None):
        interaction = self.click()
        await self.action(picker, label).callback(picker, interaction, index)
        modal = interaction.response.send_modal.await_args.args[0]
        submitted = self.click()
        with patch.object(utils, 'isUserAdminOrOwner', MagicMock(return_value = admin)), patch.object(hype_queries, 'getAllServerMatches', MagicMock(return_value = stored if stored is not None else self.twoMatches())):
            modal.pattern._inputed_value = pattern
            modal.responses._inputed_value = text
            await modal.callback(submitted)
        return modal, submitted

    async def test_hype_is_one_command_for_slash_and_prefix(self):
        self.hype.commonHype = AsyncMock()
        await self.hype.hypeSlash(self.interaction)
        self.hype.commonHype.assert_awaited_with(self.interaction, self.interaction.user)
        await self.hype.hype(self.hype, self.ctx)
        self.hype.commonHype.assert_awaited_with(self.ctx, self.author)

    async def test_the_card_lists_matches_with_add_edit_and_delete(self):
        picker = await self.openHype()
        self.assertIs(self.started.await_args.kwargs['ephemeral'], True)
        self.assertIsInstance(picker, pagination.ListPicker)
        self.assertEqual(picker.source.entries, [f"**1.** `{self.EXPECTED_REGEX}`\n💬 **Replies:** Woohoo!", f"**2.** `{self.EXPECTED_REGEX}`\n😀 **Reacts:** 👍"])
        self.assertEqual(picker.source.thumbnailUrl, 'icon url')
        self.assertEqual([(action.label, action.row) for action in picker.actions], [('Add reply', 2), ('Add reaction', 2), ('Edit', 2), ('Delete', 2), ('Test', 3)])
        self.assertTrue(self.action(picker, 'Delete').confirm)
        self.assertTrue(self.action(picker, 'Edit').needsSelection)

    async def test_the_card_opens_privately_from_either_command(self):
        with patch('GBotDiscord.src.hype.hype_cog.pagination.openPrivately', AsyncMock()) as openPrivately:
            await self.hype.commonHype(self.ctx, self.author)
        openPrivately.assert_awaited_once_with(self.ctx, '↩️', 'Hype matches', self.hype.openCard, feature = 'toggle_hype', admin = True)

    async def test_testing_a_message_says_what_would_fire(self):
        matches = {
            'a': {'regex': "(?i)let'?s go", 'responses': ['Woohoo!', 'Gooo'], 'isReaction': False},
            'b': {'regex': 'gg', 'responses': ['🎉'], 'isReaction': True},
            'c': {'regex': '(?i)let', 'responses': [], 'isReaction': False},
            'd': {'regex': '(?i)lets', 'responses': ['🔥'], 'isReaction': True}}
        picker = await self.openHype(matches = matches)
        interaction = self.click()
        await self.action(picker, 'Test').callback(picker, interaction, None)
        form = interaction.response.send_modal.await_args.args[0]
        self.assertEqual(form.title, 'Test a message')
        submitted = self.click()
        with patch.object(utils, 'isUserAdminOrOwner', MagicMock(return_value = True)), patch.object(hype_queries, 'getAllServerMatches', MagicMock(return_value = matches)):
            await form.onSubmit(submitted, ["LET'S GO team"])
            notice = submitted.response.edit_message.await_args.kwargs['embed'].fields[-1].value
            self.assertEqual(notice, "🧪 That message would match:\n**1.** `(?i)let'?s go` 💬 replies with one of: Woohoo!, Gooo")
            submitted = self.click()
            await form.onSubmit(submitted, ['hello'])
            self.assertIn("🧪 That message wouldn't match anything.", self.shown(submitted))
        # someone no longer an admin is told so, and nothing is tested
        submitted = self.click()
        with patch.object(utils, 'isUserAdminOrOwner', MagicMock(return_value = False)):
            await form.onSubmit(submitted, ['gg'])
        self.assertIn('need to be an admin', self.shown(submitted))

    async def test_with_no_matches_the_card_still_opens_to_add_one(self):
        self.guild.icon = None
        picker = await self.openHype(matches = None)
        self.assertEqual(picker.source.entries, [])
        self.assertIn('Add reply', picker.source.empty)
        self.assertIsNone(picker.source.thumbnailUrl)

    async def test_the_slash_card_is_private_from_the_start(self):
        interaction = Mock(spec = nextcord.Interaction)
        interaction.guild = self.guild
        interaction.user = self.author
        interaction.response = Mock(defer = AsyncMock())
        await self.openHype(interaction)
        interaction.response.defer.assert_awaited_once_with(ephemeral = True)

    async def test_adding_a_reply_one_per_line(self):
        picker = await self.openHype()
        with patch.object(hype_queries, 'createMatch', MagicMock()) as create:
            modal, submitted = await self.submit(picker, 'Add reply', ' (?i)gg ', "Good game!\n\n  Well played  \n")
        self.assertEqual(modal.title, 'Add a reply')
        create.assert_called_once_with(self.guild.id, '(?i)gg', ['Good game!', 'Well played'], False)
        self.assertIn('✅ Added', self.shown(submitted))
        submitted.response.defer.assert_awaited_once_with()

    async def test_adding_a_reaction_takes_real_and_custom_emoji(self):
        picker = await self.openHype()
        self.hype.client.get_emoji = MagicMock(side_effect = lambda emojiId: Mock() if emojiId == 5 else None)
        with patch.object(hype_queries, 'createMatch', MagicMock()) as create:
            modal, submitted = await self.submit(picker, 'Add reaction', 'gg', '🎉 <:party:5>\n👍')
        self.assertEqual(modal.responses.label, 'Emoji to react with')
        create.assert_called_once_with(self.guild.id, 'gg', ['🎉', '<:party:5>', '👍'], True)

    async def test_bad_forms_are_refused_on_the_card(self):
        picker = await self.openHype()
        self.hype.client.get_emoji = MagicMock(return_value = None)
        with patch.object(hype_queries, 'createMatch', MagicMock()) as create:
            for label, pattern, text, expected in (('Add reply', '(unclosed', 'x', "isn't a valid regular expression"), ('Add reply', 'gg', '  \n ', 'at least one reply'), ('Add reaction', 'gg', '   ', 'at least one emoji'), ('Add reaction', 'gg', 'notanemoji', "can't react with notanemoji"), ('Add reaction', 'gg', '<:gone:9>', "can't react with <:gone:9>")):
                _, submitted = await self.submit(picker, label, pattern, text)
                self.assertIn(f'❌', self.shown(submitted))
                self.assertIn(expected, self.shown(submitted), (label, text))
            create.assert_not_called()

    async def test_editing_starts_from_the_match_and_keeps_its_kind(self):
        picker = await self.openHype()
        with patch.object(hype_queries, 'updateMatch', MagicMock()) as update:
            modal, submitted = await self.submit(picker, 'Edit', 'gg', '🔥', index = 1)
        self.assertEqual(modal.title, 'Edit match 2')
        self.assertEqual(modal.pattern.default_value, self.EXPECTED_REGEX)
        self.assertEqual(modal.responses.default_value, '👍')
        self.assertEqual(modal.responses.label, 'Emoji to react with')
        update.assert_called_once_with(self.guild.id, 'match2', 'gg', ['🔥'])
        self.assertIn('Match 2 updated', self.shown(submitted))

    async def test_someone_no_longer_an_admin_changes_nothing(self):
        picker = await self.openHype()
        with patch.object(hype_queries, 'createMatch', MagicMock()) as create:
            _, submitted = await self.submit(picker, 'Add reply', 'gg', 'x', admin = False)
        create.assert_not_called()
        self.assertIn('need to be an admin', self.shown(submitted))
        interaction = self.click()
        with patch.object(utils, 'isUserAdminOrOwner', MagicMock(return_value = False)), patch.object(hype_queries, 'removeMatch', MagicMock()) as remove:
            await self.action(picker, 'Delete').callback(picker, interaction, 0)
        remove.assert_not_called()

    async def test_deleting_a_match_removes_it_and_refreshes_the_list(self):
        picker = await self.openHype()
        interaction = self.click()
        remaining = {"match1": self.twoMatches()["match1"]}
        with patch.object(utils, 'isUserAdminOrOwner', MagicMock(return_value = True)), patch.object(hype_queries, 'removeMatch', MagicMock()) as remove, patch.object(hype_queries, 'getAllServerMatches', MagicMock(return_value = remaining)):
            await self.action(picker, 'Delete').callback(picker, interaction, 1)
        remove.assert_called_once_with(self.guild.id, 'match2')
        self.assertEqual(len(picker.source.entries), 1)
        self.assertIn('🗑️ Match 2 deleted.', self.shown(interaction))
        interaction.response.defer.assert_awaited_once_with()

    async def test_the_form_hands_both_boxes_on(self):
        received = []
        async def submitted(interaction, pattern, text):
            received.append((pattern, text))
        modal = HypeModal('T', False, None, '', submitted)
        self.assertIsNone(modal.responses.default_value)
        self.assertEqual(modal.responses.label, 'Replies, one per line')
        modal.pattern._inputed_value = 'p'
        modal.responses._inputed_value = 'r'
        await modal.callback(Mock())
        self.assertEqual(received, [('p', 'r')])

    async def test_on_message_no_matches_configured(self):
        hype_queries.getAllServerMatches = MagicMock(return_value = None)
        await self.hype.on_message(self.message1)
        self.message1.add_reaction.assert_not_called()
        self.message1.reply.assert_not_called()

    async def test_on_message_add_reaction_exception_replies_with_error(self):
        self.message1.add_reaction = AsyncMock(side_effect = Exception('boom'))
        hype_queries.getAllServerMatches = MagicMock(return_value = {
            'match1': {
                'regex': r"((.|\n)*)([Ll]+[Ee]+[Tt]+[']?[Ss]+[\s]+[Gg]+[Oo]+)((.|\n)*)",
                'responses': ["👍"],
                'isReaction': True,
            },
        })
        await self.hype.on_message(self.message1)
        self.message1.reply.assert_awaited_once_with(
            "GBot ran into an issue trying to react to this message. Please remove the broken match.")

    def test_setup_adds_cog(self):
        from GBotDiscord.src.hype import hype_cog
        client = MagicMock()
        hype_cog.setup(client)
        client.add_cog.assert_called_once()
        addedCog = client.add_cog.call_args[0][0]
        self.assertIsInstance(addedCog, Hype)


if __name__ == '__main__':
    unittest.main()