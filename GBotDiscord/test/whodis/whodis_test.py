#region IMPORTS
import threading
import unittest
from unittest.mock import MagicMock, Mock, AsyncMock, patch
import nextcord
from nextcord.ext import commands
from nextcord.ext.commands.context import Context
from datetime import datetime, timedelta
from decimal import Decimal

from GBotDiscord.test.utils import AsyncIter
from GBotDiscord.src import utils
from GBotDiscord.src.config import config_queries
from GBotDiscord.src.gcoin import gcoin_queries
from GBotDiscord.src.leaderboards import leaderboards_queries
from GBotDiscord.src.whodis import whodis_cog
from GBotDiscord.src.whodis.whodis_cog import WhoDis
from GBotDiscord.src import pagination
from GBotDiscord.test import isolation
from GBotDiscord.src.exceptions import WhoDisNotConfigured, CustomCommandOnCooldown
from GBotDiscord.src.properties import GBotPropertiesManager
from GBotDiscord.test.card_assertions import assertCard, assertErrorCard
#endregion

# to run this test suite:
#   - execute the following command from the GBot directory: python -m unittest GBotDiscord/test/whodis/whodis_test.py
#   - or use the "Python: Current File" run configuration to run whodis_test.py
#   - or use the "Python: Current File" run configuration to run tests.py to run all test suites
# ✖️ Close has no label, which nextcord keeps as MISSING
CLOSE = nextcord.utils.MISSING

