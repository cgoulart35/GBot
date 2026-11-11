#region IMPORTS
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from GBotDiscord.src import access, utils
from GBotDiscord.src.patreon import patreon_queries
from GBotDiscord.src.properties import GBotPropertiesManager
#endregion

NOW = datetime(2026, 11, 9, 12, 0, tzinfo = timezone.utc)
# the real clock, before setUp patches it
REAL_UTC_NOW = access.utcNow

def startedDaysAgo(days, **extra):
    return dict({'started': (NOW - timedelta(days = days)).isoformat()}, **extra)

class TestAccess(unittest.TestCase):

    @classmethod
    def setUpClass(self):
        print('\n\nStarting access unit tests...\n')

    @classmethod
    def tearDownClass(self):
        print('\n\nCompleted access unit tests.\n')

    def setUp(self):
        # each test starts without remembered answers
        access.ACTIVE.clear()
        patches = [
            patch.object(GBotPropertiesManager, 'TRIAL_DAYS', 7),
            patch.object(GBotPropertiesManager, 'GRACE_DAYS', 3),
            patch.object(utils, 'getGuildsForPatreonToIgnore', MagicMock(return_value = [1])),
            patch.object(patreon_queries, 'getAllPatrons', MagicMock(return_value = {'p': {'serverId': '2'}})),
            patch.object(patreon_queries, 'getTrial', MagicMock(return_value = None)),
            patch.object(patreon_queries, 'getAllTrials', MagicMock(return_value = None)),
            patch.object(patreon_queries, 'setTrial', MagicMock()),
            patch.object(access, 'utcNow', MagicMock(return_value = NOW))
        ]
        for started in patches:
            started.start()
            self.addCleanup(started.stop)

    def test_state_in_order_ignore_list_then_patreon_then_trial(self):
        trial = startedDaysAgo(1)
        self.assertEqual(access.state(1, [1], {1}, trial), access.IGNORED)
        self.assertEqual(access.state(1, [], {1}, trial), access.SUBSCRIBED)
        self.assertEqual(access.state(1, [], set(), trial), access.TRIAL)
        self.assertEqual(access.state(1, [], set(), None), access.NONE)

    def test_a_trial_ends_then_its_grace_days_run_out(self):
        self.assertEqual(access.state(5, [], set(), startedDaysAgo(6.9)), access.TRIAL)
        self.assertEqual(access.state(5, [], set(), startedDaysAgo(7)), access.ENDED)
        self.assertEqual(access.state(5, [], set(), startedDaysAgo(9.9)), access.ENDED)
        self.assertEqual(access.state(5, [], set(), startedDaysAgo(10)), access.EXPIRED)
        # the lengths are read live, so setProperty changes running trials too
        GBotPropertiesManager.TRIAL_DAYS = 30
        self.assertEqual(access.state(5, [], set(), startedDaysAgo(10)), access.TRIAL)

    def test_only_the_allowed_states_may_use_gbot_and_only_the_finished_ones_leave(self):
        self.assertEqual(set(access.ALLOWED), {access.IGNORED, access.SUBSCRIBED, access.TRIAL})
        self.assertEqual(set(access.GRACE), {access.ENDED, access.LAPSED})
        self.assertEqual(set(access.LEAVES), {access.EXPIRED, access.NONE})

    def test_a_lapsed_subscription_is_its_own_state_unless_a_trial_is_still_running(self):
        lapsed = {5}
        self.assertEqual(access.state(5, [], set(), None, lapsed = lapsed), access.LAPSED)
        self.assertEqual(access.state(5, [], set(), startedDaysAgo(20), lapsed = lapsed), access.LAPSED)
        self.assertEqual(access.state(5, [], set(), startedDaysAgo(1), lapsed = lapsed), access.TRIAL)
        # someone else still paying wins
        self.assertEqual(access.state(5, [], {5}, None, lapsed = lapsed), access.SUBSCRIBED)

    def test_patrons_who_lapsed_dont_count_as_subscribed(self):
        patrons = {'a': {'serverId': '5', 'lapsed': NOW.isoformat()}, 'b': {'serverId': '6'}}
        self.assertEqual(access.subscribedServerIds(patrons), {6})
        self.assertEqual(access.lapsedServerIds(patrons), {5})
        self.assertEqual(access.lapsedServerIds(None), set())
        patreon_queries.getAllPatrons.return_value = patrons
        self.assertEqual(access.check(5), access.LAPSED)
        self.assertEqual(access.check(6), access.SUBSCRIBED)
        self.assertEqual(access.lapseEnds(patrons['a']), NOW + timedelta(days = 3))

    def test_check_a_server(self):
        self.assertEqual(access.check(1), access.IGNORED)
        self.assertEqual(access.check(2), access.SUBSCRIBED)
        self.assertEqual(access.check(3), access.NONE)
        patreon_queries.getTrial.return_value = startedDaysAgo(1)
        self.assertEqual(access.check(3), access.TRIAL)
        patreon_queries.getTrial.assert_called_with(3)

    def test_check_a_server_with_no_patrons_or_ignore_list(self):
        utils.getGuildsForPatreonToIgnore.return_value = None
        patreon_queries.getAllPatrons.return_value = None
        self.assertEqual(access.check(3), access.NONE)

    def test_check_a_private_message_by_the_servers_it_could_come_from(self):
        self.assertEqual(access.check(None, [3, 1]), access.IGNORED)
        self.assertEqual(access.check(None, [3, 2]), access.SUBSCRIBED)
        self.assertEqual(access.check(None, []), access.NONE)
        patreon_queries.getAllTrials.assert_not_called()
        self.assertEqual(access.check(None, [3, 4]), access.NONE)
        # an ended trial doesn't count, a running one does
        patreon_queries.getAllTrials.return_value = {'3': startedDaysAgo(8), '4': startedDaysAgo(1)}
        self.assertEqual(access.check(None, [3]), access.NONE)
        self.assertEqual(access.check(None, [3, 4]), access.TRIAL)

    def test_is_active_for_what_gbot_does_on_its_own(self):
        self.assertTrue(access.isActive(2))
        self.assertFalse(access.isActive(3))

    def test_is_active_remembers_its_answer_for_a_minute(self):
        clock = MagicMock(return_value = 1000.0)
        with patch.object(access.time, 'monotonic', clock):
            self.assertTrue(access.isActive(2))
            self.assertTrue(access.isActive(2))
            self.assertEqual(patreon_queries.getAllPatrons.call_count, 1)
            clock.return_value = 1000.0 + access.ACTIVE_SECONDS + 1
            access.isActive(2)
            self.assertEqual(patreon_queries.getAllPatrons.call_count, 2)

    def test_trial_ending(self):
        self.assertIsNone(access.trialEnding(3))
        patreon_queries.getTrial.return_value = startedDaysAgo(2)
        self.assertEqual(access.trialEnding(3), NOW + timedelta(days = 5))
        # a subscribed server isn't on a trial, whatever its record says
        self.assertIsNone(access.trialEnding(2))

    def test_a_server_gets_one_trial_ever(self):
        patreon_queries.setTrial.side_effect = lambda serverId, started: setattr(patreon_queries.getTrial, 'return_value', {'started': started})
        with self.assertLogs(level = 'INFO') as logged:
            self.assertEqual(access.startTrial(3), NOW + timedelta(days = 7))
        self.assertEqual(logged.records[0].getMessage(), 'GBot started a free trial in server 3.')
        patreon_queries.setTrial.assert_called_once_with(3, NOW.isoformat())
        # re-added during it: the same trial, not a new one
        self.assertEqual(access.startTrial(3), NOW + timedelta(days = 7))
        # re-added after it: none
        patreon_queries.getTrial.return_value = startedDaysAgo(30)
        self.assertIsNone(access.startTrial(3))
        self.assertEqual(patreon_queries.setTrial.call_count, 1)

    def test_no_trial_for_a_subscribed_or_ignored_server_or_when_trials_are_off(self):
        self.assertIsNone(access.startTrial(1))
        self.assertIsNone(access.startTrial(2))
        GBotPropertiesManager.TRIAL_DAYS = 0
        self.assertIsNone(access.startTrial(3))
        patreon_queries.setTrial.assert_not_called()

    def test_reminders_two_days_left_the_last_day_and_the_end(self):
        def due(days, reminded = None):
            trial = startedDaysAgo(days, **({} if reminded is None else {'reminded': reminded}))
            return access.reminderDue(trial, access.state(3, [], set(), trial))
        self.assertIsNone(due(4.9))
        self.assertEqual(due(5), access.REMINDER_TWO_DAYS)
        self.assertIsNone(due(5.5, access.REMINDER_TWO_DAYS))
        self.assertEqual(due(6), access.REMINDER_LAST_DAY)
        self.assertEqual(due(6, access.REMINDER_TWO_DAYS), access.REMINDER_LAST_DAY)
        self.assertIsNone(due(6.5, access.REMINDER_LAST_DAY))
        self.assertEqual(due(7, access.REMINDER_LAST_DAY), access.REMINDER_ENDED)
        self.assertIsNone(due(8, access.REMINDER_ENDED))
        # one missed while GBot was offline is skipped rather than sent late
        self.assertEqual(due(7), access.REMINDER_ENDED)
        # nothing once GBot is leaving, or for a subscribed server
        self.assertIsNone(due(11))
        self.assertIsNone(access.reminderDue(startedDaysAgo(6), access.SUBSCRIBED))

    def test_reminder_text(self):
        trial = startedDaysAgo(5)
        ends = int((NOW + timedelta(days = 2)).timestamp())
        leaves = int((NOW + timedelta(days = 5)).timestamp())
        how = "To keep GBot, subscribe on Patreon, then run `/patreon` with this server's ID, `3`, in the GBot Patreon server."
        self.assertEqual(access.reminderText(3, trial, access.REMINDER_TWO_DAYS), f"🎁 GBot's free trial in this server ends <t:{ends}:R>. {how}")
        self.assertEqual(access.reminderText(3, trial, access.REMINDER_LAST_DAY), f"🎁 GBot's free trial in this server ends <t:{ends}:R>. That's the last day. {how}")
        self.assertEqual(access.reminderText(3, trial, access.REMINDER_ENDED), f"🎁 GBot's free trial in this server has ended, so its commands now ask to subscribe. Without a subscription GBot leaves after <t:{leaves}:D>, and its settings here go with it. {how}")

    def test_what_a_refusal_and_a_lapse_notice_say(self):
        self.assertEqual(access.endedText(3, False), "GBot's free trial in this server has ended. To keep GBot, subscribe on Patreon, then run `/patreon` with this server's ID, `3`, in the GBot Patreon server.")
        renew = "To keep GBot, renew on Patreon, or have someone else subscribe and run `/patreon` with this server's ID, `3`, in the GBot Patreon server."
        self.assertEqual(access.endedText(3, True), f"This server's GBot subscription has ended. {renew}")
        leaves = int((NOW + timedelta(days = 3)).timestamp())
        self.assertEqual(access.lapseText(3, {'lapsed': NOW.isoformat()}), f"💳 This server's GBot subscription has ended, so its commands now ask to subscribe. Without one GBot leaves after <t:{leaves}:D>, and its settings here go with it. {renew}")

    def test_utc_now_is_aware(self):
        self.assertEqual(REAL_UTC_NOW().tzinfo, timezone.utc)
