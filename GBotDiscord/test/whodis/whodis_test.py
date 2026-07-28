#region IMPORTS
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
from GBotDiscord.src.whodis.whodis_cog import WhoDis
from GBotDiscord.src.exceptions import WhoDisNotConfigured, CustomCommandOnCooldown
from GBotDiscord.src.properties import GBotPropertiesManager
#endregion

# to run this test suite:
#   - execute the following command from the GBot directory: python -m unittest GBotDiscord/test/whodis/whodis_test.py
#   - or use the "Python: Current File" run configuration to run whodis_test.py
#   - or use the "Python: Current File" run configuration to run tests.py to run all test suites
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
        self.client.fetch_channel = AsyncMock(return_value = self.channel)

        self.whodis: WhoDis = WhoDis(self.client)

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

    async def test_on_message_prefix_command_skipped_dot(self):
        self._seed_game()
        msg = Mock()
        msg.guild = None
        msg.author = self.author
        msg.content = ".dis user"
        await self.whodis.on_message(msg)
        # randomUser should not receive a forwarded message
        self.randomUser.send.assert_not_called()

    async def test_on_message_prefix_command_skipped_slash(self):
        self._seed_game()
        msg = Mock()
        msg.guild = None
        msg.author = self.author
        msg.content = "/dis user"
        await self.whodis.on_message(msg)
        self.randomUser.send.assert_not_called()

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
        self.ctx.send.assert_called_once_with(f'Sorry {self.author.mention}, Who Dis games must be started in a server.')

    async def test_commonWhoDis_existing_game_cancels(self):
        gameKey = self._seed_game()
        await self.whodis.commonWhoDis(self.ctx, self.author)
        # game is removed
        self.assertNotIn(gameKey, self.whodis.whoDisGames)
        # author received a "you cancelled" DM
        self.author.send.assert_any_call("# DIS... A GHOST? - GAME CANCELLED #\n**(you cancelled the game)**")
        # randomUser received a "game was cancelled" DM (since author is initiator)
        self.randomUser.send.assert_any_call("# DIS... A GHOST? - GAME CANCELLED #\n**(the game was cancelled)**")

    async def test_commonWhoDis_not_configured_no_role_id(self):
        # configured returns (False, None)
        config_queries.getServerValue = MagicMock(return_value = None)
        utils.sendMessageToAdmins = AsyncMock()
        utils.purgePreviousMessages = AsyncMock()
        await self.whodis.commonWhoDis(self.ctx, self.author)
        self.ctx.send.assert_any_call('Who Dis not started.')
        self.author.send.assert_any_call(f'Sorry {self.author.mention}, Who Dis is not configured in this server.')
        utils.sendMessageToAdmins.assert_called_once()

    async def test_commonWhoDis_not_configured_role_not_present(self):
        # role_who_dis returns an id that isn't in guild.roles; isWhoDisEnabled returns True
        config_queries.getServerValue = MagicMock(side_effect = lambda sid, key: True if key == 'toggle_who_dis' else 'missing-role-id')
        self.guild.roles = []
        utils.sendMessageToAdmins = AsyncMock()
        utils.purgePreviousMessages = AsyncMock()
        await self.whodis.commonWhoDis(self.ctx, self.author)
        self.author.send.assert_any_call(f'Sorry {self.author.mention}, Who Dis is not configured in this server.')

    async def test_commonWhoDis_author_offline(self):
        config_queries.getServerValue = MagicMock(side_effect = lambda sid, key: True if key == 'toggle_who_dis' else str(self.role.id))
        utils.purgePreviousMessages = AsyncMock()
        self.author.status = nextcord.Status.offline
        await self.whodis.commonWhoDis(self.ctx, self.author)
        self.ctx.send.assert_any_call('Who Dis not started.')
        self.author.send.assert_any_call(f"Sorry {self.author.mention}, you need to be online to start 'Who Dis?' games.")

    async def test_commonWhoDis_role_add_success(self):
        config_queries.getServerValue = MagicMock(side_effect = lambda sid, key: True if key == 'toggle_who_dis' else str(self.role.id))
        utils.purgePreviousMessages = AsyncMock()
        # author is not assigned the role -> code path adds it
        self.author.roles = []
        utils.isUserAssignedRole = MagicMock(return_value = False)
        utils.addRoleToUser = AsyncMock(return_value = True)
        # no other online users to pair with so the flow stops after role-add + opt-in DM
        utils.getOnlineAndIdleUsers = AsyncMock(return_value = [])
        await self.whodis.commonWhoDis(self.ctx, self.author)
        utils.addRoleToUser.assert_called_once_with(self.author, self.role)
        self.author.send.assert_any_call("You have consented to participating in 'Who Dis?' games. Please follow your server's rules. You can opt-out with the `/leaveDis` command anytime.")

    async def test_commonWhoDis_role_add_fails(self):
        config_queries.getServerValue = MagicMock(side_effect = lambda sid, key: True if key == 'toggle_who_dis' else str(self.role.id))
        utils.purgePreviousMessages = AsyncMock()
        utils.sendMessageToAdmins = AsyncMock()
        self.author.roles = []
        utils.isUserAssignedRole = MagicMock(return_value = False)
        utils.addRoleToUser = AsyncMock(return_value = False)
        await self.whodis.commonWhoDis(self.ctx, self.author)
        self.ctx.send.assert_any_call('Who Dis not started.')
        self.author.send.assert_any_call(f"Sorry {self.author.mention}, there was a problem opting you into 'Who Dis?' games.")
        utils.sendMessageToAdmins.assert_called_once()

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

    async def test_commonWhoDis_no_available_users(self):
        config_queries.getServerValue = MagicMock(side_effect = lambda sid, key: True if key == 'toggle_who_dis' else str(self.role.id))
        utils.purgePreviousMessages = AsyncMock()
        utils.isUserAssignedRole = MagicMock(return_value = True)
        utils.getOnlineAndIdleUsers = AsyncMock(return_value = [])
        await self.whodis.commonWhoDis(self.ctx, self.author)
        self.ctx.send.assert_any_call('Who Dis not started.')
        self.author.send.assert_any_call(f'Sorry {self.author.mention}, there are currently no users available for Who Dis.')

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

    async def test_commonWhoDis_interaction_defers(self):
        # existing game -> cancel path; ensures interaction.response.defer is awaited
        self._seed_game()
        await self.whodis.commonWhoDis(self.interaction, self.author)
        self.interaction.response.defer.assert_called_once()
    #endregion

    #region commonLeaveDis
    async def test_commonLeaveDis_not_configured(self):
        config_queries.getServerValue = MagicMock(return_value = None)
        utils.sendMessageToAdmins = AsyncMock()
        await self.whodis.commonLeaveDis(self.ctx, self.author)
        self.ctx.send.assert_called_once_with(f'Sorry {self.author.mention}, Who Dis is not configured in this server.')
        utils.sendMessageToAdmins.assert_called_once()

    async def test_commonLeaveDis_role_assigned_removes(self):
        config_queries.getServerValue = MagicMock(side_effect = lambda sid, key: True if key == 'toggle_who_dis' else str(self.role.id))
        utils.isUserAssignedRole = MagicMock(return_value = True)
        await self.whodis.commonLeaveDis(self.ctx, self.author)
        self.author.remove_roles.assert_called_once_with(self.role)
        self.ctx.send.assert_called_once_with(f"{self.author.mention}, you have successfully opted-out of this server's 'Who Dis?' games.")

    async def test_commonLeaveDis_role_not_assigned(self):
        config_queries.getServerValue = MagicMock(side_effect = lambda sid, key: True if key == 'toggle_who_dis' else str(self.role.id))
        utils.isUserAssignedRole = MagicMock(return_value = False)
        await self.whodis.commonLeaveDis(self.ctx, self.author)
        self.author.remove_roles.assert_not_called()
        self.ctx.send.assert_called_once_with(f"{self.author.mention}, you are already not participating in this server's 'Who Dis?' games.")
    #endregion

    #region commonDis
    async def test_commonDis_no_active_game(self):
        await self.whodis.commonDis(self.ctx, self.author, self.randomUser.name)
        self.ctx.send.assert_called_once_with(f'Sorry {self.author.mention}, there is currently no active Who Dis game.')

    async def test_commonDis_user_not_found(self):
        self._seed_game()
        utils.getUserIdFromName = AsyncMock(return_value = None)
        await self.whodis.commonDis(self.ctx, self.author, "nobody")
        self.ctx.send.assert_called_once_with(f'Sorry {self.author.mention}, please provide the name of a user in the server in which the Who Dis game was started. Nicknames are not supported.')

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
        self.ctx.send.assert_any_call(f"# DIS {self.randomUser.mention} - GAME OVER #\n**(you guessed correctly and won 250.00 GCoin!)**")
        # randomUser got the figured-out DM
        self.randomUser.send.assert_any_call("# DIS... A GHOST? - GAME OVER #\n**(they figured out it was you!)**")

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
        self.ctx.send.assert_any_call("# DIS... A GHOST? - GAME OVER #\n**(you guessed incorrectly!)**")
        self.randomUser.send.assert_any_call("# DIS... A GHOST? - GAME OVER #\n**(they guessed incorrectly!)**")

    async def test_commonDis_interaction_defers(self):
        await self.whodis.commonDis(self.interaction, self.author, self.randomUser.name)
        self.interaction.response.defer.assert_called_once()
    #endregion

    #region commonReport
    async def test_commonReport_guild_no_user_provided(self):
        await self.whodis.commonReport(self.ctx, self.author, None)
        self.ctx.send.assert_called_once_with(f'Sorry {self.author.mention}, please report a user when using this command in a server.')

    async def test_commonReport_guild_user_not_found(self):
        utils.getUserIdFromName = AsyncMock(return_value = None)
        await self.whodis.commonReport(self.ctx, self.author, self.randomUser)
        self.ctx.send.assert_called_once_with(f'Sorry {self.author.mention}, please provide the name of a user in this server. Nicknames are not supported.')

    async def test_commonReport_guild_admin_channel_missing(self):
        utils.getUserIdFromName = AsyncMock(return_value = self.randomUser.id)
        utils.sendMessageToAdmins = AsyncMock(return_value = False)
        await self.whodis.commonReport(self.ctx, self.author, self.randomUser)
        self.ctx.send.assert_called_once_with('The report was not submitted because the server has no admin channel configured.')

    async def test_commonReport_guild_success_with_messages(self):
        utils.getUserIdFromName = AsyncMock(return_value = self.randomUser.id)
        utils.sendMessageToAdmins = AsyncMock(return_value = True)
        utils.getServerPrefixOrDefault = MagicMock(return_value = '!')

        # randomUser's recent channel history: one plain text, one prefixed command (should be skipped)
        msg1 = Mock()
        msg1.author = self.randomUser
        msg1.content = "something bad"
        msg1.attachments = []
        msg1.stickers = []
        cmdMsg = Mock()
        cmdMsg.author = self.randomUser
        cmdMsg.content = "!report someone"
        cmdMsg.attachments = []
        cmdMsg.stickers = []
        otherUserMsg = Mock()
        otherUserMsg.author = self.author
        otherUserMsg.content = "unrelated"
        otherUserMsg.attachments = []
        otherUserMsg.stickers = []
        self.channel.history = MagicMock(return_value = AsyncIter([msg1, cmdMsg, otherUserMsg]))

        await self.whodis.commonReport(self.ctx, self.author, self.randomUser)
        self.ctx.send.assert_called_once_with('The report has been successfully submitted.')
        # the initial admin-channel message + the captured msg1 (cmdMsg + otherUserMsg are filtered out)
        self.assertEqual(utils.sendMessageToAdmins.call_count, 2)

    async def test_commonReport_guild_collects_attachments_and_stickers(self):
        utils.getUserIdFromName = AsyncMock(return_value = self.randomUser.id)
        utils.sendMessageToAdmins = AsyncMock(return_value = True)
        utils.getServerPrefixOrDefault = MagicMock(return_value = '!')

        attachment = Mock()
        attachment.url = "http://example.com/img.png"
        sticker = Mock()
        sticker.url = "http://example.com/sticker.png"
        msg = Mock()
        msg.author = self.randomUser
        msg.content = None
        msg.attachments = [attachment]
        msg.stickers = [sticker]
        self.channel.history = MagicMock(return_value = AsyncIter([msg]))

        await self.whodis.commonReport(self.ctx, self.author, self.randomUser)
        # initial admin msg + textToSend + attachment url + sticker url
        self.assertEqual(utils.sendMessageToAdmins.call_count, 4)

    async def test_commonReport_guild_stops_at_max_messages(self):
        utils.getUserIdFromName = AsyncMock(return_value = self.randomUser.id)
        utils.sendMessageToAdmins = AsyncMock(return_value = True)
        utils.getServerPrefixOrDefault = MagicMock(return_value = '!')

        # produce more than NUM_MESSAGES_TO_REPORT (5) candidate messages
        msgs = []
        for i in range(self.whodis.NUM_MESSAGES_TO_REPORT + 3):
            m = Mock()
            m.author = self.randomUser
            m.content = f"msg{i}"
            m.attachments = []
            m.stickers = []
            msgs.append(m)
        self.channel.history = MagicMock(return_value = AsyncIter(msgs))

        await self.whodis.commonReport(self.ctx, self.author, self.randomUser)
        # initial admin msg + NUM_MESSAGES_TO_REPORT captured messages = 1 + 5 = 6 calls
        self.assertEqual(utils.sendMessageToAdmins.call_count, 1 + self.whodis.NUM_MESSAGES_TO_REPORT)

    async def test_commonReport_private_no_active_game(self):
        self.ctx.guild = None
        await self.whodis.commonReport(self.ctx, self.author, None)
        self.ctx.send.assert_called_once_with(f'Sorry {self.author.mention}, there is currently no active Who Dis game. You can report users in server text channels as well.')

    async def test_commonReport_private_active_game_author_is_initiator(self):
        self.ctx.guild = None
        capturedMsg = Mock()
        capturedMsg.content = "questionable"
        capturedMsg.attachments = []
        capturedMsg.stickers = []
        self._seed_game(randomUserMessages = [capturedMsg])
        utils.sendMessageToAdmins = AsyncMock(return_value = True)
        await self.whodis.commonReport(self.ctx, self.author, None)
        # initial admin msg + the captured message = 2
        self.assertEqual(utils.sendMessageToAdmins.call_count, 2)
        self.ctx.send.assert_called_once_with('The report has been successfully submitted.')

    async def test_commonReport_private_active_game_author_is_random_user(self):
        self.ctx.guild = None
        self.ctx.author = self.randomUser
        capturedMsg = Mock()
        capturedMsg.content = "questionable"
        capturedMsg.attachments = []
        capturedMsg.stickers = []
        self._seed_game(initiatorMessages = [capturedMsg])
        utils.sendMessageToAdmins = AsyncMock(return_value = True)
        await self.whodis.commonReport(self.ctx, self.randomUser, None)
        self.assertEqual(utils.sendMessageToAdmins.call_count, 2)

    async def test_commonReport_interaction_defers(self):
        await self.whodis.commonReport(self.interaction, self.author, None)
        self.interaction.response.defer.assert_called_once()
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
        self.ctx.send.assert_called_once_with("# DIS... A GHOST? - GAME OVER #\n**(you guessed incorrectly!)**")
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
        self.author.send.assert_any_call("# DIS... A GHOST? - GAME CANCELLED #\n**(you cancelled the game)**")
        self.randomUser.send.assert_any_call("# DIS... A GHOST? - GAME CANCELLED #\n**(the game was cancelled)**")
        self.ctx.send.assert_called_once_with('Who Dis cancelled.')

    async def test_cancelWhoDis_author_is_random_user_private(self):
        gameKey = self._seed_game()
        deleteMsgs = []
        # author is randomUser, context is private message (no guild echo)
        privCtx = Mock()
        privCtx.send = AsyncMock()
        await self.whodis.cancelWhoDis(privCtx, True, self.randomUser, deleteMsgs, gameKey)
        self.assertNotIn(gameKey, self.whodis.whoDisGames)
        # canceller is told via the context (private message), not author DM
        privCtx.send.assert_called_once_with("# DIS... A GHOST? - GAME CANCELLED #\n**(you cancelled the game)**")
        # the other party (initiator) is notified
        self.author.send.assert_any_call("# DIS... A GHOST? - GAME CANCELLED #\n**(the game was cancelled)**")
    #endregion

    #region timeoutWhoDis
    async def test_timeoutWhoDis_pops_game_and_notifies_both(self):
        gameKey = self._seed_game()
        await self.whodis.timeoutWhoDis(gameKey)
        self.assertNotIn(gameKey, self.whodis.whoDisGames)
        self.author.send.assert_called_once_with("# DIS... A GHOST? - GAME TIMED OUT #\n**(time ran out!)**")
        self.randomUser.send.assert_called_once_with("# DIS... A GHOST? - GAME TIMED OUT #\n**(time ran out!)**")
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

    #region prefix command wrappers (delegate to commonX)
    # Slash wrappers route through SlashApplicationCommand.__call__ which auto-binds parent_cog
    # and can't be invoked the same way; commonX_interaction_defers tests cover the same paths.
    async def test_whodis_prefix_delegates_to_commonWhoDis(self):
        self._seed_game()
        await self.whodis.whodis(self.whodis, self.ctx)
        # author received a cancellation DM via the cancel path
        self.author.send.assert_any_call("# DIS... A GHOST? - GAME CANCELLED #\n**(you cancelled the game)**")

    async def test_leavedis_prefix_delegates_to_commonLeaveDis(self):
        config_queries.getServerValue = MagicMock(side_effect = lambda sid, key: True if key == 'toggle_who_dis' else str(self.role.id))
        utils.isUserAssignedRole = MagicMock(return_value = False)
        await self.whodis.leavedis(self.whodis, self.ctx)
        self.ctx.send.assert_called_once_with(f"{self.author.mention}, you are already not participating in this server's 'Who Dis?' games.")

    async def test_dis_prefix_delegates_to_commonDis(self):
        await self.whodis.dis(self.whodis, self.ctx, self.randomUser.name)
        self.ctx.send.assert_called_once_with(f'Sorry {self.author.mention}, there is currently no active Who Dis game.')

    async def test_report_prefix_delegates_to_commonReport(self):
        await self.whodis.report(self.whodis, self.ctx, None)
        self.ctx.send.assert_called_once_with(f'Sorry {self.author.mention}, please report a user when using this command in a server.')
    #endregion

    #region slash command wrappers (delegate to commonX)
    async def test_whoDisSlash_delegates(self):
        self.whodis.commonWhoDis = AsyncMock()
        interaction = Mock(spec = nextcord.Interaction)
        interaction.user = self.author
        await self.whodis.whoDisSlash(interaction)
        self.whodis.commonWhoDis.assert_awaited_once_with(interaction, self.author)

    async def test_leaveDisSlash_delegates(self):
        self.whodis.commonLeaveDis = AsyncMock()
        interaction = Mock(spec = nextcord.Interaction)
        interaction.user = self.author
        await self.whodis.leaveDisSlash(interaction)
        self.whodis.commonLeaveDis.assert_awaited_once_with(interaction, self.author)

    async def test_disSlash_delegates(self):
        self.whodis.commonDis = AsyncMock()
        interaction = Mock(spec = nextcord.Interaction)
        interaction.user = self.author
        await self.whodis.disSlash(interaction, self.randomUser.name)
        self.whodis.commonDis.assert_awaited_once_with(interaction, self.author, self.randomUser.name)

    async def test_reportSlash_delegates(self):
        self.whodis.commonReport = AsyncMock()
        interaction = Mock(spec = nextcord.Interaction)
        interaction.user = self.author
        await self.whodis.reportSlash(interaction, self.randomUser)
        self.whodis.commonReport.assert_awaited_once_with(interaction, self.author, self.randomUser)
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

    async def test_commonDis_correct_guess_by_random_user_other_is_initiator(self):
        # exercises the else branch in commonGuess that sets otherUser = initiator (lines 499-500)
        from GBotDiscord.src.gcoin import gcoin_queries
        gameKey = self._seed_game()
        # author (test setUp's author) is the initiator. swap context so randomUser is the guesser.
        randomCtx = Mock()
        randomCtx.guild = None
        randomCtx.send = AsyncMock()
        # the randomUser names the initiator (author) — this guess is correct
        gcoin_queries.performTransaction = MagicMock()
        utils.isUrlImageContentTypeAndStatus200 = AsyncMock(return_value = True)

        await self.whodis.commonDis(randomCtx, self.randomUser, self.author.name)

        # the initiator was DM'd as "otherUser"
        self.author.send.assert_any_call("# DIS... A GHOST? - GAME OVER #\n**(they figured out it was you!)**")
        self.assertNotIn(gameKey, self.whodis.whoDisGames)

    def test_setup_adds_cog(self):
        from GBotDiscord.src.whodis import whodis_cog
        client = MagicMock()
        whodis_cog.setup(client)
        client.add_cog.assert_called_once()
        addedCog = client.add_cog.call_args[0][0]
        self.assertIsInstance(addedCog, WhoDis)


if __name__ == '__main__':
    unittest.main()
