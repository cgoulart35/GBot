#region IMPORTS
import unittest
from unittest.mock import MagicMock, AsyncMock
import nextcord
from nextcord.ext import commands
from datetime import datetime, timedelta

from GBotDiscord.src.presence.presence_cog import Presence
from GBotDiscord.src.properties import GBotPropertiesManager
#endregion

# to run this test suite:
#   - execute the following command from the GBot directory: python -m unittest GBotDiscord/test/presence/presence_test.py
#   - or use the "Python: Current File" run configuration to run presence_test.py
#   - or use the "Python: Current File" run configuration to run tests.py to run all test suites
class TestPresence(unittest.IsolatedAsyncioTestCase):

    @classmethod
    def setUpClass(self):
        print('\nExecuting presence unit tests...\n')

    @classmethod
    def tearDownClass(self):
        print('\n\nCompleted presence unit tests.\n')

    def setUp(self):
        GBotPropertiesManager.GBOT_VERSION = '1.2.3'

        self.client: nextcord.Client = commands.Bot()
        self.client.change_presence = AsyncMock()

        self.presence: Presence = Presence(self.client)
        self.presence.logger = MagicMock()

    async def test_on_ready_populates_activities_and_starts_loop(self):
        self.presence.loop_presence = MagicMock()
        await self.presence.on_ready()
        self.assertEqual(len(self.presence.default_presence_activities), 3)
        activities = self.presence.default_presence_activities
        self.assertIsInstance(activities[0], nextcord.Game)
        self.assertEqual(activities[0].name, 'GBot 1.2.3')
        self.assertEqual(activities[1].type, nextcord.ActivityType.listening)
        self.assertEqual(activities[1].name, 'slash commands')
        self.assertEqual(activities[2].type, nextcord.ActivityType.watching)
        self.assertEqual(activities[2].name, 'user messages')
        self.presence.loop_presence.start.assert_called_once()

    # A-12: on_ready re-fires on every gateway RESUME/READY; it used to append the same three
    # activities each time, growing the list without bound on a long-running process.
    async def test_on_ready_does_not_duplicate_activities_when_it_refires(self):
        self.presence.loop_presence = MagicMock()
        await self.presence.on_ready()
        await self.presence.on_ready()
        await self.presence.on_ready()
        self.assertEqual(len(self.presence.default_presence_activities), 3)

    async def test_on_ready_handles_runtime_error_from_start(self):
        self.presence.loop_presence = MagicMock()
        self.presence.loop_presence.start.side_effect = RuntimeError()
        await self.presence.on_ready()
        self.presence.logger.info.assert_called_once_with('loop_presence task is already launched and is not completed.')

    async def test_loop_presence_changes_presence_and_increments_index(self):
        activity1, activity2, activity3 = MagicMock(), MagicMock(), MagicMock()
        self.presence.default_presence_activities = [activity1, activity2, activity3]
        self.presence.presence_index = 0
        self.presence.custom_presence_expire_time = datetime.now() - timedelta(seconds=10)
        await self.presence.loop_presence()
        self.client.change_presence.assert_called_once_with(status=nextcord.Status.online, activity=activity1)
        self.assertEqual(self.presence.presence_index, 1)

    async def test_loop_presence_wraps_index_to_zero(self):
        activity1, activity2, activity3 = MagicMock(), MagicMock(), MagicMock()
        self.presence.default_presence_activities = [activity1, activity2, activity3]
        self.presence.presence_index = 2
        self.presence.custom_presence_expire_time = datetime.now() - timedelta(seconds=10)
        await self.presence.loop_presence()
        self.client.change_presence.assert_called_once_with(status=nextcord.Status.online, activity=activity3)
        self.assertEqual(self.presence.presence_index, 0)

    async def test_loop_presence_skipped_when_custom_presence_not_expired(self):
        self.presence.default_presence_activities = [MagicMock()]
        self.presence.presence_index = 0
        self.presence.custom_presence_expire_time = datetime.now() + timedelta(hours=1)
        await self.presence.loop_presence()
        self.client.change_presence.assert_not_called()
        self.assertEqual(self.presence.presence_index, 0)

    async def test_loop_presence_logs_exception(self):
        self.presence.default_presence_activities = []
        self.presence.presence_index = 0
        self.presence.custom_presence_expire_time = datetime.now() - timedelta(seconds=10)
        await self.presence.loop_presence()
        self.client.change_presence.assert_not_called()
        self.presence.logger.error.assert_called_once()
        logArg = self.presence.logger.error.call_args[0][0]
        self.assertIn('Error in Presence.loop_presence():', logArg)

    async def test_change_presence_success(self):
        activity = MagicMock()
        expireTime = datetime.now() + timedelta(minutes=5)
        result = await self.presence.changePresence(activity, expireTime)
        self.assertTrue(result)
        self.assertEqual(self.presence.custom_presence_expire_time, expireTime)
        self.client.change_presence.assert_called_once_with(status=nextcord.Status.online, activity=activity)

    async def test_change_presence_exception_returns_false_and_logs(self):
        self.client.change_presence = AsyncMock(side_effect=Exception('boom'))
        activity = MagicMock()
        expireTime = datetime.now() + timedelta(minutes=5)
        result = await self.presence.changePresence(activity, expireTime)
        self.assertFalse(result)
        self.presence.logger.error.assert_called_once()
        logArg = self.presence.logger.error.call_args[0][0]
        self.assertIn('Error in Presence.changePresence():', logArg)

    def test_setup_adds_cog(self):
        from GBotDiscord.src.presence import presence_cog
        client = MagicMock()
        presence_cog.setup(client)
        client.add_cog.assert_called_once()
        addedCog = client.add_cog.call_args[0][0]
        self.assertIsInstance(addedCog, Presence)

if __name__ == '__main__':
    unittest.main()
