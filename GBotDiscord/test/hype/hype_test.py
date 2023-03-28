#region IMPORTS
import unittest
from unittest.mock import MagicMock, Mock, AsyncMock
import nextcord
from nextcord.ext import commands
from nextcord.ext.commands.context import Context

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
                "regex": "((.|\n)*)([Ll]+[Ee]+[Tt]+[']?[Ss]+[\s]+[Gg]+[Oo]+)((.|\n)*)",
                "responses": [
                    "Woohoo!"
                ],
                "isReaction": False
            },
            "match2": {
                "regex": "((.|\n)*)([Ll]+[Ee]+[Tt]+[']?[Ss]+[\s]+[Gg]+[Oo]+)((.|\n)*)",
                "responses": [
                    "👍"
                ],
                "isReaction": True
            },
        })

        self.ctx: Context = Mock()
        self.ctx.guild = self.guild
        self.ctx.author = self.author

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

    async def test_hype(self):
        regex = "((.|\n)*)([Ll]+[Ee]+[Tt]+[']?[Ss]+[\s]+[Gg]+[Oo]+)((.|\n)*)"
        responses = ["Woohoo!", "Ayyy!", "👏👏👏"]
        GBotFirebaseService.push = MagicMock()
        self.ctx.send = AsyncMock()
        await self.hype.hype(self.hype, self.ctx, regex, "Woohoo!", "Ayyy!", "👏👏👏")
        GBotFirebaseService.push.assert_any_call(["hype_servers", self.guild.id], {"regex": regex, "responses": responses, "isReaction": False})
        self.ctx.send.assert_called_once_with(f"A new message match has been created with regex '{regex}'. All matching messages will reply with one of the following: {responses}")

    async def test_react(self):
        partialEmoji = nextcord.PartialEmoji(
            id = 10,
            name = "partialEmoji"
        )

        emoji = Mock(spec = nextcord.Emoji)
        emoji.id = 11
        emoji.name = "emoji"

        regex = "((.|\n)*)([Ll]+[Ee]+[Tt]+[']?[Ss]+[\s]+[Gg]+[Oo]+)((.|\n)*)"
        emojiList = ["👍", "💯", "👏", f"<:{emoji.name}:{emoji.id}>"]
        GBotFirebaseService.push = MagicMock()
        self.ctx.send = AsyncMock()
        await self.hype.react(self.hype, self.ctx, regex, "👍", "💯", "👏", partialEmoji, emoji)
        GBotFirebaseService.push.assert_any_call(["hype_servers", self.guild.id], {"regex": regex, "responses": emojiList, "isReaction": True})
        self.ctx.send.assert_any_call(f"The emoji could not be added as the bot does not have access to this emoji: '<:{partialEmoji.name}:{partialEmoji.id}>'")
        self.ctx.send.assert_any_call(f"A new message match has been created with regex '{regex}'. All matching messages will react with one of the following: {emojiList}")

    async def test_unmatch_no_matches(self):
        self.ctx.send = AsyncMock()
        hype_queries.getAllServerMatches = MagicMock(return_value = None)
        await self.hype.unmatch(self.hype, self.ctx)
        self.ctx.send.assert_called_once_with(f"Sorry {self.author.mention}, the server has no matches configured.")

    async def test_unmatch_cancel(self):
        # TODO - need to be able to mock the __init__ of CustomButtonMenuPages in additon to FieldPageSource so we don't throw an error; this will allow us to go further
        # TODO - once figured out here, update gcoin_test & config_test to behave the same way (remove try/catch blocks)

        # assert all matches shown correctly
        # assert question asked to user
        # assert cancelled message
        pass

    async def test_unmatch_timeout(self):
        # assert all matches shown correctly
        # assert question asked to user
        # assert timeout message
        pass

    async def test_unmatch_match_deleted(self):
        # assert all matches shown correctly
        # assert question asked to user
        # assert match deleted message
        # assert remove query called
        pass

if __name__ == '__main__':
    unittest.main()