class TestWhoDis(unittest.IsolatedAsyncioTestCase):

    @classmethod
    def setUpClass(self):
        print('\nExecuting whodis unit tests...\n')

    @classmethod
    def tearDownClass(self):
        print('\n\nCompleted whodis unit tests.\n')

    def setUp(self):
        GBotPropertiesManager.WHODIS_TIMEOUT_MINUTES = 5
        GBotPropertiesManager.WHODIS_COOLDOWN_MINUTES = 10

        self.avatar = Mock()
        self.avatar.url = "avatar url"

        self.icon = Mock()
        self.icon.url = "icon url"

        self.role = Mock()
        self.role.id = 77777
        self.role.mention = "<@&77777>"

        self.author = Mock()
        self.author.id = 54321
        self.author.name = "author name"
        self.author.mention = "<@!54321>"
        self.author.bot = False
        self.author.avatar = self.avatar
        self.author.status = nextcord.Status.online
        self.author.roles = [self.role]
        self.author.send = AsyncMock()
        self.author.add_roles = AsyncMock()
        self.author.remove_roles = AsyncMock()

        self.randomUser = Mock()
        self.randomUser.id = 12345
        self.randomUser.name = "random user name"
        self.randomUser.mention = "<@!12345>"
        self.randomUser.bot = False
        self.randomUser.avatar = self.avatar
        self.randomUser.status = nextcord.Status.online
        self.randomUser.roles = [self.role]
        self.randomUser.send = AsyncMock()

        self.otherUser = Mock()
        self.otherUser.id = 99988
        self.otherUser.name = "other user"
        self.otherUser.mention = "<@!99988>"
        self.otherUser.bot = False
        self.otherUser.avatar = self.avatar
        self.otherUser.status = nextcord.Status.online
        self.otherUser.roles = []
        self.otherUser.send = AsyncMock()

        self.guild: nextcord.Guild = Mock()
        self.guild.id = 99999
        self.guild.name = "guild name"
        self.guild.icon = self.icon
        self.guild.roles = [self.role]
        self.guild.get_member = MagicMock(side_effect = lambda uid: self.author if uid == self.author.id else self.randomUser)

        self.channel = Mock()
        self.channel.id = 88888
        self.channel.mention = "<#88888>"
        self.channel.send = AsyncMock()
        self.channel.history = MagicMock(return_value = AsyncIter([]))
        self.channel.delete_messages = AsyncMock()

        self.message = Mock()
        self.message.channel = self.channel
        self.message.delete = AsyncMock()

        self.ctx: Context = Mock(spec = Context)
        self.ctx.guild = self.guild
        self.ctx.author = self.author
        self.ctx.channel = self.channel
        self.ctx.send = AsyncMock()
        self.ctx.message = self.message

        self.interaction: nextcord.Interaction = Mock(spec = nextcord.Interaction)
        self.interaction.guild = self.guild
        self.interaction.user = self.author
        self.interaction.channel = self.channel
        self.interaction.send = AsyncMock()
        self.interaction.response = Mock()
        self.interaction.response.defer = AsyncMock()

        self.client: nextcord.Client = commands.Bot()
        # chat by default; the tests of commands say otherwise
        self.client.get_context = AsyncMock(return_value = Mock(valid = False))
        self.client.fetch_channel = AsyncMock(return_value = self.channel)

        self.whodis: WhoDis = WhoDis(self.client)
        # GBot can give the role out, unless a test says otherwise
        roleProblem = patch.object(whodis_cog.server_setup, 'roleProblem', MagicMock(return_value = None))
        self.roleProblem = roleProblem.start()
        self.addCleanup(roleProblem.stop)

        # freeze time so date strings are deterministic
        self.fixed_now = datetime(2024, 5, 15, 10, 30, 0)
        self.date = self.fixed_now.strftime("%m/%d/%y %I:%M:%S %p")
        self.datetime_patcher = patch('GBotDiscord.src.whodis.whodis_cog.datetime')
        mock_datetime = self.datetime_patcher.start()
        mock_datetime.now.return_value = self.fixed_now
        mock_datetime.strptime = datetime.strptime
        self.addCleanup(self.datetime_patcher.stop)

    def _seed_game(self, initiator = None, randomUser = None, guild = None, numOnlineParticipants = 5, startTime = None, initiatorMessages = None, randomUserMessages = None):
        initiator = initiator if initiator is not None else self.author
        randomUser = randomUser if randomUser is not None else self.randomUser
        guild = guild if guild is not None else self.guild
        gameKey = f'{initiator.id}:{randomUser.id}'
        self.whodis.whoDisGames[gameKey] = {
            'startTime': startTime if startTime is not None else self.date,
            'initiator': initiator,
            'randomUser': randomUser,
            'numOnlineParticipants': numOnlineParticipants,
            'guild': guild,
            'initiatorMessages': initiatorMessages if initiatorMessages is not None else [],
            'randomUserMessages': randomUserMessages if randomUserMessages is not None else [],
        }
        return gameKey

    #region on_ready
    async def test_on_ready_starts_task(self):
        self.whodis.who_dis_timeout.start = MagicMock()
        await self.whodis.on_ready()
        self.whodis.who_dis_timeout.start.assert_called_once()

    async def test_on_ready_already_running(self):
        self.whodis.who_dis_timeout.start = MagicMock(side_effect = RuntimeError("already started"))
        await self.whodis.on_ready()
        self.whodis.who_dis_timeout.start.assert_called_once()
    #endregion

    #region on_message
    async def test_on_message_in_guild_ignored(self):
        msg = Mock()
        msg.guild = self.guild
        msg.author = self.author
        msg.content = "hi"
        await self.whodis.on_message(msg)
        # nothing happens because guild is not None
        self.author.send.assert_not_called()

    async def test_on_message_from_bot_ignored(self):
        botAuthor = Mock()
        botAuthor.bot = True
        botAuthor.id = self.author.id
        msg = Mock()
        msg.guild = None
        msg.author = botAuthor
        msg.content = "hi"
        await self.whodis.on_message(msg)
        self.author.send.assert_not_called()

    async def test_on_message_no_active_game(self):
        # private message, not a bot, but no game exists for this user
        msg = Mock()
        msg.guild = None
        msg.author = self.author
        msg.content = "hi"
        await self.whodis.on_message(msg)
        self.author.send.assert_not_called()

    async def test_on_message_command_is_not_forwarded(self):
        self._seed_game()
        self.client.get_context = AsyncMock(return_value = Mock(valid = True))
        msg = Mock()
        msg.guild = None
        msg.author = self.author
        msg.content = ".whodis guess user"
        await self.whodis.on_message(msg)
        self.randomUser.send.assert_not_called()

    async def test_on_message_chat_starting_like_a_command_is_forwarded(self):
        # only real commands stay out: "...ok" used to vanish without the sender knowing
        self._seed_game()
        msg = Mock()
        msg.guild = None
        msg.author = self.author
        msg.content = "...ok"
        msg.attachments = []
        msg.stickers = []
        await self.whodis.on_message(msg)
        self.randomUser.send.assert_called_once_with("...ok")

    async def test_on_message_longer_than_a_bot_can_send_is_split(self):
        self._seed_game()
        msg = Mock()
        msg.guild = None
        msg.author = self.author
        msg.content = 'x' * 2500
        msg.attachments = []
        msg.stickers = []
        await self.whodis.on_message(msg)
        self.assertEqual([call.args[0] for call in self.randomUser.send.call_args_list], ['x' * 2000, 'x' * 500])

    async def test_on_guild_remove_ends_that_servers_games_only(self):
        gameKey = self._seed_game()
        otherGuild = Mock(id = self.guild.id + 1)
        await self.whodis.on_guild_remove(otherGuild)
        self.assertIn(gameKey, self.whodis.whoDisGames)
        await self.whodis.on_guild_remove(self.guild)
        self.assertNotIn(gameKey, self.whodis.whoDisGames)
        assertCard(self.author.send, '🚪 Game over', 'GBot left the server this game was started from.')
        assertCard(self.randomUser.send, '🚪 Game over', 'GBot left the server this game was started from.')

    async def test_startWhoDis_random_user_dms_closed_records_nothing(self):
        # the game would otherwise hold both players and spend the cooldown until it timed out
        self.randomUser.send = AsyncMock(side_effect = nextcord.Forbidden(Mock(status = 403, reason = 'Forbidden'), 'closed'))
        started = await self.whodis.startWhoDis(self.author, self.randomUser, 5, self.guild)
        self.assertFalse(started)
        self.assertEqual(self.whodis.whoDisGames, {})
        self.assertEqual(self.whodis.whoDisCooldown, {})
        assertCard(self.author.send, '🚪 Game cancelled', 'The other player can not be messaged right now.')

    async def test_startWhoDis_initiator_dms_closed_never_tells_the_other_player(self):
        self.author.send = AsyncMock(side_effect = nextcord.Forbidden(Mock(status = 403, reason = 'Forbidden'), 'closed'))
        started = await self.whodis.startWhoDis(self.author, self.randomUser, 5, self.guild)
        self.assertFalse(started)
        self.randomUser.send.assert_not_called()
        self.assertEqual(self.whodis.whoDisCooldown, {})

    async def test_commonWhoDis_refuses_when_a_player_cannot_be_messaged(self):
        self.whodis.isServerWhoDisConfigured = MagicMock(return_value = (True, self.role))
        utils.isUserAssignedRole = MagicMock(return_value = True)
        self.whodis.getRandomWhoDisUser = AsyncMock(return_value = (self.randomUser, 5))
        self.whodis.startWhoDis = AsyncMock(return_value = False)
        self.whodis.deletePublicWhoDisMessages = AsyncMock()
        self.author.status = nextcord.Status.online
        interaction = Mock(spec = nextcord.Interaction)
        interaction.guild = self.guild
        interaction.channel = self.channel
        interaction.response = Mock(defer = AsyncMock())
        interaction.send = AsyncMock()
        await self.whodis.commonWhoDis(interaction, self.author)
        self.assertIn("private messages are closed", interaction.send.call_args.kwargs['embed'].description)

    async def test_on_message_initiator_forwards_text_to_random_user(self):
        gameKey = self._seed_game()
        msg = Mock()
        msg.guild = None
        msg.author = self.author
        msg.content = "hello stranger"
        msg.attachments = []
        msg.stickers = []
        await self.whodis.on_message(msg)
        self.randomUser.send.assert_called_once_with("hello stranger")
        self.assertEqual(self.whodis.whoDisGames[gameKey]['initiatorMessages'], [msg])

    async def test_on_message_random_user_forwards_to_initiator(self):
        gameKey = self._seed_game()
        msg = Mock()
        msg.guild = None
        msg.author = self.randomUser
        msg.content = "right back at you"
        msg.attachments = []
        msg.stickers = []
        await self.whodis.on_message(msg)
        self.author.send.assert_called_once_with("right back at you")
        self.assertEqual(self.whodis.whoDisGames[gameKey]['randomUserMessages'], [msg])

    async def test_on_message_initiator_buffer_capped(self):
        # pre-fill the initiator message buffer to NUM_MESSAGES_TO_REPORT
        existingMsgs = [Mock() for _ in range(self.whodis.NUM_MESSAGES_TO_REPORT)]
        gameKey = self._seed_game(initiatorMessages = list(existingMsgs))
        newMsg = Mock()
        newMsg.guild = None
        newMsg.author = self.author
        newMsg.content = "newest"
        newMsg.attachments = []
        newMsg.stickers = []
        await self.whodis.on_message(newMsg)
        # buffer is popped (LIFO pop removes last) before appending; still at cap
        self.assertEqual(len(self.whodis.whoDisGames[gameKey]['initiatorMessages']), self.whodis.NUM_MESSAGES_TO_REPORT)
        self.assertIn(newMsg, self.whodis.whoDisGames[gameKey]['initiatorMessages'])

    async def test_on_message_random_buffer_capped(self):
        existingMsgs = [Mock() for _ in range(self.whodis.NUM_MESSAGES_TO_REPORT)]
        gameKey = self._seed_game(randomUserMessages = list(existingMsgs))
        newMsg = Mock()
        newMsg.guild = None
        newMsg.author = self.randomUser
        newMsg.content = "newest"
        newMsg.attachments = []
        newMsg.stickers = []
        await self.whodis.on_message(newMsg)
        self.assertEqual(len(self.whodis.whoDisGames[gameKey]['randomUserMessages']), self.whodis.NUM_MESSAGES_TO_REPORT)
        self.assertIn(newMsg, self.whodis.whoDisGames[gameKey]['randomUserMessages'])

    async def test_on_message_forwards_attachments(self):
        self._seed_game()
        attachment = Mock()
        attachment.url = "http://example.com/img.png"
        msg = Mock()
        msg.guild = None
        msg.author = self.author
        msg.content = None
        msg.attachments = [attachment]
        msg.stickers = []
        await self.whodis.on_message(msg)
        self.randomUser.send.assert_called_once_with("http://example.com/img.png")

    async def test_on_message_forwards_stickers(self):
        self._seed_game()
        sticker = Mock()
        sticker.url = "http://example.com/sticker.png"
        msg = Mock()
        msg.guild = None
        msg.author = self.author
        msg.content = None
        msg.attachments = []
        msg.stickers = [sticker]
        await self.whodis.on_message(msg)
        self.randomUser.send.assert_called_once_with("http://example.com/sticker.png")

    async def test_on_message_forwards_text_and_attachments_and_stickers(self):
        self._seed_game()
        attachment = Mock()
        attachment.url = "http://example.com/img.png"
        sticker = Mock()
        sticker.url = "http://example.com/sticker.png"
        msg = Mock()
        msg.guild = None
        msg.author = self.author
        msg.content = "look at this"
        msg.attachments = [attachment]
        msg.stickers = [sticker]
        await self.whodis.on_message(msg)
        self.randomUser.send.assert_any_call("look at this")
        self.randomUser.send.assert_any_call("http://example.com/img.png")
        self.randomUser.send.assert_any_call("http://example.com/sticker.png")
        self.assertEqual(self.randomUser.send.call_count, 3)
    #endregion

    #region who_dis_timeout
    async def test_who_dis_timeout_no_games_no_cooldowns(self):
        # both dicts empty -> coroutine runs and returns without touching anything
        await self.whodis.who_dis_timeout.coro(self.whodis)
        self.author.send.assert_not_called()
        self.randomUser.send.assert_not_called()

    async def test_who_dis_timeout_game_not_yet_expired(self):
        # started 2 minutes ago, timeout is 5 minutes
        startTime = (self.fixed_now - timedelta(minutes = 2)).strftime("%m/%d/%y %I:%M:%S %p")
        gameKey = self._seed_game(startTime = startTime)
        await self.whodis.who_dis_timeout.coro(self.whodis)
        self.assertIn(gameKey, self.whodis.whoDisGames)
        self.author.send.assert_not_called()

    async def test_who_dis_timeout_game_expired(self):
        # started 6 minutes ago, timeout is 5 minutes
        startTime = (self.fixed_now - timedelta(minutes = 6)).strftime("%m/%d/%y %I:%M:%S %p")
        gameKey = self._seed_game(startTime = startTime)
        await self.whodis.who_dis_timeout.coro(self.whodis)
        self.assertNotIn(gameKey, self.whodis.whoDisGames)
        self.author.send.assert_called_once()
        self.randomUser.send.assert_called_once()

    async def test_who_dis_timeout_cooldown_not_yet_expired(self):
        # cooldown started 5 minutes ago, default cooldown is 10 minutes
        startTime = (self.fixed_now - timedelta(minutes = 5)).strftime("%m/%d/%y %I:%M:%S %p")
        self.whodis.whoDisCooldown[str(self.author.id)] = startTime
        await self.whodis.who_dis_timeout.coro(self.whodis)
        self.assertIn(str(self.author.id), self.whodis.whoDisCooldown)

    async def test_a_press_that_starts_a_game_points_to_it_from_a_server_only(self):
        # in DMs the game card arrives right below, and says itself
        config_queries.getServerValue = MagicMock(side_effect = lambda sid, key: True if key == 'toggle_who_dis' else str(self.role.id))
        utils.purgePreviousMessages = AsyncMock()
        utils.isUserAssignedRole = MagicMock(side_effect = lambda user, roleId: True)
        utils.getOnlineAndIdleUsers = AsyncMock(return_value = [self.author, self.randomUser])
        for guild, said in ((None, None), (self.guild, "🕵️ Game started. It's in your DMs with GBot.")):
            with self.subTest(inDms = guild is None):
                self.whodis.whoDisGames.clear()
                self.whodis.whoDisCooldown.clear()
                interaction = Mock(spec = nextcord.Interaction, guild = guild, channel = self.channel, user = self.author, response = Mock(defer = AsyncMock(), is_done = Mock(return_value = True)), send = AsyncMock())
                await self.whodis.commonWhoDis(interaction, self.author, self.guild)
                self.assertIn(f'{self.author.id}:{self.randomUser.id}', self.whodis.whoDisGames)
                if said is None:
                    interaction.send.assert_not_awaited()
                else:
                    self.assertEqual(interaction.send.await_args.kwargs['content'], said)

    async def test_who_dis_timeout_cooldown_expired(self):
        # cooldown started 11 minutes ago, default cooldown is 10 minutes
        startTime = (self.fixed_now - timedelta(minutes = 11)).strftime("%m/%d/%y %I:%M:%S %p")
        self.whodis.whoDisCooldown[str(self.author.id)] = startTime
        await self.whodis.who_dis_timeout.coro(self.whodis)
        self.assertNotIn(str(self.author.id), self.whodis.whoDisCooldown)

    async def test_who_dis_timeout_handles_exception(self):
        # malformed startTime causes strptime to raise; outer try/except logs and swallows
        self._seed_game(startTime = "not a date")
        # must not raise
        await self.whodis.who_dis_timeout.coro(self.whodis)
    #endregion

    #region commonWhoDis
    async def test_commonWhoDis_private_message_no_existing_game(self):
        self.ctx.guild = None
        # private message branch: cannot start a game outside a guild
        await self.whodis.commonWhoDis(self.ctx, self.author)
        assertErrorCard(self.ctx.send, f'Sorry {self.author.mention}, Who Dis games must be started in a server.')

    async def test_commonWhoDis_existing_game_is_refused_not_ended(self):
        # checked under the start lock, so a second quick press of Start can't end the game the first made
        gameKey = self._seed_game()
        await self.whodis.commonWhoDis(self.ctx, self.author)
        self.assertIn(gameKey, self.whodis.whoDisGames)
        self.assertIn("you're already in a game, which ends", self.ctx.send.await_args.kwargs['embed'].description)
        self.randomUser.send.assert_not_awaited()

    async def test_commonWhoDis_not_configured_no_role_id(self):
        # configured returns (False, None)
        config_queries.getServerValue = MagicMock(return_value = None)
        utils.sendMessageToAdmins = AsyncMock()
        utils.purgePreviousMessages = AsyncMock()
        await self.whodis.commonWhoDis(self.ctx, self.author)
        self.ctx.send.assert_any_call('Who Dis not started.')
        assertErrorCard(self.author.send, f'Sorry {self.author.mention}, Who Dis is not configured in this server.')
        utils.sendMessageToAdmins.assert_called_once()

    async def test_commonWhoDis_not_configured_role_not_present(self):
        # role_who_dis returns an id that isn't in guild.roles; isWhoDisEnabled returns True
        config_queries.getServerValue = MagicMock(side_effect = lambda sid, key: True if key == 'toggle_who_dis' else 'missing-role-id')
        self.guild.roles = []
        utils.sendMessageToAdmins = AsyncMock()
        utils.purgePreviousMessages = AsyncMock()
        await self.whodis.commonWhoDis(self.ctx, self.author)
        assertErrorCard(self.author.send, f'Sorry {self.author.mention}, Who Dis is not configured in this server.')

    async def test_commonWhoDis_author_offline(self):
        config_queries.getServerValue = MagicMock(side_effect = lambda sid, key: True if key == 'toggle_who_dis' else str(self.role.id))
        utils.purgePreviousMessages = AsyncMock()
        self.author.status = nextcord.Status.offline
        await self.whodis.commonWhoDis(self.ctx, self.author)
        self.ctx.send.assert_any_call('Who Dis not started.')
        assertErrorCard(self.author.send, f"Sorry {self.author.mention}, you need to be online to start Who Dis games.")

    async def test_commonWhoDis_role_add_success(self):
        config_queries.getServerValue = MagicMock(side_effect = lambda sid, key: True if key == 'toggle_who_dis' else str(self.role.id))
        utils.purgePreviousMessages = AsyncMock()
        # author is not assigned the role -> code path adds it
        self.author.roles = []
        utils.isUserAssignedRole = MagicMock(side_effect = lambda user, roleId: user is not self.author)
        utils.addRoleToUser = AsyncMock(return_value = True)
        utils.getOnlineAndIdleUsers = AsyncMock(return_value = [self.author, self.randomUser])
        await self.whodis.commonWhoDis(self.ctx, self.author)
        utils.addRoleToUser.assert_called_once_with(self.author, self.role)
        # counted before they joined, so their first game counts them too, as its reward does
        self.assertEqual(self.whodis.whoDisGames[f'{self.author.id}:{self.randomUser.id}']['numOnlineParticipants'], 2)
        self.author.send.assert_any_call(f"❓ You've joined Who Dis in **{self.guild.name}**. Please follow its rules, and leave any time from `/whodis`.")
        self.ctx.send.assert_any_call('Who Dis starting...')

    async def test_commonWhoDis_role_add_fails(self):
        config_queries.getServerValue = MagicMock(side_effect = lambda sid, key: True if key == 'toggle_who_dis' else str(self.role.id))
        utils.purgePreviousMessages = AsyncMock()
        utils.sendMessageToAdmins = AsyncMock()
        self.author.roles = []
        utils.isUserAssignedRole = MagicMock(side_effect = lambda user, roleId: user is not self.author)
        utils.addRoleToUser = AsyncMock(return_value = False)
        utils.getOnlineAndIdleUsers = AsyncMock(return_value = [self.author, self.randomUser])
        await self.whodis.commonWhoDis(self.ctx, self.author)
        self.ctx.send.assert_any_call('Who Dis not started.')
        assertErrorCard(self.author.send, f"Sorry {self.author.mention}, there was a problem opting you into Who Dis in **{self.guild.name}**.")
        utils.sendMessageToAdmins.assert_called_once()

    async def test_commonWhoDis_role_gbot_cannot_give_out(self):
        config_queries.getServerValue = MagicMock(side_effect = lambda sid, key: True if key == 'toggle_who_dis' else str(self.role.id))
        utils.purgePreviousMessages = AsyncMock()
        utils.sendMessageToAdmins = AsyncMock()
        utils.isUserAssignedRole = MagicMock(side_effect = lambda user, roleId: user is not self.author)
        utils.addRoleToUser = AsyncMock()
        utils.getOnlineAndIdleUsers = AsyncMock(return_value = [self.author, self.randomUser])
        self.roleProblem.return_value = 'Move **GBot** above it.'
        await self.whodis.commonWhoDis(self.ctx, self.author)
        utils.addRoleToUser.assert_not_called()
        assertErrorCard(self.author.send, f"Sorry {self.author.mention}, GBot can't give out this server's Who Dis role yet. The admins have been told how to fix it.")
        utils.sendMessageToAdmins.assert_called_once_with(self.client, str(self.guild.id), f"{self.author.mention} couldn't join or leave Who Dis games. Move **GBot** above it.", self.whodis.logger)

    async def test_commonWhoDis_cooldown_active_raises(self):
        config_queries.getServerValue = MagicMock(side_effect = lambda sid, key: True if key == 'toggle_who_dis' else str(self.role.id))
        utils.purgePreviousMessages = AsyncMock()
        utils.isUserAssignedRole = MagicMock(return_value = True)
        # cooldown started 1 minute ago, default is 10 minutes -> still active
        startTime = (self.fixed_now - timedelta(minutes = 1)).strftime("%m/%d/%y %I:%M:%S %p")
        self.whodis.whoDisCooldown[str(self.author.id)] = startTime
        with self.assertRaises(CustomCommandOnCooldown):
            await self.whodis.commonWhoDis(self.ctx, self.author)
        self.ctx.send.assert_any_call('Who Dis not started.')

    async def test_a_refused_start_changes_nothing(self):
        # out of Who Dis, as after a Leave: refused for the cooldown or for nobody to play with, they stay out
        config_queries.getServerValue = MagicMock(side_effect = lambda sid, key: True if key == 'toggle_who_dis' else str(self.role.id))
        utils.purgePreviousMessages = AsyncMock()
        utils.isUserAssignedRole = MagicMock(side_effect = lambda user, roleId: user is not self.author)
        utils.addRoleToUser = AsyncMock(return_value = True)
        utils.getOnlineAndIdleUsers = AsyncMock(return_value = [self.author])
        await self.whodis.commonWhoDis(self.ctx, self.author)
        self.whodis.whoDisCooldown[str(self.author.id)] = (self.fixed_now - timedelta(minutes = 1)).strftime("%m/%d/%y %I:%M:%S %p")
        with self.assertRaises(CustomCommandOnCooldown):
            await self.whodis.commonWhoDis(self.ctx, self.author)
        utils.addRoleToUser.assert_not_called()
        self.assertNotIn("You've joined", str(self.author.send.call_args_list))

    async def test_a_press_that_joins_says_so_in_its_one_reply(self):
        config_queries.getServerValue = MagicMock(side_effect = lambda sid, key: True if key == 'toggle_who_dis' else str(self.role.id))
        utils.purgePreviousMessages = AsyncMock()
        utils.addRoleToUser = AsyncMock(return_value = True)
        utils.getOnlineAndIdleUsers = AsyncMock(return_value = [self.author, self.randomUser])
        joined = f"❓ You've joined Who Dis in **{self.guild.name}**. Please follow its rules, and leave any time from `/whodis`."
        for guild, said in ((self.guild, f'{joined} Your game is in your DMs.'), (None, joined)):
            with self.subTest(inDms = guild is None):
                self.whodis.whoDisGames.clear()
                self.whodis.whoDisCooldown.clear()
                self.author.send.reset_mock()
                utils.isUserAssignedRole = MagicMock(side_effect = lambda user, roleId: user is not self.author)
                interaction = Mock(spec = nextcord.Interaction, guild = guild, channel = self.channel, user = self.author, response = Mock(defer = AsyncMock(), is_done = Mock(return_value = True)), send = AsyncMock())
                await self.whodis.commonWhoDis(interaction, self.author, self.guild)
                interaction.send.assert_awaited_once()
                self.assertEqual(interaction.send.await_args.kwargs['content'], said)
                self.assertTrue(interaction.send.await_args.kwargs['ephemeral'])
                # nothing apart from the game card itself
                self.assertNotIn("You've joined", str(self.author.send.call_args_list))

    async def test_commonWhoDis_no_available_users(self):
        config_queries.getServerValue = MagicMock(side_effect = lambda sid, key: True if key == 'toggle_who_dis' else str(self.role.id))
        utils.purgePreviousMessages = AsyncMock()
        utils.isUserAssignedRole = MagicMock(return_value = True)
        utils.getOnlineAndIdleUsers = AsyncMock(return_value = [])
        await self.whodis.commonWhoDis(self.ctx, self.author)
        self.ctx.send.assert_any_call('Who Dis not started.')
        assertErrorCard(self.author.send, f'Sorry {self.author.mention}, there are currently no users available for Who Dis.')

    async def test_commonWhoDis_success_starts_new_game(self):
        config_queries.getServerValue = MagicMock(side_effect = lambda sid, key: True if key == 'toggle_who_dis' else str(self.role.id))
        utils.purgePreviousMessages = AsyncMock()
        # author is already assigned the role
        utils.isUserAssignedRole = MagicMock(side_effect = lambda user, roleId: True)
        utils.getOnlineAndIdleUsers = AsyncMock(return_value = [self.author, self.randomUser])
        await self.whodis.commonWhoDis(self.ctx, self.author)
        self.ctx.send.assert_any_call('Who Dis starting...')
        # game registered with the expected key
        expectedKey = f'{self.author.id}:{self.randomUser.id}'
        self.assertIn(expectedKey, self.whodis.whoDisGames)
        # cooldown set for initiator
        self.assertIn(str(self.author.id), self.whodis.whoDisCooldown)

    # A private slash reply does what the prefix path needs a deleted line and a DM for, and it also
    # reaches someone whose DMs are closed.
    async def test_commonWhoDis_slash_refusal_is_a_private_reply_with_no_public_line(self):
        config_queries.getServerValue = MagicMock(side_effect = lambda sid, key: True if key == 'toggle_who_dis' else 777)
        utils.isUserAssignedRole = MagicMock(return_value = True)
        utils.purgePreviousMessages = AsyncMock()
        self.whodis.getRandomWhoDisUser = AsyncMock(return_value = (None, None))
        self.whodis.isServerWhoDisConfigured = MagicMock(return_value = (True, Mock(id = 777)))
        self.author.status = nextcord.Status.online
        self.interaction.send = AsyncMock()
        await self.whodis.commonWhoDis(self.interaction, self.author)
        self.interaction.response.defer.assert_called_once_with(ephemeral = True)
        assertErrorCard(self.interaction.send, f'Sorry {self.author.mention}, there are currently no users available for Who Dis.')
        self.assertTrue(self.interaction.send.call_args.kwargs['ephemeral'])
        self.author.send.assert_not_called()

    async def test_commonWhoDis_slash_cooldown_posts_no_public_line(self):
        config_queries.getServerValue = MagicMock(side_effect = lambda sid, key: True if key == 'toggle_who_dis' else 777)
        utils.isUserAssignedRole = MagicMock(return_value = True)
        utils.purgePreviousMessages = AsyncMock()
        self.whodis.isServerWhoDisConfigured = MagicMock(return_value = (True, Mock(id = 777)))
        self.author.status = nextcord.Status.online
        self.interaction.send = AsyncMock()
        startTime = (self.fixed_now - timedelta(minutes = 1)).strftime("%m/%d/%y %I:%M:%S %p")
        self.whodis.whoDisCooldown[str(self.author.id)] = startTime
        with self.assertRaises(CustomCommandOnCooldown):
            await self.whodis.commonWhoDis(self.interaction, self.author)
        self.interaction.send.assert_not_called()

    async def test_commonWhoDis_interaction_defers(self):
        # existing game -> cancel path; ensures interaction.response.defer is awaited
        self._seed_game()
        await self.whodis.commonWhoDis(self.interaction, self.author)
        self.interaction.response.defer.assert_called_once()

    # A-15: isPrivateMessage and deleteMsgs were bound after the deferral, so a deferral that
    # failed left them unbound and the finally block raised UnboundLocalError over the real error.
    async def test_commonWhoDis_failed_defer_surfaces_the_real_error(self):
        self._seed_game()
        self.interaction.response.defer = AsyncMock(side_effect = RuntimeError('defer failed'))
        with self.assertRaises(RuntimeError) as raised:
            await self.whodis.commonWhoDis(self.interaction, self.author)
        self.assertEqual(str(raised.exception), 'defer failed')
    #endregion

    #region commonLeaveDis
    async def test_commonLeaveDis_not_configured(self):
        config_queries.getServerValue = MagicMock(return_value = None)
        utils.sendMessageToAdmins = AsyncMock()
        await self.whodis.commonLeaveDis(self.ctx, self.author)
        assertErrorCard(self.ctx.send, f'Sorry {self.author.mention}, Who Dis is not configured in this server.')
        utils.sendMessageToAdmins.assert_called_once()

    async def test_commonLeaveDis_role_assigned_removes(self):
        config_queries.getServerValue = MagicMock(side_effect = lambda sid, key: True if key == 'toggle_who_dis' else str(self.role.id))
        utils.isUserAssignedRole = MagicMock(return_value = True)
        await self.whodis.commonLeaveDis(self.ctx, self.author)
        self.author.remove_roles.assert_called_once_with(self.role)
        self.assertIn((f"👋 You've left Who Dis in **{self.guild.name}**."), [call.kwargs.get('content') for call in self.ctx.send.call_args_list])

    async def test_leaving_ends_your_game_in_that_server(self):
        # as End would, and the other player is told they left, with Play again
        config_queries.getServerValue = MagicMock(side_effect = lambda sid, key: True if key == 'toggle_who_dis' else str(self.role.id))
        utils.isUserAssignedRole = MagicMock(return_value = True)
        gameKey = self._seed_game()
        await self.whodis.commonLeaveDis(self.ctx, self.author)
        self.assertNotIn(gameKey, self.whodis.whoDisGames)
        self.assertIn(f"👋 You've left Who Dis in **{self.guild.name}**, and your game is over.", [call.kwargs.get('content') for call in self.ctx.send.call_args_list])
        # the leaver's reply says it, so no second card for them
        self.author.send.assert_not_called()
        assertCard(self.randomUser.send, '🚪 Game cancelled', 'The other player left. No hard feelings.')
        self.assertEqual(self.randomUser.send.await_args.kwargs['view'].children[0].custom_id, f'whodis:start:{self.guild.id}')
        # a game from another server goes on
        other = Mock(id = 4242)
        gameKey = self._seed_game(guild = other)
        await self.whodis.commonLeaveDis(self.ctx, self.author)
        self.assertIn(gameKey, self.whodis.whoDisGames)

    async def test_every_ending_offers_play_again_for_its_server(self):
        # the same lasting Start the Who Dis card has, so a press goes through every check of a start
        guild = Mock(id = 77)
        for end in ('timeout', 'right', 'wrong', 'cancel'):
            with self.subTest(end = end):
                self.author.send.reset_mock()
                self.randomUser.send.reset_mock()
                gameKey = self._seed_game(guild = guild)
                context = Mock(send = AsyncMock())
                if end == 'timeout':
                    await self.whodis.timeoutWhoDis(gameKey)
                    sends = [self.author.send, self.randomUser.send]
                elif end == 'cancel':
                    await self.whodis.cancelWhoDis(context, True, self.author, [], gameKey)
                    sends = [context.send, self.randomUser.send]
                else:
                    with patch.object(whodis_cog.GBotFirebaseService, 'run', AsyncMock(return_value = 5)):
                        await self.whodis.guessWhoDis(context, self.author, [self.author.id, self.randomUser.id if end == 'right' else 0], gameKey)
                    sends = [context.send, self.randomUser.send]
                for send in sends:
                    view = send.await_args.kwargs['view']
                    self.assertEqual([(item.label, item.custom_id) for item in view.children], [('Play again', 'whodis:start:77')])
                    self.assertTrue(view.is_finished())
        # GBot gone from the server, so there is nothing to play again
        gameKey = self._seed_game()
        await self.whodis.notifyPlayers((self.author,), '🚪 Game over', 'GBot left the server this game was started from.', gameKey)
        self.assertNotIn('view', self.author.send.await_args.kwargs)

    async def test_commonLeaveDis_role_gbot_cannot_take_away(self):
        config_queries.getServerValue = MagicMock(side_effect = lambda sid, key: True if key == 'toggle_who_dis' else str(self.role.id))
        utils.isUserAssignedRole = MagicMock(return_value = True)
        utils.sendMessageToAdmins = AsyncMock()
        self.roleProblem.return_value = 'Move **GBot** above it.'
        await self.whodis.commonLeaveDis(self.ctx, self.author)
        self.author.remove_roles.assert_not_called()
        assertErrorCard(self.ctx.send, f"Sorry {self.author.mention}, GBot can't take this server's Who Dis role away yet. The admins have been told how to fix it.")
        utils.sendMessageToAdmins.assert_called_once_with(self.client, self.guild.id, f"{self.author.mention} couldn't join or leave Who Dis games. Move **GBot** above it.", self.whodis.logger)

    async def test_commonLeaveDis_role_not_assigned(self):
        config_queries.getServerValue = MagicMock(side_effect = lambda sid, key: True if key == 'toggle_who_dis' else str(self.role.id))
        utils.isUserAssignedRole = MagicMock(return_value = False)
        await self.whodis.commonLeaveDis(self.ctx, self.author)
        self.author.remove_roles.assert_not_called()
        assertErrorCard(self.ctx.send, f"Sorry {self.author.mention}, you're not in Who Dis in **{self.guild.name}**.")
    #endregion

    #region commonDis
    async def test_commonDis_no_active_game(self):
        await self.whodis.commonDis(self.ctx, self.author, self.randomUser.name)
        assertErrorCard(self.ctx.send, f'Sorry {self.author.mention}, there is currently no active Who Dis game.')

    async def test_commonDis_user_not_found(self):
        self._seed_game()
        utils.getUserIdFromName = AsyncMock(return_value = None)
        await self.whodis.commonDis(self.ctx, self.author, "nobody")
        assertErrorCard(self.ctx.send, f'Sorry {self.author.mention}, please provide the name of a user in the server in which the Who Dis game was started. Nicknames are not supported.')

    async def test_commonDis_correct_guess(self):
        gameKey = self._seed_game()
        utils.getUserIdFromName = AsyncMock(return_value = self.randomUser.id)
        leaderboards_queries.incrementUserNumValue = MagicMock()
        gcoin_queries.performTransaction = MagicMock()
        await self.whodis.commonDis(self.ctx, self.author, self.randomUser.name)
        # game is removed
        self.assertNotIn(gameKey, self.whodis.whoDisGames)
        # leaderboard updated
        leaderboards_queries.incrementUserNumValue.assert_called_once_with(self.author.id, self.author.name, 'numWhoDisWins')
        # reward calculated: 5 participants * 50.00 = 250.00
        gcoin_queries.performTransaction.assert_called_once()
        # author got the correct-guess DM
        assertCard(self.ctx.send, '🎉 You got them!', f"It was {self.randomUser.mention} all along! You won 250.00 GCoin!")
        # randomUser got the figured-out DM
        assertCard(self.randomUser.send, "👀 You've been found!", 'They figured out it was you. Nicely played, the game is over.')

    async def test_commonDis_incorrect_guess(self):
        gameKey = self._seed_game()
        # user guesses some unrelated user id
        utils.getUserIdFromName = AsyncMock(return_value = self.otherUser.id)
        leaderboards_queries.incrementUserNumValue = MagicMock()
        gcoin_queries.performTransaction = MagicMock()
        await self.whodis.commonDis(self.ctx, self.author, self.otherUser.name)
        self.assertNotIn(gameKey, self.whodis.whoDisGames)
        leaderboards_queries.incrementUserNumValue.assert_not_called()
        gcoin_queries.performTransaction.assert_not_called()
        assertCard(self.ctx.send, '❌ Wrong guess', "It wasn't them, and the mystery lives on. The game is over.")
        assertCard(self.randomUser.send, '😏 They guessed wrong', 'Your secret is safe. The game is over.')

    async def test_commonDis_interaction_defers(self):
        await self.whodis.commonDis(self.interaction, self.author, self.randomUser.name)
        self.interaction.response.defer.assert_called_once()
    #endregion

    #region commonReport
    #endregion

    #region isServerWhoDisConfigured
    def test_isServerWhoDisConfigured_no_role_id(self):
        config_queries.getServerValue = MagicMock(return_value = None)
        result = self.whodis.isServerWhoDisConfigured(self.guild)
        self.assertEqual(result, (False, None))

    def test_isServerWhoDisConfigured_role_id_not_in_guild_roles(self):
        config_queries.getServerValue = MagicMock(side_effect = lambda sid, key: True if key == 'toggle_who_dis' else 'unknown')
        self.guild.roles = []
        result = self.whodis.isServerWhoDisConfigured(self.guild)
        self.assertEqual(result, (False, None))

    def test_isServerWhoDisConfigured_enabled_and_role_present(self):
        config_queries.getServerValue = MagicMock(side_effect = lambda sid, key: True if key == 'toggle_who_dis' else str(self.role.id))
        result = self.whodis.isServerWhoDisConfigured(self.guild)
        self.assertEqual(result, (True, self.role))

    def test_isServerWhoDisConfigured_role_present_but_disabled(self):
        config_queries.getServerValue = MagicMock(side_effect = lambda sid, key: False if key == 'toggle_who_dis' else str(self.role.id))
        result = self.whodis.isServerWhoDisConfigured(self.guild)
        self.assertEqual(result, (False, self.role))
    #endregion

    #region getRandomWhoDisUser
    async def test_getRandomWhoDisUser_no_candidates(self):
        # no online users have the role
        utils.getOnlineAndIdleUsers = AsyncMock(return_value = [])
        result = await self.whodis.getRandomWhoDisUser(self.author.id, self.guild, self.role)
        self.assertEqual(result, (None, None))

    async def test_getRandomWhoDisUser_only_self_is_candidate(self):
        # only the initiator has the role -> no available pairing
        utils.getOnlineAndIdleUsers = AsyncMock(return_value = [self.author])
        utils.isUserAssignedRole = MagicMock(return_value = True)
        result = await self.whodis.getRandomWhoDisUser(self.author.id, self.guild, self.role)
        self.assertEqual(result, (None, None))

    async def test_getRandomWhoDisUser_picks_other_user(self):
        utils.getOnlineAndIdleUsers = AsyncMock(return_value = [self.author, self.randomUser])
        utils.isUserAssignedRole = MagicMock(return_value = True)
        result = await self.whodis.getRandomWhoDisUser(self.author.id, self.guild, self.role)
        self.assertEqual(result, (self.randomUser, 2))

    async def test_getRandomWhoDisUser_skips_user_already_in_game(self):
        # randomUser is already in an active game with someone else
        otherInitiator = Mock()
        otherInitiator.id = 11111
        self.whodis.whoDisGames[f'{otherInitiator.id}:{self.randomUser.id}'] = {'placeholder': True}
        utils.getOnlineAndIdleUsers = AsyncMock(return_value = [self.author, self.randomUser])
        utils.isUserAssignedRole = MagicMock(return_value = True)
        result = await self.whodis.getRandomWhoDisUser(self.author.id, self.guild, self.role)
        # no eligible pairing; numOnlineParticipants still counts randomUser (has the role)
        self.assertEqual(result, (None, None))
    #endregion

    #region getWhoDisGameKey
    def test_getWhoDisGameKey_found(self):
        gameKey = self._seed_game()
        result = self.whodis.getWhoDisGameKey(self.author.id)
        self.assertEqual(result, gameKey)

    def test_getWhoDisGameKey_not_found(self):
        result = self.whodis.getWhoDisGameKey(self.author.id)
        self.assertIsNone(result)

    def test_getWhoDisGameKey_substring_id_does_not_match(self):
        # Regression for A-7: the lookup used `str(userId) in gameKey`, so an id that is a
        # substring of a participant's id falsely matched. 4321 is a substring of 54321.
        self._seed_game()
        self.assertIsNone(self.whodis.getWhoDisGameKey(4321))

    async def test_guessWhoDis_substring_id_is_not_a_correct_guess(self):
        # Regression for A-7: the win check matched ids as substrings of the game key too,
        # so guessing a user whose id is contained in a participant's id counted as correct.
        gameKey = self._seed_game()
        self.whodis.rewardGuesser = MagicMock(return_value = Decimal('50.00'))
        leaderboards_queries.incrementUserNumValue = MagicMock()
        # randomUser.id is 12345; 1234 is a substring of it but a different user
        await self.whodis.guessWhoDis(self.ctx, self.author, [self.author.id, 1234], gameKey)
        leaderboards_queries.incrementUserNumValue.assert_not_called()
        self.whodis.rewardGuesser.assert_not_called()
        assertCard(self.ctx.send, '❌ Wrong guess', "It wasn't them, and the mystery lives on. The game is over.")
    #endregion

    #region startWhoDis
    async def test_startWhoDis_state_set_and_dms_sent(self):
        await self.whodis.startWhoDis(self.author, self.randomUser, 5, self.guild)
        expectedKey = f'{self.author.id}:{self.randomUser.id}'
        self.assertIn(expectedKey, self.whodis.whoDisGames)
        # cooldown registered for initiator
        self.assertEqual(self.whodis.whoDisCooldown[str(self.author.id)], self.date)
        # game payload populated correctly
        game = self.whodis.whoDisGames[expectedKey]
        self.assertEqual(game['initiator'], self.author)
        self.assertEqual(game['randomUser'], self.randomUser)
        self.assertEqual(game['numOnlineParticipants'], 5)
        self.assertEqual(game['guild'], self.guild)
        self.assertEqual(game['initiatorMessages'], [])
        self.assertEqual(game['randomUserMessages'], [])
        # both users got start DMs
        self.author.send.assert_called_once()
        self.randomUser.send.assert_called_once()
    #endregion

    #region cancelWhoDis
    async def test_cancelWhoDis_author_is_initiator_guild_context(self):
        gameKey = self._seed_game()
        deleteMsgs = []
        await self.whodis.cancelWhoDis(self.ctx, False, self.author, deleteMsgs, gameKey)
        self.assertNotIn(gameKey, self.whodis.whoDisGames)
        assertCard(self.author.send, '🚪 Game cancelled', 'You cancelled the game.')
        assertCard(self.randomUser.send, '🚪 Game cancelled', 'The other player left. No hard feelings.')
        self.ctx.send.assert_called_once_with('Who Dis cancelled.')

    async def test_cancelling_from_the_card_in_a_server_says_nothing_more(self):
        # the card turns back to Start, and the DM says it's cancelled
        gameKey = self._seed_game()
        self.interaction.send = AsyncMock()
        deleteMsgs = []
        await self.whodis.cancelWhoDis(self.interaction, False, self.author, deleteMsgs, gameKey)
        assertCard(self.author.send, '🚪 Game cancelled', 'You cancelled the game.')
        self.interaction.send.assert_not_awaited()
        self.assertEqual(deleteMsgs, [])

    async def test_cancelWhoDis_author_is_random_user_private(self):
        gameKey = self._seed_game()
        deleteMsgs = []
        # author is randomUser, context is private message (no guild echo)
        privCtx = Mock()
        privCtx.send = AsyncMock()
        await self.whodis.cancelWhoDis(privCtx, True, self.randomUser, deleteMsgs, gameKey)
        self.assertNotIn(gameKey, self.whodis.whoDisGames)
        # canceller is told via the context (private message), not author DM
        assertCard(privCtx.send, '🚪 Game cancelled', 'You cancelled the game.')
        # the other party (initiator) is notified
        assertCard(self.author.send, '🚪 Game cancelled', 'The other player left. No hard feelings.')
    #endregion

    #region timeoutWhoDis
    # a closed DM used to raise before the second player was ever told
    async def test_timeoutWhoDis_closed_dms_do_not_cost_the_other_player_the_notice(self):
        gameKey = self._seed_game()
        self.whodis.logger = MagicMock()
        self.author.send = AsyncMock(side_effect = Exception('Cannot send messages to this user'))
        await self.whodis.timeoutWhoDis(gameKey)
        self.assertNotIn(gameKey, self.whodis.whoDisGames)
        self.randomUser.send.assert_awaited_once()
        self.whodis.logger.error.assert_called_once()

    async def test_timeoutWhoDis_pops_game_and_notifies_both(self):
        gameKey = self._seed_game()
        await self.whodis.timeoutWhoDis(gameKey)
        self.assertNotIn(gameKey, self.whodis.whoDisGames)
        assertCard(self.author.send, "⏰ Time's up", 'Nobody guessed in time, so the mystery lives on. The game is over.')
        assertCard(self.randomUser.send, "⏰ Time's up", 'Nobody guessed in time, so the mystery lives on. The game is over.')
    #endregion

    #region rewardGuesser
    def test_rewardGuesser_below_max_participants(self):
        gcoin_queries.performTransaction = MagicMock()
        result = self.whodis.rewardGuesser(self.author, 5)
        # 5 * 50.00 = 250.00
        self.assertEqual(result, Decimal('250.00'))
        gcoin_queries.performTransaction.assert_called_once_with(
            Decimal('250.00'),
            self.date,
            {'id': None, 'name': 'Who Dis'},
            {'id': self.author.id, 'name': self.author.name},
            '',
            'Guessed User',
            False,
            False
        )

    def test_rewardGuesser_at_or_above_max_participants(self):
        gcoin_queries.performTransaction = MagicMock()
        result = self.whodis.rewardGuesser(self.author, self.whodis.NUM_PARTICIPANTS_FOR_MAX_REWARD)
        self.assertEqual(result, self.whodis.MAX_REWARD_GCOIN)
        gcoin_queries.performTransaction.assert_called_once()
    #endregion

    #region deletePublicWhoDisMessages
    async def test_deletePublicWhoDisMessages_empty_list_noop(self):
        utils.purgePreviousMessages = AsyncMock()
        await self.whodis.deletePublicWhoDisMessages(self.guild.id, [], self.channel)
        utils.purgePreviousMessages.assert_not_called()

    async def test_deletePublicWhoDisMessages_none_list_noop(self):
        utils.purgePreviousMessages = AsyncMock()
        await self.whodis.deletePublicWhoDisMessages(self.guild.id, None, self.channel)
        utils.purgePreviousMessages.assert_not_called()

    async def test_deletePublicWhoDisMessages_success(self):
        utils.purgePreviousMessages = AsyncMock()
        msgs = [Mock()]
        await self.whodis.deletePublicWhoDisMessages(self.guild.id, msgs, self.channel)
        utils.purgePreviousMessages.assert_called_once_with(msgs, self.channel)

    async def test_deletePublicWhoDisMessages_purge_fails(self):
        utils.purgePreviousMessages = AsyncMock(side_effect = Exception("perm denied"))
        utils.sendMessageToAdmins = AsyncMock()
        msgs = [Mock()]
        # must not raise; failures are reported to admins
        await self.whodis.deletePublicWhoDisMessages(self.guild.id, msgs, self.channel)
        utils.sendMessageToAdmins.assert_called_once()
    #endregion



    def test_isServerWhoDisConfigured_iterates_past_non_matching_role(self):
        # roleId matches the second role -> for-loop hits the `False → next iteration` branch on role 1
        otherRole = Mock()
        otherRole.id = 11111
        self.guild.roles = [otherRole, self.role]
        config_queries.getServerValue = MagicMock(side_effect = lambda sid, key: True if key == 'toggle_who_dis' else str(self.role.id))
        result = self.whodis.isServerWhoDisConfigured(self.guild)
        self.assertEqual(result, (True, self.role))

    async def test_getRandomWhoDisUser_skips_users_without_role(self):
        # one online user has the role and one doesn't — covers the `if isUserAssignedRole False -> next iter` branch
        utils.getOnlineAndIdleUsers = AsyncMock(return_value = [self.author, self.randomUser])
        utils.isUserAssignedRole = MagicMock(side_effect = lambda user, roleId: user is self.randomUser)
        result = await self.whodis.getRandomWhoDisUser(self.author.id, self.guild, self.role)
        # only randomUser has the role, so it's picked; numOnlineParticipants == 1
        self.assertEqual(result, (self.randomUser, 1))

    def test_getWhoDisGameKey_iterates_past_non_matching(self):
        # two games — the first doesn't include the userId, the second does. exercises the
        # `if str(userId) in gameKey False -> next iter` branch.
        targetKey = self._seed_game()
        self.whodis.whoDisGames['9999:8888'] = {'placeholder': True}
        # rebuild the dict so the non-matching key is first
        self.whodis.whoDisGames = {'9999:8888': {'placeholder': True}, targetKey: self.whodis.whoDisGames[targetKey]}
        result = self.whodis.getWhoDisGameKey(self.author.id)
        self.assertEqual(result, targetKey)

    async def test_commonDis_reward_runs_off_the_event_loop(self):
        from GBotDiscord.src.gcoin import gcoin_queries
        self._seed_game()
        threads = []
        def record(*args):
            threads.append(threading.current_thread())
        utils.getUserIdFromName = AsyncMock(return_value = self.randomUser.id)
        with patch.object(gcoin_queries, 'performTransaction', new = record), patch.object(leaderboards_queries, 'incrementUserNumValue', new = record):
            await self.whodis.commonDis(self.ctx, self.author, self.randomUser.name)
        self.assertEqual(len(threads), 2)
        self.assertTrue(all(thread is not threading.main_thread() for thread in threads))

    async def test_commonDis_guessing_your_own_name_wins_nothing(self):
        # both ids are in the game key, so checking only the key paid a reward for this
        from GBotDiscord.src.gcoin import gcoin_queries
        gameKey = self._seed_game()
        utils.getUserIdFromName = AsyncMock(return_value = self.author.id)
        leaderboards_queries.incrementUserNumValue = MagicMock()
        gcoin_queries.performTransaction = MagicMock()
        await self.whodis.commonDis(self.ctx, self.author, self.author.name)
        gcoin_queries.performTransaction.assert_not_called()
        leaderboards_queries.incrementUserNumValue.assert_not_called()
        assertCard(self.ctx.send, '❌ Wrong guess', "It wasn't them, and the mystery lives on. The game is over.")
        self.assertNotIn(gameKey, self.whodis.whoDisGames)

    async def test_commonDis_wrong_guess_by_random_user_tells_the_initiator(self):
        # the notice always went to randomUser, so here the guesser got it and the other player nothing
        self._seed_game()
        utils.getUserIdFromName = AsyncMock(return_value = self.otherUser.id)
        randomCtx = Mock()
        randomCtx.send = AsyncMock()
        await self.whodis.commonDis(randomCtx, self.randomUser, self.otherUser.name)
        assertCard(self.author.send, '😏 They guessed wrong', 'Your secret is safe. The game is over.')
        self.randomUser.send.assert_not_called()

    async def test_on_message_report_buffer_keeps_the_latest_messages(self):
        # a report promises the last messages, and this was dropping the newest of them instead
        existingMsgs = [Mock() for _ in range(self.whodis.NUM_MESSAGES_TO_REPORT)]
        gameKey = self._seed_game(initiatorMessages = list(existingMsgs))
        newMsg = Mock()
        newMsg.guild = None
        newMsg.author = self.author
        newMsg.content = 'latest'
        newMsg.attachments = []
        newMsg.stickers = []
        await self.whodis.on_message(newMsg)
        self.assertEqual(self.whodis.whoDisGames[gameKey]['initiatorMessages'], existingMsgs[1:] + [newMsg])

    async def test_commonDis_correct_guess_by_random_user_other_is_initiator(self):
        # exercises the else branch in commonGuess that sets otherUser = initiator (lines 499-500)
        from GBotDiscord.src.gcoin import gcoin_queries
        gameKey = self._seed_game()
        # author (test setUp's author) is the initiator. swap context so randomUser is the guesser.
        randomCtx = Mock()
        randomCtx.guild = None
        randomCtx.send = AsyncMock()
        # the randomUser names the initiator (author) — this guess is correct
        utils.getUserIdFromName = AsyncMock(return_value = self.author.id)
        gcoin_queries.performTransaction = MagicMock()
        utils.isUrlImageContentTypeAndStatus200 = AsyncMock(return_value = True)

        await self.whodis.commonDis(randomCtx, self.randomUser, self.author.name)

        # the initiator was DM'd as "otherUser"
        assertCard(self.author.send, "👀 You've been found!", 'They figured out it was you. Nicely played, the game is over.')
        self.assertNotIn(gameKey, self.whodis.whoDisGames)

    def test_setup_adds_cog(self):
        from GBotDiscord.src.whodis import whodis_cog
        client = MagicMock()
        whodis_cog.setup(client)
        client.add_cog.assert_called_once()
        addedCog = client.add_cog.call_args[0][0]
        self.assertIsInstance(addedCog, WhoDis)

    #region the /whodis card and the game card's buttons
    def press(self, user = None, guild = 'default', customId = None):
        interaction = Mock(spec = nextcord.Interaction)
        interaction.user = user or self.author
        interaction.guild = self.guild if guild == 'default' else guild
        interaction.channel = self.channel
        interaction.type = nextcord.InteractionType.component
        interaction.data = {'custom_id': customId} if customId else {}
        answered = []
        interaction.response = Mock(defer = AsyncMock(side_effect = lambda **kwargs: answered.append(True)), send_modal = AsyncMock(), send_message = AsyncMock(), is_done = Mock(side_effect = lambda: bool(answered)))
        interaction.send = AsyncMock(return_value = Mock(edit = AsyncMock()))
        interaction.message = Mock(edit = AsyncMock())
        return interaction

    def labels(self, interaction):
        return [item.label for item in interaction.send.await_args.kwargs['view'].children]

    async def test_a_name_guesses_and_nothing_opens_the_card(self):
        isolation.restorePagination()
        with patch.object(self.whodis, 'commonDis', AsyncMock()) as commonDis:
            interaction = self.press()
            await self.whodis.whodisSlash(interaction, 'stormerg')
            commonDis.assert_awaited_once_with(interaction, interaction.user, 'stormerg')
            dmContext = Mock(spec = Context, guild = None, author = self.author)
            await self.whodis.whodis.callback(self.whodis, dmContext, 'stormerg')
            commonDis.assert_awaited_with(dmContext, self.author, 'stormerg')
            # typed in a server, a guess would tell the channel; it's refused privately and removed
            with patch.object(self.whodis, 'deletePublicWhoDisMessages', AsyncMock()) as delete:
                await self.whodis.whodis.callback(self.whodis, self.ctx, 'stormerg')
            delete.assert_awaited_once_with(self.guild.id, [self.message], self.channel)
            self.assertIn('guess in this private message', self.author.send.await_args.kwargs['embed'].description)
            self.assertEqual(commonDis.await_count, 2)
        with patch.object(self.whodis, 'openCardFromChannel', AsyncMock()) as fromChannel, patch.object(self.whodis, 'openCard', AsyncMock()) as openCard:
            # typed in a server, it goes to their DMs, with no line saying who asked
            await self.whodis.commonWhoDisCommand(self.ctx, self.author, None)
            fromChannel.assert_awaited_once_with(self.ctx.message, self.author, self.ctx.guild)
            await self.whodis.commonWhoDisCommand(dmContext, self.author, None)
            openCard.assert_awaited_once_with(dmContext, self.author)
            interaction = self.press()
            await self.whodis.commonWhoDisCommand(interaction, self.author, None)
            openCard.assert_awaited_with(interaction, self.author)

    async def test_the_card_offers_what_you_can_do_now(self):
        interaction = self.press()
        await self.whodis.openCard(interaction, self.author)
        self.assertEqual(self.labels(interaction), ['Start a game', 'Leave Who Dis', 'How it works', CLOSE])
        self.assertIn('10 minutes after starting the last', interaction.send.await_args.kwargs['embed'].description)
        self.assertTrue(interaction.send.await_args.kwargs['ephemeral'])
        # its buttons last, naming the server they act for
        view = interaction.send.await_args.kwargs['view']
        self.assertIsNone(view.timeout)
        self.assertTrue(view.is_finished())
        self.assertEqual([item.custom_id for item in view.children], [f'whodis:start:{self.guild.id}', f'whodis:leave:{self.guild.id}', 'whodis:guide', 'whodis:close'])
        # in a game it says so, and still offers no End: that's on the game's own card
        self._seed_game()
        await self.whodis.openCard(interaction, self.author)
        self.assertEqual(self.labels(interaction), ['Start a game', 'Leave Who Dis', 'How it works', CLOSE])
        ends = int((self.fixed_now + timedelta(minutes = 5)).timestamp())
        self.assertIn(f'ends <t:{ends}:R>', interaction.send.await_args.kwargs['embed'].description)
        self.whodis.whoDisGames.clear()
        interaction = self.press(guild = None)
        await self.whodis.openCard(interaction, self.author)
        self.assertEqual(self.labels(interaction), ['How it works', CLOSE])
        self.assertIn('Start a game from a server', interaction.send.await_args.kwargs['embed'].description)

    def cardPress(self, action, user = None, guild = 'default', ephemeral = True):
        serverPart = f':{self.guild.id}' if action in ('start', 'leave') else ''
        pressed = self.press(user = user, guild = guild, customId = f'whodis:{action}{serverPart}')
        pressed.message = Mock(delete = AsyncMock(), flags = Mock(ephemeral = ephemeral))
        pressed.delete_original_message = AsyncMock()
        return pressed

    async def test_the_cards_buttons(self):
        with patch.object(whodis_cog.predicates, 'recheck', AsyncMock()) as recheck, \
             patch.object(whodis_cog.predicates, 'ensureSubscribed', AsyncMock()) as ensureSubscribed, \
             patch.object(self.whodis, 'commonWhoDis', AsyncMock()) as commonWhoDis, \
             patch.object(self.whodis, 'commonLeaveDis', AsyncMock()) as commonLeaveDis, \
             patch.object(self.whodis.client, 'get_guild', Mock(side_effect = lambda guildId: self.guild if guildId == self.guild.id else None)):
            pressed = self.cardPress('start')
            await self.whodis.on_interaction(pressed)
            pressed.response.defer.assert_awaited_once_with(ephemeral = True)
            recheck.assert_awaited_with(pressed, feature = 'toggle_who_dis', privateMessagesAllowed = True, guild = self.guild)
            # a new game, so no grace days once a trial or subscription has ended
            ensureSubscribed.assert_awaited_once_with(self.guild, pressed.user)
            commonWhoDis.assert_awaited_once_with(pressed, pressed.user, self.guild)
            pressed = self.cardPress('leave')
            await self.whodis.on_interaction(pressed)
            commonLeaveDis.assert_awaited_once_with(pressed, pressed.user, self.guild)
            ensureSubscribed.assert_awaited_once()
            # refused, as a new command would be
            ensureSubscribed.side_effect = whodis_cog.predicates.AccessEnded('ended', self.guild.id)
            pressed = self.cardPress('start')
            await self.whodis.on_interaction(pressed)
            commonWhoDis.assert_awaited_once()
            ensureSubscribed.side_effect = None
            # a server GBot has left since
            pressed = self.press(customId = 'whodis:start:404')
            await self.whodis.on_interaction(pressed)
            self.assertIn('GBot is no longer in that server', pressed.send.await_args.kwargs['embed'].description)
        pressed = self.cardPress('guide')
        await self.whodis.on_interaction(pressed)
        embed = pressed.response.send_message.await_args.kwargs['embed']
        self.assertEqual(embed.title, '📖 How Who Dis works')
        self.assertIn('/whodis user:<their name>', embed.description)
        # closing: a private reply through the click, a DM by deleting it, and one already gone stays gone
        pressed = self.cardPress('close')
        await self.whodis.on_interaction(pressed)
        pressed.delete_original_message.assert_awaited_once()
        pressed = self.cardPress('close', ephemeral = False)
        await self.whodis.on_interaction(pressed)
        pressed.message.delete.assert_awaited_once()
        pressed.message.delete.side_effect = nextcord.HTTPException(Mock(status = 404), 'gone')
        await self.whodis.on_interaction(pressed)

    async def test_typed_in_a_channel_the_card_goes_to_dms(self):
        isolation.restorePagination()
        self.guild.name = 'My Server'
        member = Mock(id = self.author.id, mention = self.author.mention, status = nextcord.Status.online, send = AsyncMock())
        self.guild.get_member = Mock(side_effect = lambda userId: member if userId == member.id else None)
        message = Mock(delete = AsyncMock(), channel = Mock(send = AsyncMock()))
        self.assertTrue(await self.whodis.openCardFromChannel(message, member, self.guild))
        message.delete.assert_awaited_once()
        message.channel.send.assert_not_awaited()
        kwargs = member.send.await_args.kwargs
        self.assertEqual(kwargs['embed'].title, '❓ Who Dis? in My Server')
        self.assertEqual([item.label for item in kwargs['view'].children], ['Start a game', 'Leave Who Dis', 'How it works', CLOSE])
        # a press in DMs acts for the server, as its member there
        with patch.object(whodis_cog.predicates, 'recheck', AsyncMock()) as recheck, \
             patch.object(whodis_cog.predicates, 'ensureSubscribed', AsyncMock()), \
             patch.object(self.whodis, 'commonWhoDis', AsyncMock()) as commonWhoDis, \
             patch.object(self.whodis, 'commonLeaveDis', AsyncMock()) as commonLeaveDis, \
             patch.object(self.whodis.client, 'get_guild', Mock(return_value = self.guild)):
            user = Mock(id = member.id, mention = member.mention)
            pressed = self.cardPress('start', user = user, guild = None)
            await self.whodis.on_interaction(pressed)
            recheck.assert_awaited_with(pressed, feature = 'toggle_who_dis', privateMessagesAllowed = True, guild = self.guild)
            commonWhoDis.assert_awaited_once_with(pressed, member, self.guild)
            pressed = self.cardPress('leave', user = user, guild = None)
            await self.whodis.on_interaction(pressed)
            commonLeaveDis.assert_awaited_once_with(pressed, member, self.guild)
            # someone who has left the server since
            gone = Mock(id = 999, mention = '<@999>')
            for action in ('start', 'leave'):
                pressed = self.cardPress(action, user = gone, guild = None)
                await self.whodis.on_interaction(pressed)
                self.assertIn("you're no longer in My Server", pressed.send.await_args.kwargs['embed'].description)
            commonWhoDis.assert_awaited_once()
            commonLeaveDis.assert_awaited_once()
        # a message GBot can't delete stays, and closed DMs are said in the channel
        message.delete.side_effect = nextcord.HTTPException(Mock(status = 403), 'no')
        member.send.side_effect = nextcord.HTTPException(Mock(status = 403), 'closed')
        self.assertFalse(await self.whodis.openCardFromChannel(message, member, self.guild))
        self.assertIn("GBot couldn't message you", message.channel.send.await_args.args[0])

    async def test_the_game_card_carries_end_and_report(self):
        sent = []
        self.author.send = AsyncMock(side_effect = lambda **kwargs: sent.append(kwargs))
        self.randomUser.send = AsyncMock(side_effect = lambda **kwargs: sent.append(kwargs))
        self.assertTrue(await self.whodis.startWhoDis(self.author, self.randomUser, 5, self.guild))
        self.assertEqual([item.custom_id for item in sent[0]['view'].children], [f'whodis:end:{self.author.id}:{self.randomUser.id}', f'whodis:report:{self.author.id}:{self.randomUser.id}'])
        self.assertTrue(sent[0]['view'].is_finished())
        self.assertIn('/whodis user:<their name>', sent[0]['embed'].description)
        ends = int((self.fixed_now + timedelta(minutes = 5)).timestamp())
        self.assertIn(f'⏳ Ends <t:{ends}:R>', sent[0]['embed'].description)

    async def test_ending_from_the_game_card(self):
        key = self._seed_game()
        interaction = self.press(guild = None, customId = f'whodis:end:{key}')
        await self.whodis.on_interaction(interaction)
        interaction.response.defer.assert_awaited_once_with(ephemeral = True)
        self.assertEqual(self.whodis.whoDisGames, {})
        self.assertEqual(interaction.send.await_args.kwargs['embed'].title, '🚪 Game cancelled')
        self.randomUser.send.assert_awaited()
        interaction.message.edit.assert_awaited_once_with(view = None)
        # pressed again, or after a restart, the game is simply over
        interaction = self.press(guild = None, customId = f'whodis:end:{key}')
        interaction.message.edit.side_effect = nextcord.NotFound(Mock(status = 404, reason = 'gone'), 'gone')
        await self.whodis.on_interaction(interaction)
        self.assertEqual(interaction.send.await_args.kwargs['content'], '🚪 This game is already over.')

    async def test_reporting_from_the_game_card(self):
        theirs = [Mock()]
        key = self._seed_game(randomUserMessages = theirs, initiatorMessages = ['mine'])
        config = Mock(fileReport = AsyncMock(return_value = True))
        self.client.get_cog = Mock(return_value = config)
        interaction = self.press(guild = None, customId = f'whodis:report:{key}')
        await self.whodis.on_interaction(interaction)
        form = interaction.response.send_modal.await_args.args[0]
        self.assertEqual(form.title, 'Report this game')
        submitted = self.press(guild = None)
        await form.onSubmit(submitted, ['rude'])
        submitted.response.defer.assert_awaited_once_with(ephemeral = True, with_message = True)
        config.fileReport.assert_awaited_once_with(self.guild, self.author, self.randomUser, 'a Who Dis game', theirs, 'rude')
        self.assertIn('Sent to the admins', submitted.send.await_args.kwargs['content'])
        # the other player reports the initiator
        submitted = self.press(self.randomUser, guild = None)
        await form.onSubmit(submitted, [''])
        self.assertEqual(config.fileReport.await_args.args[2:5], (self.author, 'a Who Dis game', ['mine']))
        config.fileReport.return_value = False
        await form.onSubmit(submitted, [''])
        self.assertIn('no admin channel', submitted.send.await_args.kwargs['embed'].description)
        self.whodis.whoDisGames.clear()
        await form.onSubmit(submitted, [''])
        self.assertIn('This game is over', submitted.send.await_args.kwargs['embed'].description)

    async def test_an_old_game_card_cannot_act_on_a_newer_game(self):
        self._seed_game(randomUser = self.otherUser)
        interaction = self.press(guild = None, customId = f'whodis:end:{self.author.id}:{self.randomUser.id}')
        await self.whodis.on_interaction(interaction)
        self.assertEqual(interaction.send.await_args.kwargs['content'], '🚪 This game is already over.')
        self.assertEqual(len(self.whodis.whoDisGames), 1)

    async def test_game_card_presses_that_fail_or_are_not_ours(self):
        with patch.object(self.whodis, 'endFromCard', AsyncMock(side_effect = KeyError('x'))), patch.object(whodis_cog.presentation, 'sendInteractionError', AsyncMock()) as sendInteractionError:
            await self.whodis.on_interaction(self.press(customId = 'whodis:end'))
            await self.whodis.on_interaction(self.press(customId = 'whodis:other'))
            await self.whodis.on_interaction(self.press(customId = 'gtrade:buy:1'))
        sendInteractionError.assert_awaited_once()

    async def test_a_guess_is_private(self):
        interaction = self.press()
        await self.whodis.commonDis(interaction, self.author, 'someone')
        interaction.response.defer.assert_awaited_once_with(ephemeral = True)
    #endregion

if __name__ == '__main__':
    unittest.main()
