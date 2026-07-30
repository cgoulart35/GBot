#region IMPORTS
import asyncio
import unittest
from unittest.mock import MagicMock, Mock, AsyncMock
import nextcord
from nextcord.ext import commands
from nextcord.ext.commands.context import Context

from GBotDiscord.src import pagination
from GBotDiscord.src import utils
from GBotDiscord.src.config import config_queries
from GBotDiscord.src.hype import hype_queries
from GBotDiscord.src.hype.hype_cog import Hype
from GBotDiscord.src.properties import GBotPropertiesManager
from GBotDiscord.src.firebase import GBotFirebaseService
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
    async def test_hype_rejects_invalid_regex(self):
        GBotFirebaseService.push = MagicMock()
        self.ctx.send = AsyncMock()
        await self.hype.hype(self.hype, self.ctx, "([unclosed", "Woohoo!")
        GBotFirebaseService.push.assert_not_called()
        self.assertIn("is not a valid regular expression", self.ctx.send.call_args[0][0])

    async def test_react_rejects_invalid_regex(self):
        GBotFirebaseService.push = MagicMock()
        self.ctx.send = AsyncMock()
        await self.hype.react(self.hype, self.ctx, "([unclosed", "👍")
        GBotFirebaseService.push.assert_not_called()
        self.assertIn("is not a valid regular expression", self.ctx.send.call_args[0][0])

    async def test_hype(self):
        regex = r"((.|\n)*)([Ll]+[Ee]+[Tt]+[']?[Ss]+[\s]+[Gg]+[Oo]+)((.|\n)*)"
        responses = ["Woohoo!", "Ayyy!", "👏👏👏"]
        GBotFirebaseService.push = MagicMock()
        self.ctx.send = AsyncMock()
        await self.hype.hype(self.hype, self.ctx, regex, "Woohoo!", "Ayyy!", "👏👏👏")
        GBotFirebaseService.push.assert_any_call(["hype_servers", self.guild.id], {"regex": regex, "responses": responses, "isReaction": False})
        self.ctx.send.assert_called_once_with(f"A new message match has been created with regex '{regex}'. All matching messages will reply with one of the following: {responses}")

    async def test_hype_slash(self):
        regex = r"((.|\n)*)([Ll]+[Ee]+[Tt]+[']?[Ss]+[\s]+[Gg]+[Oo]+)((.|\n)*)"
        responses = ["Woohoo!", "Ayyy!", "👏👏👏"]
        GBotFirebaseService.push = MagicMock()
        self.interaction.send = AsyncMock()
        await self.hype.hypeSlash(self.interaction, regex, "\"Woohoo!\"\"Ayyy!\"\"👏👏👏\"")
        GBotFirebaseService.push.assert_any_call(["hype_servers", self.guild.id], {"regex": regex, "responses": responses, "isReaction": False})
        self.interaction.send.assert_called_once_with(f"A new message match has been created with regex '{regex}'. All matching messages will reply with one of the following: {responses}")

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
        self.ctx.send.assert_any_call(f"The emoji could not be added as the bot does not have access to this emoji: '<:{partialEmoji.name}:{partialEmoji.id}>'")
        self.ctx.send.assert_any_call(f"A new message match has been created with regex '{regex}'. All matching messages will react with one of the following: {emojiList}")

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
        self.interaction.send.assert_any_call(f"A new message match has been created with regex '{regex}'. All matching messages will react with one of the following: {emojiList}")

    async def test_unmatch_no_matches(self):
        self.ctx.send = AsyncMock()
        hype_queries.getAllServerMatches = MagicMock(return_value = None)
        await self.hype.unmatch(self.hype, self.ctx)
        self.ctx.send.assert_called_once_with(f"Sorry {self.author.mention}, the server has no matches configured.")

    async def test_unmatch_slash_no_matches(self):
        self.interaction.send = AsyncMock()
        hype_queries.getAllServerMatches = MagicMock(return_value = None)
        await self.hype.unmatchSlash(self.interaction)
        self.interaction.send.assert_called_once_with(f"Sorry {self.author.mention}, the server has no matches configured.")

    # The unmatch cog code calls pagination.CustomButtonMenuPages(source = pagination.FieldPageSource(...))
    # then awaits pagination.startPages(context, pages). To exercise the rest of commonUnmatch
    # (the askUserQuestion loop and its outcome branches) without rendering a real menu, we stub
    # both __init__s with return_value=None and replace startPages with an AsyncMock — this lets
    # control flow proceed past pagination so we can assert on the question, the removeMatch call,
    # and the final response message. setUp does not reset these stubs, so each test re-stubs.

    EXPECTED_REGEX = r"((.|\n)*)([Ll]+[Ee]+[Tt]+[']?[Ss]+[\s]+[Gg]+[Oo]+)((.|\n)*)"
    EXPECTED_QUESTION = " What match would you like to remove for this server? Please respond with the corresponding number, or 'cancel'."

    def _stubPagination(self):
        pagination.FieldPageSource.__init__ = MagicMock(return_value = None)
        pagination.CustomButtonMenuPages.__init__ = MagicMock(return_value = None)
        pagination.startPages = AsyncMock()
        utils.getServerPrefixOrDefault = MagicMock(return_value = '.')
        hype_queries.removeMatch = MagicMock()

    def _expectedFields(self):
        return [
            ('Match 1', f"`Regex: {self.EXPECTED_REGEX}`\n`Replies: ['Woohoo!']`"),
            ('Match 2', f"`Regex: {self.EXPECTED_REGEX}`\n`Reactions: ['👍']`"),
        ]

    def _slashInteraction(self):
        interaction = Mock(spec = nextcord.Interaction)
        interaction.guild = self.guild
        interaction.user = self.author
        interaction.response = Mock()
        interaction.response.defer = AsyncMock()
        interaction.send = AsyncMock()
        return interaction

    def _assertMenuRendered(self, thumbnailUrl):
        pagination.FieldPageSource.__init__.assert_called_once_with(
            self._expectedFields(), thumbnailUrl, "GBot Hype Matches", nextcord.Color.blue(), False, 10)
        pagination.CustomButtonMenuPages.__init__.assert_called_once()
        pagination.startPages.assert_awaited_once()

    async def test_unmatch_cancel(self):
        self._stubPagination()
        cancelMsg = Mock()
        cancelMsg.content = 'cancel'
        utils.askUserQuestion = AsyncMock(return_value = cancelMsg)
        self.ctx.send = AsyncMock()

        await self.hype.unmatch(self.hype, self.ctx)

        self._assertMenuRendered(self.icon.url)
        utils.askUserQuestion.assert_awaited_once()
        self.assertEqual(utils.askUserQuestion.await_args.args[3], self.EXPECTED_QUESTION)
        hype_queries.removeMatch.assert_not_called()
        self.ctx.send.assert_called_once_with(f'{self.author.mention}, match deletion has been cancelled.')

    async def test_unmatch_slash_cancel(self):
        self._stubPagination()
        cancelMsg = Mock()
        cancelMsg.content = 'cancel'
        utils.askUserQuestion = AsyncMock(return_value = cancelMsg)
        interaction = self._slashInteraction()

        await self.hype.unmatchSlash(interaction)

        interaction.response.defer.assert_awaited_once()
        self._assertMenuRendered(self.icon.url)
        utils.askUserQuestion.assert_awaited_once()
        self.assertEqual(utils.askUserQuestion.await_args.args[3], self.EXPECTED_QUESTION)
        hype_queries.removeMatch.assert_not_called()
        interaction.send.assert_called_once_with(f'{self.author.mention}, match deletion has been cancelled.')

    async def test_unmatch_timeout(self):
        self._stubPagination()
        utils.askUserQuestion = AsyncMock(side_effect = asyncio.TimeoutError)
        self.ctx.send = AsyncMock()

        await self.hype.unmatch(self.hype, self.ctx)

        self._assertMenuRendered(self.icon.url)
        utils.askUserQuestion.assert_awaited_once()
        hype_queries.removeMatch.assert_not_called()
        self.ctx.send.assert_called_once_with(f'Sorry {self.author.mention}, you did not respond in time.')

    async def test_unmatch_slash_timeout(self):
        self._stubPagination()
        utils.askUserQuestion = AsyncMock(side_effect = asyncio.TimeoutError)
        interaction = self._slashInteraction()

        await self.hype.unmatchSlash(interaction)

        interaction.response.defer.assert_awaited_once()
        self._assertMenuRendered(self.icon.url)
        utils.askUserQuestion.assert_awaited_once()
        hype_queries.removeMatch.assert_not_called()
        interaction.send.assert_called_once_with(f'Sorry {self.author.mention}, you did not respond in time.')

    async def test_unmatch_match_deleted(self):
        self._stubPagination()
        # First response is invalid (forces a second prompt with "Invalid selection." prefix),
        # second response selects match 2 — covers the loop's invalid-input branch and the
        # successful removal in one test.
        invalidMsg = Mock()
        invalidMsg.content = 'abc'
        validMsg = Mock()
        validMsg.content = '2'
        utils.askUserQuestion = AsyncMock(side_effect = [invalidMsg, validMsg])
        self.ctx.send = AsyncMock()

        await self.hype.unmatch(self.hype, self.ctx)

        self._assertMenuRendered(self.icon.url)
        self.assertEqual(utils.askUserQuestion.await_count, 2)
        self.assertEqual(utils.askUserQuestion.await_args_list[0].args[3], self.EXPECTED_QUESTION)
        self.assertEqual(utils.askUserQuestion.await_args_list[1].args[3], 'Invalid selection.' + self.EXPECTED_QUESTION)
        hype_queries.removeMatch.assert_called_once_with(self.guild.id, 'match2')
        self.ctx.send.assert_called_once_with('Match 2 deleted.')

    async def test_unmatch_slash_match_deleted(self):
        self._stubPagination()
        validMsg = Mock()
        validMsg.content = '1'
        utils.askUserQuestion = AsyncMock(return_value = validMsg)
        interaction = self._slashInteraction()
        # exercise the no-icon branch on the slash variant for additional coverage
        self.guild.icon = None

        await self.hype.unmatchSlash(interaction)

        interaction.response.defer.assert_awaited_once()
        self._assertMenuRendered(None)
        utils.askUserQuestion.assert_awaited_once()
        hype_queries.removeMatch.assert_called_once_with(self.guild.id, 'match1')
        interaction.send.assert_called_once_with('Match 1 deleted.')

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
        self.ctx.send.assert_called_once_with(
            f"The emoji could not be added as the bot does not have access to this emoji: '<:{partialEmoji.name}:{partialEmoji.id}>'")

    async def test_unmatch_empty_response_loops_and_succeeds(self):
        self._stubPagination()
        emptyMsg = Mock()
        emptyMsg.content = ''
        validMsg = Mock()
        validMsg.content = '1'
        utils.askUserQuestion = AsyncMock(side_effect = [emptyMsg, validMsg])
        self.ctx.send = AsyncMock()

        await self.hype.unmatch(self.hype, self.ctx)

        self.assertEqual(utils.askUserQuestion.await_count, 2)
        hype_queries.removeMatch.assert_called_once_with(self.guild.id, 'match1')
        self.ctx.send.assert_called_once_with('Match 1 deleted.')

    async def test_unmatch_out_of_range_number_loops_until_valid(self):
        self._stubPagination()
        oorMsg = Mock()
        oorMsg.content = '999'
        validMsg = Mock()
        validMsg.content = '1'
        utils.askUserQuestion = AsyncMock(side_effect = [oorMsg, validMsg])
        self.ctx.send = AsyncMock()

        await self.hype.unmatch(self.hype, self.ctx)

        self.assertEqual(utils.askUserQuestion.await_count, 2)
        self.assertEqual(utils.askUserQuestion.await_args_list[1].args[3], 'Invalid selection.' + self.EXPECTED_QUESTION)
        hype_queries.removeMatch.assert_called_once_with(self.guild.id, 'match1')
        self.ctx.send.assert_called_once_with('Match 1 deleted.')

    def test_setup_adds_cog(self):
        from GBotDiscord.src.hype import hype_cog
        client = MagicMock()
        hype_cog.setup(client)
        client.add_cog.assert_called_once()
        addedCog = client.add_cog.call_args[0][0]
        self.assertIsInstance(addedCog, Hype)


if __name__ == '__main__':
    unittest.main()