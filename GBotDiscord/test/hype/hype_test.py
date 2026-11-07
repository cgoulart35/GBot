#region IMPORTS
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
from GBotDiscord.src.hype.hype_cog import Hype
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

    async def test_on_message_match_saved_without_responses(self):
        # the database doesn't store an empty list, so the key is missing altogether
        hype_queries.getAllServerMatches = MagicMock(return_value = {"match1": {"regex": ".*", "isReaction": False}})
        await self.hype.on_message(self.message1)
        self.message1.reply.assert_not_called()

    async def test_respond_refuses_no_responses(self):
        GBotFirebaseService.push = MagicMock()
        self.ctx.send = AsyncMock()
        await self.hype.respond(self.hype, self.ctx, ".*")
        GBotFirebaseService.push.assert_not_called()
        self.assertIn("no responses", self.ctx.send.call_args.kwargs["embed"].description)

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
    async def test_respond_rejects_invalid_regex(self):
        GBotFirebaseService.push = MagicMock()
        self.ctx.send = AsyncMock()
        await self.hype.respond(self.hype, self.ctx, "([unclosed", "Woohoo!")
        GBotFirebaseService.push.assert_not_called()
        self.assertIn("is not a valid regular expression", self.ctx.send.call_args.kwargs["embed"].description)

    async def test_react_rejects_invalid_regex(self):
        GBotFirebaseService.push = MagicMock()
        self.ctx.send = AsyncMock()
        await self.hype.react(self.hype, self.ctx, "([unclosed", "👍")
        GBotFirebaseService.push.assert_not_called()
        self.assertIn("is not a valid regular expression", self.ctx.send.call_args.kwargs["embed"].description)

    async def test_respond(self):
        regex = r"((.|\n)*)([Ll]+[Ee]+[Tt]+[']?[Ss]+[\s]+[Gg]+[Oo]+)((.|\n)*)"
        responses = ["Woohoo!", "Ayyy!", "👏👏👏"]
        GBotFirebaseService.push = MagicMock()
        self.ctx.send = AsyncMock()
        await self.hype.respond(self.hype, self.ctx, regex, "Woohoo!", "Ayyy!", "👏👏👏")
        GBotFirebaseService.push.assert_any_call(["hype_servers", self.guild.id], {"regex": regex, "responses": responses, "isReaction": False})
        self.assertIn((f"↩️ A new message match has been created with regex `{regex}`. All matching messages will reply with one of the following: {', '.join(responses)}"), [call.kwargs.get('content') for call in self.ctx.send.call_args_list])

    async def test_respond_slash(self):
        regex = r"((.|\n)*)([Ll]+[Ee]+[Tt]+[']?[Ss]+[\s]+[Gg]+[Oo]+)((.|\n)*)"
        responses = ["Woohoo!", "Ayyy!", "👏👏👏"]
        GBotFirebaseService.push = MagicMock()
        self.interaction.send = AsyncMock()
        await self.hype.respondSlash(self.interaction, regex, "\"Woohoo!\"\"Ayyy!\"\"👏👏👏\"")
        GBotFirebaseService.push.assert_any_call(["hype_servers", self.guild.id], {"regex": regex, "responses": responses, "isReaction": False})
        self.assertIn((f"↩️ A new message match has been created with regex `{regex}`. All matching messages will reply with one of the following: {', '.join(responses)}"), [call.kwargs.get('content') for call in self.interaction.send.call_args_list])

    async def test_react(self):
        partialEmoji = nextcord.PartialEmoji(
            id = 10,
            name = "partialEmoji"
        )

        emoji = Mock(spec = nextcord.Emoji)
        emoji.id = 11
        emoji.name = "emoji"

        regex = r"((.|\n)*)([Ll]+[Ee]+[Tt]+[']?[Ss]+[\s]+[Gg]+[Oo]+)((.|\n)*)"
        emojiList = ["👍", "💯", "👏", f"<:{emoji.name}:{emoji.id}>"]
        GBotFirebaseService.push = MagicMock()
        self.ctx.send = AsyncMock()
        await self.hype.react(self.hype, self.ctx, regex, "👍", "💯", "👏", partialEmoji, emoji)
        GBotFirebaseService.push.assert_any_call(["hype_servers", self.guild.id], {"regex": regex, "responses": emojiList, "isReaction": True})
        assertErrorCard(self.ctx.send, f"The emoji could not be added as the bot does not have access to this emoji: '<:{partialEmoji.name}:{partialEmoji.id}>'")
        self.assertIn((f"↩️ A new message match has been created with regex `{regex}`. All matching messages will react with one of the following: {', '.join(emojiList)}"), [call.kwargs.get('content') for call in self.ctx.send.call_args_list])

    async def test_react_slash(self):
        emoji = Mock(spec = nextcord.Emoji)
        emoji.id = 11
        emoji.name = "emoji"
        emoji_string = f"<:{emoji.name}:{emoji.id}>"

        regex = r"((.|\n)*)([Ll]+[Ee]+[Tt]+[']?[Ss]+[\s]+[Gg]+[Oo]+)((.|\n)*)"
        emojiList = ["👍", "💯", "👏", emoji_string]
        GBotFirebaseService.push = MagicMock()
        self.interaction.send = AsyncMock()
        await self.hype.reactSlash(self.interaction, regex, "👍💯👏"+ emoji_string)
        GBotFirebaseService.push.assert_any_call(["hype_servers", self.guild.id], {"regex": regex, "responses": emojiList, "isReaction": True})
        self.assertIn((f"↩️ A new message match has been created with regex `{regex}`. All matching messages will react with one of the following: {', '.join(emojiList)}"), [call.kwargs.get('content') for call in self.interaction.send.call_args_list])

    async def test_remove_no_matches(self):
        self.ctx.send = AsyncMock()
        hype_queries.getAllServerMatches = MagicMock(return_value = None)
        await self.hype.remove(self.hype, self.ctx)
        assertErrorCard(self.ctx.send, f"Sorry {self.author.mention}, the server has no matches configured.")

    async def test_remove_slash_no_matches(self):
        self.interaction.send = AsyncMock()
        hype_queries.getAllServerMatches = MagicMock(return_value = None)
        await self.hype.removeSlash(self.interaction)
        assertErrorCard(self.interaction.send, f"Sorry {self.author.mention}, the server has no matches configured.")

    EXPECTED_REGEX = r"((.|\n)*)([Ll]+[Ee]+[Tt]+[']?[Ss]+[\s]+[Gg]+[Oo]+)((.|\n)*)"

    def twoMatches(self):
        return {
            "match1": {"regex": self.EXPECTED_REGEX, "responses": ["Woohoo!"], "isReaction": False},
            "match2": {"regex": self.EXPECTED_REGEX, "responses": ["👍"], "isReaction": True}
        }

    async def openRemove(self, context):
        context.send = AsyncMock()
        with patch.object(hype_queries, 'getAllServerMatches', MagicMock(return_value = self.twoMatches())), patch.object(pagination, 'startPages', AsyncMock()) as start:
            await self.hype.commonUnmatch(context, self.author)
        return start

    async def test_remove_lists_matches_in_a_picker(self):
        start = await self.openRemove(self.ctx)
        picker = start.await_args.args[1]
        self.assertIs(start.await_args.kwargs['ephemeral'], True)
        self.assertIsInstance(picker, pagination.ListPicker)
        self.assertEqual(picker.source.entries, [f"**1.** `{self.EXPECTED_REGEX}`\n💬 **Replies:** Woohoo!", f"**2.** `{self.EXPECTED_REGEX}`\n😀 **Reacts:** 👍"])
        self.assertEqual(picker.source.thumbnailUrl, 'icon url')
        self.assertEqual([action.label for action in picker.actions], ['Delete'])
        self.assertTrue(picker.actions[0].confirm)
        self.assertTrue(picker.actions[0].needsSelection)

    async def test_remove_without_an_icon(self):
        self.guild.icon = None
        start = await self.openRemove(self.ctx)
        self.assertIsNone(start.await_args.args[1].source.thumbnailUrl)

    async def test_remove_slash_is_private_from_the_start(self):
        interaction = Mock(spec = nextcord.Interaction)
        interaction.guild = self.guild
        interaction.user = self.author
        interaction.response = Mock(defer = AsyncMock())
        await self.openRemove(interaction)
        interaction.response.defer.assert_awaited_once_with(ephemeral = True)

    async def test_deleting_a_match_removes_it_and_refreshes_the_list(self):
        start = await self.openRemove(self.ctx)
        picker = start.await_args.args[1]
        interaction = Mock(response = Mock(edit_message = AsyncMock()))
        remaining = {"match1": self.twoMatches()["match1"]}
        with patch.object(hype_queries, 'removeMatch', MagicMock()) as remove, patch.object(hype_queries, 'getAllServerMatches', MagicMock(return_value = remaining)):
            await picker.actions[0].callback(picker, interaction, 1)
        remove.assert_called_once_with(self.guild.id, 'match2')
        self.assertEqual(len(picker.source.entries), 1)
        embed = interaction.response.edit_message.await_args.kwargs['embed']
        self.assertIn('🗑️ Match 2 deleted.', [field.value for field in embed.fields])
        with patch.object(hype_queries, 'removeMatch', MagicMock()), patch.object(hype_queries, 'getAllServerMatches', MagicMock(return_value = None)):
            await picker.actions[0].callback(picker, interaction, 0)
        self.assertEqual(picker.source.entries, [])
        self.assertIn('No matches left', interaction.response.edit_message.await_args.kwargs['embed'].description)

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

    async def test_commonReact_no_valid_emojis_skips_createMatch(self):
        partialEmoji = nextcord.PartialEmoji(id = 10, name = "partialEmoji")
        self.ctx.send = AsyncMock()
        GBotFirebaseService.push = MagicMock()
        await self.hype.commonReact(self.ctx, 'regex', [partialEmoji])
        GBotFirebaseService.push.assert_not_called()
        assertErrorCard(self.ctx.send, f"The emoji could not be added as the bot does not have access to this emoji: '<:{partialEmoji.name}:{partialEmoji.id}>'")

    def test_setup_adds_cog(self):
        from GBotDiscord.src.hype import hype_cog
        client = MagicMock()
        hype_cog.setup(client)
        client.add_cog.assert_called_once()
        addedCog = client.add_cog.call_args[0][0]
        self.assertIsInstance(addedCog, Hype)


if __name__ == '__main__':
    unittest.main()