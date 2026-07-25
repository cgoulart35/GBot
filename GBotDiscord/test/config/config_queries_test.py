#region IMPORTS
import unittest
from unittest.mock import MagicMock

from GBotDiscord.src.firebase import GBotFirebaseService
from GBotDiscord.src.config import config_queries
#endregion

# to run this test suite:
#   - execute the following command from the GBot directory: python -m unittest GBotDiscord/test/config/config_queries_test.py
#   - or use the "Python: Current File" run configuration to run config_queries_test.py
#   - or use the "Python: Current File" run configuration to run tests.py to run all test suites

# Other test suites replace `config_queries.getServerValue` etc. with MagicMocks at module
# scope and never restore them. Snapshotting the originals here keeps this suite order-independent.
_ORIGINAL_CONFIG_FUNCS = {
    name: getattr(config_queries, name)
    for name in dir(config_queries)
    if callable(getattr(config_queries, name)) and not name.startswith('_')
}


def _mockResult(value):
    result = MagicMock()
    result.val.return_value = value
    return result


class TestConfigQueries(unittest.TestCase):

    @classmethod
    def setUpClass(self):
        print('\nExecuting config queries unit tests...\n')

    @classmethod
    def tearDownClass(self):
        print('\n\nCompleted config queries unit tests.\n')

    def setUp(self):
        for name, fn in _ORIGINAL_CONFIG_FUNCS.items():
            setattr(config_queries, name, fn)
        self._saved = {
            name: getattr(GBotFirebaseService, name)
            for name in ('get', 'set', 'push', 'update', 'remove')
        }
        GBotFirebaseService.get = MagicMock()
        GBotFirebaseService.set = MagicMock()
        GBotFirebaseService.remove = MagicMock()

    def tearDown(self):
        for name, fn in self._saved.items():
            setattr(GBotFirebaseService, name, fn)

    def test_getAllServers_returns_val(self):
        GBotFirebaseService.get.return_value = _mockResult({'9': {'prefix': '.'}})
        self.assertEqual(config_queries.getAllServers(), {'9': {'prefix': '.'}})
        GBotFirebaseService.get.assert_called_once_with(['servers'])

    def test_getAllServerValues_returns_val(self):
        GBotFirebaseService.get.return_value = _mockResult({'prefix': '.'})
        self.assertEqual(config_queries.getAllServerValues('9'), {'prefix': '.'})
        GBotFirebaseService.get.assert_called_once_with(['servers', '9'])

    def test_getServerValue_returns_val(self):
        GBotFirebaseService.get.return_value = _mockResult('.')
        self.assertEqual(config_queries.getServerValue('9', 'prefix'), '.')
        GBotFirebaseService.get.assert_called_once_with(['servers', '9', 'prefix'])

    def test_setServerValue_calls_set(self):
        config_queries.setServerValue('9', 'prefix', '.')
        GBotFirebaseService.set.assert_called_once_with(['servers', '9', 'prefix'], '.')

    def test_clearServerValues_removes(self):
        config_queries.clearServerValues('9')
        GBotFirebaseService.remove.assert_called_once_with(['servers', '9'])

    def test_initServerValues_writes_defaults(self):
        config_queries.initServerValues('9', '7.0.0')
        expected = {
            'version': '7.0.0',
            'prefix': '.',
            'toggle_music': False,
            'toggle_gcoin': False,
            'toggle_gtrade': False,
            'toggle_hype': False,
            'toggle_storms': False,
            'toggle_legacy_prefix_commands': False,
            'toggle_who_dis': False,
        }
        GBotFirebaseService.set.assert_called_once_with(['servers', '9'], expected)

    def test_upgradeServerValues_all_fields_missing_sets_all_defaults(self):
        GBotFirebaseService.get.return_value = _mockResult({})
        config_queries.upgradeServerValues('9', '7.0.0')
        set_calls = [call.args for call in GBotFirebaseService.set.call_args_list]
        self.assertIn((['servers', '9', 'version'], '7.0.0'), set_calls)
        for toggle in ('toggle_music', 'toggle_gcoin', 'toggle_gtrade', 'toggle_hype',
                       'toggle_storms', 'toggle_legacy_prefix_commands', 'toggle_who_dis'):
            self.assertIn((['servers', '9', toggle], False), set_calls)

    def test_upgradeServerValues_all_fields_present_only_sets_version(self):
        GBotFirebaseService.get.return_value = _mockResult({
            'toggle_music': True,
            'toggle_gcoin': True,
            'toggle_gtrade': True,
            'toggle_hype': True,
            'toggle_storms': True,
            'toggle_legacy_prefix_commands': True,
            'toggle_who_dis': True,
        })
        config_queries.upgradeServerValues('9', '7.0.0')
        set_calls = [call.args for call in GBotFirebaseService.set.call_args_list]
        # only the version is set
        self.assertEqual(set_calls, [(['servers', '9', 'version'], '7.0.0')])

    def test_upgradeServerValues_none_value_treated_as_missing(self):
        # an existing key with value None should still trigger the default set
        GBotFirebaseService.get.return_value = _mockResult({
            'toggle_music': None,
            'toggle_gcoin': True,
            'toggle_gtrade': True,
            'toggle_hype': True,
            'toggle_storms': True,
            'toggle_legacy_prefix_commands': True,
            'toggle_who_dis': True,
        })
        config_queries.upgradeServerValues('9', '7.0.0')
        set_calls = [call.args for call in GBotFirebaseService.set.call_args_list]
        self.assertIn((['servers', '9', 'toggle_music'], False), set_calls)


if __name__ == '__main__':
    unittest.main()
