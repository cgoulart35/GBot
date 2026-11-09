#region IMPORTS
import unittest
from unittest.mock import MagicMock, patch

from GBotDiscord.src.firebase import GBotFirebaseService
from GBotDiscord.src.reminders import reminders_queries
#endregion

def result(value):
    made = MagicMock()
    made.val.return_value = value
    return made

class TestRemindersQueries(unittest.TestCase):

    @classmethod
    def setUpClass(self):
        print('\n\nStarting reminders queries unit tests...\n')

    @classmethod
    def tearDownClass(self):
        print('\n\nCompleted reminders queries unit tests.\n')

    def setUp(self):
        for name in ('get', 'set', 'push', 'update', 'remove'):
            started = patch.object(GBotFirebaseService, name, MagicMock(return_value = result({'a': 1})))
            started.start()
            self.addCleanup(started.stop)

    def test_reading(self):
        self.assertEqual(reminders_queries.getAllReminders(), {'a': 1})
        GBotFirebaseService.get.assert_called_with(['reminders'])
        reminders_queries.getServerReminders(10)
        GBotFirebaseService.get.assert_called_with(['reminders', '10'])
        reminders_queries.getReminder(10, 'r1')
        GBotFirebaseService.get.assert_called_with(['reminders', '10', 'r1'])
        reminders_queries.getTimezone(1)
        GBotFirebaseService.get.assert_called_with(['users', '1', 'timezone'])

    def test_writing(self):
        GBotFirebaseService.push.return_value = 'r1'
        self.assertEqual(reminders_queries.addReminder(10, {'text': 'x'}), 'r1')
        GBotFirebaseService.push.assert_called_once_with(['reminders', '10'], {'text': 'x'})
        reminders_queries.updateReminder(10, 'r1', {'nextAt': 'y'})
        GBotFirebaseService.update.assert_called_once_with(['reminders', '10', 'r1'], {'nextAt': 'y'})
        reminders_queries.removeReminder(10, 'r1')
        GBotFirebaseService.remove.assert_called_once_with(['reminders', '10', 'r1'])
        reminders_queries.setTimezone(1, 'America/Denver')
        GBotFirebaseService.set.assert_called_once_with(['users', '1', 'timezone'], 'America/Denver')
