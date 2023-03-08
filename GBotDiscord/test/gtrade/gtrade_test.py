#region IMPORTS
import unittest

#endregion

# to run this test suite:
#   - execute the following command from the GBot directory: python -m unittest GBotDiscord/test/gtrade/gtrade_test.py
#   - or use the "Python: Current File" run configuration to run gtrade_test.py
#   - or use the "Python: Current File" run configuration to run tests.py to run all test suites
class TestGTrade(unittest.TestCase):

    @classmethod
    def setUpClass(self):
        print('\nExecuting gtrade unit tests...\n')

    @classmethod
    def tearDownClass(self):
        print('\n\nCompleted gtrade unit tests.\n')

    def test_on_guild_remove(self):
        pass

    def test_on_ready(self):
        pass

    def test_remove_expired_transactions(self):
        pass

    def test_craft(self):
        pass

    def test_rename(self):
        pass

    def test_destroy(self):
        pass

    def test_items(self):
        pass

    def test_item(self):
        pass

    def test_market(self):
        pass

    def test_buy(self):
        pass

    def test_sell(self):
        pass

if __name__ == '__main__':
    unittest.main()