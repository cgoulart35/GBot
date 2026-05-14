#region IMPORTS
import unittest
from unittest.mock import MagicMock
from werkzeug.exceptions import HTTPException

from GBotDiscord.src.leaderboards import leaderboards_queries
from GBotDiscord.src.quart_api.leaderboards_resource import Leaderboard
#endregion

_ORIGINAL_LB_FUNCS = {
    name: getattr(leaderboards_queries, name)
    for name in dir(leaderboards_queries)
    if callable(getattr(leaderboards_queries, name)) and not name.startswith('_')
}


# to run this test suite:
#   - execute the following command from the GBot directory: python -m unittest GBotDiscord/test/quart_api/leaderboards_resource_test.py
#   - or use the "Python: Current File" run configuration to run leaderboards_resource_test.py
#   - or use the "Python: Current File" run configuration to run tests.py to run all test suites
class TestLeaderboardResource(unittest.TestCase):

    @classmethod
    def setUpClass(self):
        print('\nExecuting leaderboards_resource unit tests...\n')

    @classmethod
    def tearDownClass(self):
        print('\n\nCompleted leaderboards_resource unit tests.\n')

    def setUp(self):
        for name, fn in _ORIGINAL_LB_FUNCS.items():
            setattr(leaderboards_queries, name, fn)

    def test_get_returns_leaderboard_query_result(self):
        expected = {'u1': {'balance': '21.00', 'username': 'alice'}}
        leaderboards_queries.getLeaderboard = MagicMock(return_value=expected)

        result = Leaderboard.get()

        self.assertEqual(result, expected)
        leaderboards_queries.getLeaderboard.assert_called_once_with()

    def test_get_aborts_400_when_query_raises(self):
        leaderboards_queries.getLeaderboard = MagicMock(side_effect=Exception('db down'))

        with self.assertRaises(HTTPException) as cm:
            Leaderboard.get()
        self.assertEqual(cm.exception.code, 400)


if __name__ == '__main__':
    unittest.main()
