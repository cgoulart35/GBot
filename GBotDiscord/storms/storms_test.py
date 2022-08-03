#region IMPORTS
import unittest

#endregion

# to run this test suite:
#   - execute the following command from the GBot directory: python -m unittest GBotDiscord/storms/storms_test.py
#   - or use the "Python: Current File" run configuration to run storms_test.py
#   - or use the "Python: Current File" run configuration to run tests.py to run all test suites
class TestStorms(unittest.TestCase):

    @classmethod
    def setUpClass(self):
        print('\nExecuting storms unit tests...\n')

    @classmethod
    def tearDownClass(self):
        print('\n\nCompleted storms unit tests.\n')

    def test_on_guild_join(self):
        pass

    def test_on_guild_remove(self):
        pass

    def test_on_ready(self):
        pass

    def test_storm_invoker(self):
        pass

    def test_umbrella(self):
        pass

    def test_guess(self):
        pass

    def test_bet(self):
        pass

if __name__ == '__main__':
    unittest.main()