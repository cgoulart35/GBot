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
        agent_queries.clearChannel(1, 2)
        GBotFirebaseService.remove.assert_called_with(['agent_servers', 1, 'channels', 2])
        agent_queries.removeMemory(1, 'm')
        GBotFirebaseService.remove.assert_called_with(['agent_servers', 1, 'memories', 'm'])
        agent_queries.clearServer(1)
        GBotFirebaseService.remove.assert_called_with(['agent_servers', 1])

    def test_saveMemory_records_who_saved_it(self):
        GBotFirebaseService.get.return_value = result(None)
        self.assertTrue(agent_queries.saveMemory(1, 'text', 'chris', True, '2026-11-02'))
        GBotFirebaseService.push.assert_called_once_with(['agent_servers', 1, 'memories'], {'text': 'text', 'savedBy': 'chris', 'byAdmin': True, 'date': '2026-11-02'})

    def test_saveMemory_stops_when_full(self):
        GBotFirebaseService.get.return_value = result({'a': {}, 'b': {}})
        self.assertFalse(agent_queries.saveMemory(1, 'text', 'chris', True, '2026-11-02'))
        GBotFirebaseService.push.assert_not_called()

    def test_addUsage_adds_up_within_a_day_and_starts_over_on_the_next(self):
        GBotFirebaseService.get.return_value = result({'day': '2026-11-02', 'tokens': 5})
        agent_queries.addUsage(1, '2026-11-02', 3)
        GBotFirebaseService.set.assert_called_with(['agent_servers', 1, 'usage'], {'day': '2026-11-02', 'tokens': 8})
        agent_queries.addUsage(1, '2026-11-03', 3)
        GBotFirebaseService.set.assert_called_with(['agent_servers', 1, 'usage'], {'day': '2026-11-03', 'tokens': 3})
        GBotFirebaseService.get.return_value = result(None)
        agent_queries.addUsage(1, '2026-11-03', 2)
        GBotFirebaseService.set.assert_called_with(['agent_servers', 1, 'usage'], {'day': '2026-11-03', 'tokens': 2})
