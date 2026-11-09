#region IMPORTS
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, Mock, AsyncMock, patch
import nextcord
from nextcord.ext import commands
from nextcord.ext.commands.context import Context

from GBotDiscord.src import access, presentation
from GBotDiscord.src.config import config_queries
from GBotDiscord.src.patreon import patreon_queries
from GBotDiscord.src.patreon import patreon_cog as patreon_cog_module
from GBotDiscord.src.patreon.patreon_cog import Patreon
from GBotDiscord.src.properties import GBotPropertiesManager
from GBotDiscord.src.firebase import GBotFirebaseService
#endregion

# to run this test suite:
#   - execute the following command from the GBot directory: python -m unittest GBotDiscord/test/patreon/patreon_test.py
#   - or use the "Python: Current File" run configuration to run patreon_test.py
#   - or use the "Python: Current File" run configuration to run tests.py to run all test suites
class TestPatreon(unittest.IsolatedAsyncioTestCase):

    @classmethod
    def setUpClass(self):
        print('\nExecuting patreon unit tests...\n')

    @classmethod
    def tearDownClass(self):
        print('\n\nCompleted patreon unit tests.\n')

    def setUp(self):
        GBotPropertiesManager.PATREON_GUILD_ID = 10
        GBotPropertiesManager.PATRON_ROLE_ID = 50
        GBotPropertiesManager.PATREON_IGNORE_GUILDS = [11,12,13]
        GBotPropertiesManager.TRIAL_DAYS = 7
        GBotPropertiesManager.GRACE_DAYS = 3
        GBotPropertiesManager.PATREON_URL = 'https://patreon.example'

        patreon_queries.getAllPatrons = MagicMock(return_value = [])
        patreon_queries.getAllTrials = MagicMock(return_value = None)

        self.role = Mock()
        self.role.id = 50

        self.author = Mock()
        self.author.id = 54321
        self.author.roles = []

        self.guild1: nextcord.Guild = Mock()
        self.guild1.id = 10
        self.guild1.fetch_member = AsyncMock()
        self.guild1.fetch_member.return_value = self.author

        self.guild2: nextcord.Guild = Mock()
        self.guild2.id = 9
        self.guild2.leave = AsyncMock()

        self.guild3: nextcord.Guild = Mock()
        self.guild3.id = 12
        self.guild3.leave = AsyncMock()

        self.guild4: nextcord.Guild = Mock()
        self.guild4.id = 14
        self.guild4.leave = AsyncMock()

        self.ctx: Context = Mock()
        self.ctx.guild = self.guild1
        self.ctx.author = self.author

        self.interaction: nextcord.Interaction = Mock()
        self.interaction.guild = self.guild1
        self.interaction.user = self.author

        self.client: nextcord.Client = commands.Bot()
        self.client.fetch_guild = AsyncMock()
        self.client.fetch_guild.return_value = self.guild1

        self.patreon: Patreon = Patreon(self.client)

    async def test_patreon_validation_ignore_subscribed_guilds(self):
        patreon_queries.getAllPatrons = MagicMock(side_effect = [
            {
                "1000": {
                    "serverId": "9"
                }
            },
            {
                "1000": {
                    "serverId": "9"
                }
            }
        ])
        self.author.roles = [self.role]
        GBotFirebaseService.remove = MagicMock()
        self.patreon.getAllGuilds = MagicMock()
        self.patreon.getAllGuilds.return_value = [self.guild2]
        await self.patreon.patreon_validation()
        GBotFirebaseService.remove.assert_not_called()
        self.guild2.leave.assert_not_called()

    async def test_patreon_validation_ignore_ignored_guilds(self):
        patreon_queries.getAllPatrons = MagicMock(side_effect = [
            {
                "1000": {
                    "serverId": "12"
                }
            },
            {}
        ])
        GBotFirebaseService.remove = MagicMock()
        self.patreon.getAllGuilds = MagicMock()
        self.patreon.getAllGuilds.return_value = [self.guild3]
        await self.patreon.patreon_validation()
        GBotFirebaseService.remove.assert_not_called()
        self.guild3.leave.assert_not_called()

    async def test_patreon_validation_ignored_entry_does_not_abandon_later_patrons(self):
        # Regression for A-2: the ignore-list check used `break`, so the first patron mapped
        # to an ignored server abandoned every remaining entry and stale patrons were never
        # reaped. Patron "1000" is on ignored server 12; "2000" is on tracked server 9 and
        # has lost the patron role, so it must still be removed.
        patreon_queries.getAllPatrons = MagicMock(side_effect = [
            {
                "1000": {
                    "serverId": "12"
                },
                "2000": {
                    "serverId": "9"
                }
            },
            {}
        ])
        GBotFirebaseService.set = MagicMock()
        self.author.roles = []          # no patron role -> entry should be marked lapsed
        self.patreon.getAllGuilds = MagicMock(return_value = [])
        await self.patreon.patreon_validation()
        self.assertEqual(GBotFirebaseService.set.call_args.args[0], ["patreon_members", "2000", "lapsed"])

    # A-16: the ignore list was snapshotted in Patreon.__init__, so a setProperty on
    # PATREON_IGNORE_GUILDS had no effect until the bot restarted, and the cog disagreed with
    # the predicates (which read it live).
    async def test_patreon_validation_rereads_ignore_guilds_property_after_it_changes(self):
        patreon_queries.getAllPatrons = MagicMock(side_effect = [{}, {}])
        self.patreon.getAllGuilds = MagicMock(return_value = [self.guild2])

        # guild2 (id 9) is not ignored at construction time, so it would be left
        GBotPropertiesManager.PATREON_IGNORE_GUILDS = [9]
        await self.patreon.patreon_validation()
        self.guild2.leave.assert_not_called()

    async def test_patreon_validation_remove_unsubscribed_guilds(self):
        # lapsed longer ago than the grace days: removed, and its server left
        lapsedAt = (datetime.now(timezone.utc) - timedelta(days = 3)).isoformat()
        patreon_queries.getAllPatrons = MagicMock(side_effect = [
            {
                "1000": {
                    "serverId": "14",
                    "lapsed": lapsedAt
                }
            },
            {}
        ])
        GBotFirebaseService.remove = MagicMock()
        self.patreon.getAllGuilds = MagicMock()
        self.patreon.getAllGuilds.return_value = [self.guild4]
        await self.patreon.patreon_validation()
        GBotFirebaseService.remove.assert_called_once_with(["patreon_members", '1000'])
        self.guild4.leave.assert_called_once()

    async def test_patreon(self):
        GBotFirebaseService.set = MagicMock()
        self.ctx.send = AsyncMock()
        await self.patreon.patreon(self.patreon, self.ctx, self.guild1.id)
        GBotFirebaseService.set.assert_any_call(["patreon_members", self.author.id], {"serverId": str(self.guild1.id)})
        self.ctx.send.assert_called_once_with('⭐ GBot is now accessible in the specified server. Thank you for subscribing and enjoy!')

    async def test_patreon_slash(self):
        GBotFirebaseService.set = MagicMock()
        self.interaction.send = AsyncMock()
        await self.patreon.patreonSlash(self.interaction, self.guild1.id)
        GBotFirebaseService.set.assert_any_call(["patreon_members", self.author.id], {"serverId": str(self.guild1.id)})
        self.interaction.send.assert_called_once_with('⭐ GBot is now accessible in the specified server. Thank you for subscribing and enjoy!')

    def test_get_all_guilds_returns_client_guilds(self):
        sentinelGuilds = [self.guild1, self.guild2]
        fakeClient = Mock()
        fakeClient.guilds = sentinelGuilds
        self.patreon.client = fakeClient
        self.assertEqual(self.patreon.getAllGuilds(), sentinelGuilds)

    async def test_on_ready_starts_patreon_validation(self):
        self.patreon.patreon_validation = MagicMock()
        self.patreon.trial_reminders = MagicMock()
        await self.patreon.on_ready()
        self.patreon.patreon_validation.start.assert_called_once()
        self.patreon.trial_reminders.start.assert_called_once()

    async def test_on_ready_handles_runtime_error_from_start(self):
        self.patreon.patreon_validation = MagicMock()
        self.patreon.patreon_validation.start.side_effect = RuntimeError()
        self.patreon.trial_reminders = MagicMock()
        self.patreon.trial_reminders.start.side_effect = RuntimeError()
        self.patreon.logger = MagicMock()
        await self.patreon.on_ready()
        self.patreon.logger.info.assert_any_call('patreon_validation task is already launched and is not completed.')
        self.patreon.logger.info.assert_any_call('trial_reminders task is already launched and is not completed.')

    # trials

    def startedDaysAgo(self, days, **extra):
        return dict({'started': (datetime.now(timezone.utc) - timedelta(days = days)).isoformat()}, **extra)

    def server(self, serverId):
        guild = Mock(id = serverId)
        guild.leave = AsyncMock()
        return guild

    async def test_patreon_validation_stays_through_a_trial_and_its_grace_days_then_leaves(self):
        onTrial, ended, expired, never = self.server(20), self.server(21), self.server(22), self.server(23)
        patreon_queries.getAllPatrons = MagicMock(return_value = None)
        patreon_queries.getAllTrials = MagicMock(return_value = {'20': self.startedDaysAgo(1), '21': self.startedDaysAgo(8), '22': self.startedDaysAgo(11)})
        self.patreon.getAllGuilds = MagicMock(return_value = [onTrial, ended, expired, never])
        await self.patreon.patreon_validation()
        onTrial.leave.assert_not_awaited()
        ended.leave.assert_not_awaited()
        expired.leave.assert_awaited_once()
        never.leave.assert_awaited_once()

    def remindable(self, *guilds):
        self.patreon.getAllGuilds = MagicMock(return_value = list(guilds))
        self.patreon.sendNotice = AsyncMock()
        GBotFirebaseService.set = MagicMock()

    async def test_trial_reminders_sends_whats_due_once_and_records_it(self):
        twoDaysLeft, notYet, subscribed, noTrial = self.server(20), self.server(21), self.server(22), self.server(23)
        patreon_queries.getAllTrials = MagicMock(return_value = {'20': self.startedDaysAgo(5), '21': self.startedDaysAgo(1), '22': self.startedDaysAgo(6)})
        patreon_queries.getAllPatrons = MagicMock(return_value = {'p': {'serverId': '22'}})
        self.remindable(twoDaysLeft, notYet, subscribed, noTrial)
        await self.patreon.trial_reminders()
        self.patreon.sendNotice.assert_awaited_once()
        guild, text = self.patreon.sendNotice.await_args.args
        self.assertIs(guild, twoDaysLeft)
        self.assertTrue(text.startswith("🎁 GBot's free trial in this server ends <t:"))
        GBotFirebaseService.set.assert_called_once_with(['trials', '20', 'reminded'], access.REMINDER_TWO_DAYS)

    # lapses

    async def test_a_lapsed_patron_is_kept_for_the_grace_days_and_cleared_when_they_renew(self):
        GBotFirebaseService.set = MagicMock()
        GBotFirebaseService.remove = MagicMock()
        recently = {'serverId': '9', 'lapsed': datetime.now(timezone.utc).isoformat()}
        await self.patreon.checkPatron('1000', recently, False)
        GBotFirebaseService.set.assert_not_called()
        GBotFirebaseService.remove.assert_not_called()
        await self.patreon.checkPatron('1000', recently, True)
        GBotFirebaseService.set.assert_called_once_with(['patreon_members', '1000'], {'serverId': '9'})
        # a patron in good standing is left alone
        GBotFirebaseService.set.reset_mock()
        await self.patreon.checkPatron('1000', {'serverId': '9'}, True)
        GBotFirebaseService.set.assert_not_called()

    async def test_a_lapse_is_told_once_only_to_a_server_this_bot_is_in_that_nobody_else_pays_for(self):
        lapsedAt = datetime.now(timezone.utc).isoformat()
        mine, notified, coveredByAnother = self.server(20), self.server(21), self.server(22)
        patreon_queries.getAllPatrons = MagicMock(side_effect = [None, {
            'a': {'serverId': '20', 'lapsed': lapsedAt},
            'b': {'serverId': '21', 'lapsed': lapsedAt, 'lapseNotified': True},
            'c': {'serverId': '22', 'lapsed': lapsedAt},
            'd': {'serverId': '22'},
            'e': {'serverId': '30', 'lapsed': lapsedAt}
        }])
        GBotFirebaseService.set = MagicMock()
        self.patreon.sendNotice = AsyncMock()
        self.patreon.getAllGuilds = MagicMock(return_value = [mine, notified, coveredByAnother])
        await self.patreon.patreon_validation()
        self.patreon.sendNotice.assert_awaited_once()
        self.assertIs(self.patreon.sendNotice.await_args.args[0], mine)
        GBotFirebaseService.set.assert_called_once_with(['patreon_members', 'a', 'lapseNotified'], True)
        for guild in (mine, notified, coveredByAnother):
            guild.leave.assert_not_awaited()

    async def test_trial_reminders_with_no_trials_reads_nothing_else(self):
        patreon_queries.getAllPatrons = MagicMock()
        self.remindable(self.server(20))
        await self.patreon.trial_reminders()
        patreon_queries.getAllPatrons.assert_not_called()
        self.patreon.sendNotice.assert_not_awaited()

    async def test_trial_reminders_logs_a_failure(self):
        patreon_queries.getAllTrials = MagicMock(side_effect = Exception('boom'))
        self.patreon.logger = MagicMock()
        await self.patreon.trial_reminders()
        self.patreon.logger.error.assert_called_once_with('Error in Patreon.trial_reminders(): boom')

    def remindIn(self, adminChannelId, adminChannel = None, fallback = None):
        config_queries.getServerValue = MagicMock(return_value = adminChannelId)
        guild = self.server(20)
        guild.get_channel = Mock(return_value = adminChannel)
        self.patreon.logger = MagicMock()
        return guild, patch.object(presentation, 'postableChannel', return_value = fallback)

    async def test_a_trial_reminder_goes_to_the_admin_channel_with_the_patreon_button(self):
        admin = Mock(send = AsyncMock())
        guild, fallback = self.remindIn('111', admin)
        with fallback:
            await self.patreon.sendNotice(guild, 'ends soon')
        guild.get_channel.assert_called_once_with(111)
        self.assertEqual(admin.send.await_args.args, ('ends soon',))
        self.assertEqual(admin.send.await_args.kwargs['view'].children[0].url, 'https://patreon.example')

    async def test_a_trial_reminder_falls_back_to_where_the_welcome_went(self):
        welcome = Mock(send = AsyncMock())
        for adminChannelId in (None, '111'):
            guild, fallback = self.remindIn(adminChannelId, None, welcome)
            with self.subTest(adminChannelId = adminChannelId), fallback:
                await self.patreon.sendNotice(guild, 'ends soon')
        self.assertEqual(welcome.send.await_count, 2)

    async def test_a_trial_reminder_with_nowhere_to_go_or_failing_is_logged(self):
        guild, fallback = self.remindIn(None)
        with fallback:
            await self.patreon.sendNotice(guild, 'ends soon')
        self.patreon.logger.info.assert_called_once_with('GBot had nowhere to post a notice in server 20.')
        guild, fallback = self.remindIn('111', Mock(send = AsyncMock(side_effect = Exception('Missing Access'))))
        with fallback:
            await self.patreon.sendNotice(guild, 'ends soon')
        self.patreon.logger.error.assert_called_once_with('GBot could not send a notice in server 20: Missing Access')

    async def test_patreon_validation_none_patrons_skips_member_check_and_leaves_unsubscribed(self):
        # both calls to getAllPatrons return None — first loop short-circuits, second loop
        # leaves any non-ignored guild because subscribedServerIds is empty.
        patreon_queries.getAllPatrons = MagicMock(side_effect=[None, None])
        GBotFirebaseService.remove = MagicMock()
        self.patreon.getAllGuilds = MagicMock(return_value=[self.guild4])
        await self.patreon.patreon_validation()
        # fetch_guild only called when patrons exist; it should not have been called here
        self.client.fetch_guild.assert_not_called()
        GBotFirebaseService.remove.assert_not_called()
        self.guild4.leave.assert_called_once()

    async def test_patreon_validation_logs_when_guild_leave_raises(self):
        patreon_queries.getAllPatrons = MagicMock(side_effect=[None, None])
        self.patreon.getAllGuilds = MagicMock(return_value=[self.guild4])
        self.guild4.leave = AsyncMock(side_effect=Exception('boom'))
        self.patreon.logger = MagicMock()
        await self.patreon.patreon_validation()
        self.guild4.leave.assert_called_once()
        self.patreon.logger.error.assert_called_once_with(
            f'GBot Patreon failed to leave unsubscribed server {self.guild4.id}: boom'
        )

    def _not_found(self):
        return nextcord.NotFound(Mock(status = 404, reason = 'Not Found'), 'Unknown Member')

    # Used to abort the whole run, every run: no later patron was checked and no unsubscribed guild
    # was ever left. Having left the Patreon server, they cannot hold the role.
    async def test_patreon_validation_patron_who_left_lapses_and_the_run_continues(self):
        allPatrons = {"1000": {"serverId": "8"}, "2000": {"serverId": "9"}}
        lapsed = {"1000": {"serverId": "8", "lapsed": datetime.now(timezone.utc).isoformat()}, "2000": {"serverId": "9"}}
        patreon_queries.getAllPatrons = MagicMock(side_effect = [allPatrons, lapsed])
        GBotFirebaseService.remove = MagicMock()
        GBotFirebaseService.set = MagicMock()
        self.patreon.sendNotice = AsyncMock()
        self.author.roles = [self.role]
        self.guild1.fetch_member = AsyncMock(side_effect = [self._not_found(), self.author])
        # guild1 is the Patreon server itself and guild3 is on PATREON_IGNORE_GUILDS; neither has a
        # subscription, and neither may ever be left
        self.patreon.getAllGuilds = MagicMock(return_value = [self.guild2, self.guild1, self.guild3])
        self.guild1.leave = AsyncMock()
        self.guild2.id = 8
        self.guild2.leave = AsyncMock()
        await self.patreon.patreon_validation()
        GBotFirebaseService.remove.assert_not_called()
        self.assertEqual(GBotFirebaseService.set.call_args_list[0].args[0], ["patreon_members", "1000", "lapsed"])
        self.assertEqual(self.guild1.fetch_member.await_count, 2)
        # its server is told, and kept for the grace days
        self.assertIs(self.patreon.sendNotice.await_args.args[0], self.guild2)
        self.assertTrue(self.patreon.sendNotice.await_args.args[1].startswith("💳 This server's GBot subscription has ended"))
        GBotFirebaseService.set.assert_called_with(["patreon_members", "1000", "lapseNotified"], True)
        self.guild2.leave.assert_not_awaited()
        self.guild1.leave.assert_not_awaited()
        self.guild3.leave.assert_not_awaited()

    # A check that did not complete must never get as far as leaving a guild.
    async def test_patreon_validation_other_member_lookup_failure_leaves_no_guild(self):
        patreon_queries.getAllPatrons = MagicMock(return_value = {"1000": {"serverId": "9"}})
        GBotFirebaseService.remove = MagicMock()
        self.guild1.fetch_member = AsyncMock(side_effect = Exception('Discord is down'))
        self.patreon.getAllGuilds = MagicMock(return_value = [self.guild2])
        self.guild2.leave = AsyncMock()
        self.patreon.logger = MagicMock()
        await self.patreon.patreon_validation()
        GBotFirebaseService.remove.assert_not_called()
        self.guild2.leave.assert_not_awaited()
        self.patreon.logger.error.assert_called_once()

    async def test_patreon_validation_outer_exception_logged(self):
        patreon_queries.getAllPatrons = MagicMock(side_effect=Exception('boom'))
        self.patreon.logger = MagicMock()
        await self.patreon.patreon_validation()
        self.patreon.logger.error.assert_called_once()
        logArg = self.patreon.logger.error.call_args[0][0]
        self.assertIn('Error in Patreon.patreon_validation():', logArg)

    def test_setup_adds_patreon_cog(self):
        client = MagicMock()
        patreon_cog_module.setup(client)
        client.add_cog.assert_called_once()
        addedCog = client.add_cog.call_args[0][0]
        self.assertIsInstance(addedCog, Patreon)

if __name__ == '__main__':
    unittest.main()