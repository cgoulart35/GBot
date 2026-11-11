#region IMPORTS
import unittest
from unittest.mock import MagicMock

from GBotDiscord.src.firebase import GBotFirebaseService
from GBotDiscord.src.hype import hype_queries
#endregion

# to run this test suite:
#   - execute the following command from the GBot directory: python -m unittest GBotDiscord/test/hype/hype_queries_test.py
#   - or use the "Python: Current File" run configuration to run hype_queries_test.py
#   - or use the "Python: Current File" run configuration to run tests.py to run all test suites

_ORIGINAL_HYPE_FUNCS = {
    name: getattr(hype_queries, name)
    for name in dir(hype_queries)
    if callable(getattr(hype_queries, name)) and not name.startswith('_')
}


def _mockResult(value):
    result = MagicMock()
    result.val.return_value = value
    return result


class TestHypeQueries(unittest.TestCase):

    @classmethod
    def setUpClass(self):
        print('\nExecuting hype queries unit tests...\n')

    @classmethod
    def tearDownClass(self):
        print('\n\nCompleted hype queries unit tests.\n')

    def setUp(self):
        for name, fn in _ORIGINAL_HYPE_FUNCS.items():
            setattr(hype_queries, name, fn)
        self._saved = {
            name: getattr(GBotFirebaseService, name)
            for name in ('get', 'set', 'push', 'update', 'remove')
        }
        GBotFirebaseService.get = MagicMock()
        GBotFirebaseService.push = MagicMock()
        GBotFirebaseService.remove = MagicMock()
        GBotFirebaseService.update = MagicMock()

    def tearDown(self):
        for name, fn in self._saved.items():
            setattr(GBotFirebaseService, name, fn)

    def test_updateMatch_changes_only_the_pattern_and_responses(self):
        GBotFirebaseService.get.return_value = _mockResult({'regex': 'g', 'responses': ['a'], 'isReaction': False})
        self.assertTrue(hype_queries.updateMatch('9', 'm1', 'gg', ['a']))
        GBotFirebaseService.get.assert_called_once_with(['hype_servers', '9', 'm1'])
        GBotFirebaseService.update.assert_called_once_with(['hype_servers', '9', 'm1'], {'regex': 'gg', 'responses': ['a']})

    def test_updateMatch_never_brings_back_a_deleted_match(self):
        # half a match, with no isReaction, would fail on every message in its server
        GBotFirebaseService.get.return_value = _mockResult(None)
        self.assertFalse(hype_queries.updateMatch('9', 'm1', 'gg', ['a']))
        GBotFirebaseService.update.assert_not_called()

    def test_createMatch_pushes_dict(self):
        hype_queries.createMatch('9', 'regex', ['r1', 'r2'], True)
        GBotFirebaseService.push.assert_called_once_with(
            ['hype_servers', '9'],
            {'regex': 'regex', 'responses': ['r1', 'r2'], 'isReaction': True}
        )

    def test_removeMatch_calls_remove(self):
        hype_queries.removeMatch('9', 'matchId')
        GBotFirebaseService.remove.assert_called_once_with(['hype_servers', '9', 'matchId'])

    def test_getAllServerMatches_returns_val(self):
        GBotFirebaseService.get.return_value = _mockResult({'matchId': {'regex': 'r'}})
        self.assertEqual(hype_queries.getAllServerMatches('9'), {'matchId': {'regex': 'r'}})
        GBotFirebaseService.get.assert_called_once_with(['hype_servers', '9'])


if __name__ == '__main__':
    unittest.main()
