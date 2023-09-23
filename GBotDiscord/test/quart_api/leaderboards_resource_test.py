#region IMPORTS
import unittest

#endregion

# to run this test suite:
#   - execute the following command from the GBot directory: python -m unittest GBotDiscord/test/quart_api/leaderboards_resource.py
#   - or use the "Python: Current File" run configuration to run leaderboards_resource.py
#   - or use the "Python: Current File" run configuration to run tests.py to run all test suites
class TestLeaderboardResource(unittest.TestCase):

    @classmethod
    def setUpClass(self):
        print('\nExecuting leaderboards_resource unit tests...\n')

    @classmethod
    def tearDownClass(self):
        print('\n\nCompleted leaderboards_resource unit tests.\n')

    def test_get(self):
        pass

if __name__ == '__main__':
    unittest.main()