#region IMPORTS
import unittest

#endregion

# to run this test suite:
#   - execute the following command from the GBot directory: python -m unittest GBotDiscord/config/config_test.py
#   - or use the "Python: Current File" run configuration to run config_test.py
#   - or use the "Python: Current File" run configuration to run tests.py to run all test suites
class TestConfig(unittest.TestCase):

    @classmethod
    def setUpClass(self):
        print('\nExecuting config unit tests...\n')

    @classmethod
    def tearDownClass(self):
        print('\n\nCompleted config unit tests.\n')

    def test_on_guild_join(self):
        pass

    def test_on_guild_remove(self):
        pass

    def test_on_ready(self):
        pass

    def test_config(self):
        pass

    def test_prefix(self):
        pass

    def test_role(self):
        pass

    def test_channel(self):
        pass

    def test_toggle(self):
        pass

if __name__ == '__main__':
    unittest.main()