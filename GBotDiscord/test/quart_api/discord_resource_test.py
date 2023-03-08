#region IMPORTS
import unittest

#endregion

# to run this test suite:
#   - execute the following command from the GBot directory: python -m unittest GBotDiscord/test/quart_api/discord_resource_test.py
#   - or use the "Python: Current File" run configuration to run discord_resource_test.py
#   - or use the "Python: Current File" run configuration to run tests.py to run all test suites
class TestDiscordResource(unittest.TestCase):

    @classmethod
    def setUpClass(self):
        print('\nExecuting discord_resource unit tests...\n')

    @classmethod
    def tearDownClass(self):
        print('\n\nCompleted discord_resource unit tests.\n')

    def test_get(self):
        pass

    def test_post(self):
        pass

if __name__ == '__main__':
    unittest.main()