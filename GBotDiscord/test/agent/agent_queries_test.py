#region IMPORTS
import unittest
from unittest.mock import MagicMock, patch

from cryptography.fernet import Fernet

from GBotDiscord.src.agent import agent_queries
from GBotDiscord.src.firebase import GBotFirebaseService
from GBotDiscord.src.properties import GBotPropertiesManager
#endregion

def result(value):
    return MagicMock(val = MagicMock(return_value = value))

# to run this test suite:
#   - execute the following command from the GBot directory: python -m unittest GBotDiscord/test/agent/agent_queries_test.py
class TestAgentQueries(unittest.TestCase):

    def setUp(self):
        GBotPropertiesManager.AGENT_KEY_SECRET = Fernet.generate_key().decode()
        GBotPropertiesManager.AGENT_MAX_MEMORIES = 2
        for name in ('get', 'set', 'push', 'update', 'remove'):
            patcher = patch.object(GBotFirebaseService, name, MagicMock())
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_a_key_is_never_stored_as_written(self):
        encrypted = agent_queries.encryptKey('sk-ant-secret')
        self.assertNotIn('sk-ant-secret', encrypted)
        self.assertEqual(agent_queries.decryptKey(encrypted), 'sk-ant-secret')

    def test_a_key_from_another_secret_cannot_be_read(self):
        encrypted = agent_queries.encryptKey('sk-ant-secret')
        GBotPropertiesManager.AGENT_KEY_SECRET = Fernet.generate_key().decode()
        self.assertIsNone(agent_queries.decryptKey(encrypted))

    def test_decrypt_without_a_usable_secret_returns_nothing(self):
        encrypted = agent_queries.encryptKey('sk-ant-secret')
        for secret in (None, 'not a fernet key'):
            GBotPropertiesManager.AGENT_KEY_SECRET = secret
            self.assertIsNone(agent_queries.decryptKey(encrypted))

    def test_encrypt_without_a_usable_secret_raises(self):
        for secret, error in ((None, TypeError), ('not a fernet key', ValueError)):
            GBotPropertiesManager.AGENT_KEY_SECRET = secret
            with self.assertRaises(error):
                agent_queries.encryptKey('sk-ant-secret')

    def test_getServerConfig_defaults_to_empty(self):
        GBotFirebaseService.get.return_value = result(None)
        self.assertEqual(agent_queries.getServerConfig(1), {})
        GBotFirebaseService.get.return_value = result({'mode': 'off'})
        self.assertEqual(agent_queries.getServerConfig(1), {'mode': 'off'})

    def test_simple_writes_use_the_documented_paths(self):
        agent_queries.setServerValues(1, {'mode': 'off'})
        GBotFirebaseService.update.assert_called_once_with(['agent_servers', 1], {'mode': 'off'})
        agent_queries.removeServerValue(1, 'apiKey')
        GBotFirebaseService.remove.assert_called_with(['agent_servers', 1, 'apiKey'])
        agent_queries.setChannelValue(1, 2, 'mode', 'off')
        GBotFirebaseService.set.assert_called_once_with(['agent_servers', 1, 'channels', 2, 'mode'], 'off')
        agent_queries.clearServer(1)
        GBotFirebaseService.remove.assert_called_with(['agent_servers', 1])

    def test_clearing_a_channel_value_removes_it(self):
        # the real database raises on set(None), which is what /agent instructions none first did
        agent_queries.setChannelValue(1, 2, 'instructions', None)
        GBotFirebaseService.remove.assert_called_once_with(['agent_servers', 1, 'channels', 2, 'instructions'])
        GBotFirebaseService.set.assert_not_called()

    def test_saveMemory_records_who_saved_it(self):
        GBotFirebaseService.get.return_value = result(None)
        self.assertEqual(agent_queries.saveMemory(1, 'text', 'chris', '7', True, '2026-11-02'), agent_queries.MEMORY_SAVED)
        GBotFirebaseService.push.assert_called_once_with(['agent_servers', 1, 'memories'], {'text': 'text', 'savedBy': 'chris', 'savedById': '7', 'byAdmin': True, 'date': '2026-11-02'})

    def test_saveMemory_stops_when_full(self):
        GBotFirebaseService.get.return_value = result({'a': {}, 'b': {}})
        self.assertEqual(agent_queries.saveMemory(1, 'text', 'chris', '7', True, '2026-11-02'), agent_queries.MEMORY_FULL)
        GBotFirebaseService.push.assert_not_called()

    def test_saveMemory_remembers_the_channel_it_is_for(self):
        GBotFirebaseService.get.return_value = result(None)
        agent_queries.saveMemory(1, 'text', 'chris', '7', True, '2026-11-02', '55')
        self.assertEqual(GBotFirebaseService.push.call_args.args[1]['channelId'], '55')

    def test_saveMemory_stops_a_member_at_their_limit_only(self):
        GBotFirebaseService.get.return_value = result({'a': {'savedById': '7'}})
        self.assertEqual(agent_queries.saveMemory(1, 'text', 'chris', '7', False, '2026-11-02', None, 1), agent_queries.MEMORY_MEMBER_LIMIT)
        GBotFirebaseService.push.assert_not_called()
        self.assertEqual(agent_queries.saveMemory(1, 'text', 'sam', '8', False, '2026-11-02', None, 1), agent_queries.MEMORY_SAVED)
        self.assertEqual(agent_queries.saveMemory(1, 'text', 'chris', '7', True, '2026-11-02'), agent_queries.MEMORY_SAVED)

    def test_resetPlace_only_touches_the_channel_it_names(self):
        GBotFirebaseService.get.return_value = result({'a': {'channelId': '2'}, 'b': {'channelId': '3'}, 'c': {}})
        agent_queries.resetPlace(1, 2, ['mode'], True)
        self.assertEqual([call.args[0] for call in GBotFirebaseService.remove.call_args_list], [['agent_servers', 1, 'channels', 2, 'mode'], ['agent_servers', 1, 'memories', 'a']])

    def test_resetPlace_on_the_server_leaves_channels_alone(self):
        GBotFirebaseService.get.return_value = result({'a': {'channelId': '2'}, 'c': {}})
        agent_queries.resetPlace(1, None, ['mode'], True)
        self.assertEqual([call.args[0] for call in GBotFirebaseService.remove.call_args_list], [['agent_servers', 1, 'mode'], ['agent_servers', 1, 'memories', 'c']])

    def test_resetPlace_keeps_memories_unless_told(self):
        GBotFirebaseService.get.return_value = result(None)
        agent_queries.resetPlace(1, 2, [], False)
        GBotFirebaseService.remove.assert_not_called()
        agent_queries.resetPlace(1, 2, [], True)
        GBotFirebaseService.remove.assert_not_called()

    def test_setLimit_writes_only_that_limit(self):
        agent_queries.setLimit(1, 'tokens', 5)
        GBotFirebaseService.update.assert_called_once_with(['agent_servers', 1, 'limits'], {'tokens': 5})

    def test_changeMemory_forgets(self):
        memory = {'text': 'old'}
        GBotFirebaseService.get.return_value = result({'a': memory})
        self.assertEqual(agent_queries.changeMemory(1, 'a', lambda found: True), (memory, True))
        GBotFirebaseService.remove.assert_called_once_with(['agent_servers', 1, 'memories', 'a'])
        GBotFirebaseService.update.assert_not_called()

    def test_changeMemory_updates_only_the_text_and_who_edited(self):
        memory = {'text': 'old', 'byAdmin': False}
        GBotFirebaseService.get.return_value = result({'a': memory})
        self.assertEqual(agent_queries.changeMemory(1, 'a', lambda found: True, 'new', 'chris'), (memory, True))
        GBotFirebaseService.update.assert_called_once_with(['agent_servers', 1, 'memories', 'a'], {'text': 'new', 'editedBy': 'chris'})
        GBotFirebaseService.remove.assert_not_called()

    def test_changeMemory_writes_nothing_when_not_allowed(self):
        memory = {'text': 'old'}
        GBotFirebaseService.get.return_value = result({'a': memory})
        self.assertEqual(agent_queries.changeMemory(1, 'a', lambda found: False, 'new', 'chris'), (memory, False))
        GBotFirebaseService.update.assert_not_called()
        GBotFirebaseService.remove.assert_not_called()

    def test_changeMemory_never_builds_a_path_from_an_unknown_id(self):
        for stored in ({'a': {'text': 'old'}}, None):
            GBotFirebaseService.get.return_value = result(stored)
            self.assertEqual(agent_queries.changeMemory(1, 'a/text', lambda found: True), (None, False))
        GBotFirebaseService.remove.assert_not_called()
        GBotFirebaseService.update.assert_not_called()

    def test_shared_usage_adds_up_within_a_day_and_starts_over_on_the_next(self):
        GBotFirebaseService.get.return_value = result({'day': '2026-11-02', 'tokens': 5})
        self.assertEqual(agent_queries.getSharedTokensUsed('2026-11-02'), 5)
        self.assertEqual(agent_queries.getSharedTokensUsed('2026-11-03'), 0)
        agent_queries.addSharedUsage('2026-11-02', 3)
        GBotFirebaseService.set.assert_called_with(['agent_shared', 'usage'], {'day': '2026-11-02', 'tokens': 8})
        GBotFirebaseService.get.return_value = result(None)
        self.assertEqual(agent_queries.getSharedTokensUsed('2026-11-02'), 0)

    def test_addUsage_adds_up_within_a_day_and_starts_over_on_the_next(self):
        GBotFirebaseService.get.return_value = result({'day': '2026-11-02', 'tokens': 5})
        agent_queries.addUsage(1, '2026-11-02', 3)
        GBotFirebaseService.set.assert_called_with(['agent_servers', 1, 'usage'], {'day': '2026-11-02', 'tokens': 8})
        agent_queries.addUsage(1, '2026-11-03', 3)
        GBotFirebaseService.set.assert_called_with(['agent_servers', 1, 'usage'], {'day': '2026-11-03', 'tokens': 3})
        GBotFirebaseService.get.return_value = result(None)
        agent_queries.addUsage(1, '2026-11-03', 2)
        GBotFirebaseService.set.assert_called_with(['agent_servers', 1, 'usage'], {'day': '2026-11-03', 'tokens': 2})
