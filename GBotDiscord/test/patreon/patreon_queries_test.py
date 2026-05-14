#region IMPORTS
import unittest
from unittest.mock import MagicMock

from GBotDiscord.src.firebase import GBotFirebaseService
from GBotDiscord.src.patreon import patreon_queries
#endregion

# to run this test suite:
#   - execute the following command from the GBot directory: python -m unittest GBotDiscord/test/patreon/patreon_queries_test.py
#   - or use the "Python: Current File" run configuration to run patreon_queries_test.py
#   - or use the "Python: Current File" run configuration to run tests.py to run all test suites

# Snapshot the real module-level functions at import time. The patreon cog test suite
# replaces `patreon_queries.getAllPatrons` with a MagicMock and never restores it —
# the snapshot makes this suite order-independent.
_ORIGINAL_PATREON_FUNCS = {
    name: getattr(patreon_queries, name)
    for name in dir(patreon_queries)
    if callable(getattr(patreon_queries, name)) and not name.startswith('_')
}


def _mockResult(value):
    result = MagicMock()
    result.val.return_value = value
    return result


class TestPatreonQueries(unittest.TestCase):

    @classmethod
    def setUpClass(self):
        print('\nExecuting patreon queries unit tests...\n')

    @classmethod
    def tearDownClass(self):
        print('\n\nCompleted patreon queries unit tests.\n')

    def setUp(self):
        for name, fn in _ORIGINAL_PATREON_FUNCS.items():
            setattr(patreon_queries, name, fn)
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

    def test_getAllPatrons_returns_val(self):
        GBotFirebaseService.get.return_value = _mockResult({'1000': {'serverId': '9'}})
        self.assertEqual(patreon_queries.getAllPatrons(), {'1000': {'serverId': '9'}})
        GBotFirebaseService.get.assert_called_once_with(['patreon_members'])

    def test_getAllPatrons_returns_none_when_empty(self):
        GBotFirebaseService.get.return_value = _mockResult(None)
        self.assertIsNone(patreon_queries.getAllPatrons())

    def test_getPatronServerId_returns_val(self):
        GBotFirebaseService.get.return_value = _mockResult('9')
        self.assertEqual(patreon_queries.getPatronServerId('1000'), '9')
        GBotFirebaseService.get.assert_called_once_with(['patreon_members', '1000', 'serverId'])

    def test_addPatronEntry_writes_server_id_string(self):
        patreon_queries.addPatronEntry('1000', 9)
        GBotFirebaseService.set.assert_called_once_with(['patreon_members', '1000', 'serverId'], '9')

    def test_removePatronEntry_removes_member(self):
        patreon_queries.removePatronEntry('1000')
        GBotFirebaseService.remove.assert_called_once_with(['patreon_members', '1000'])


if __name__ == '__main__':
    unittest.main()
