#region IMPORTS
import unittest

#endregion

# to run this test suite:
#   - execute the following command from the GBot directory: python -m unittest GBotDiscord/gcoin/gcoin_test.py
#   - or use the "Python: Current File" run configuration to run gcoin_test.py
#   - or use the "Python: Current File" run configuration to run tests.py to run all test suites
class TestGCoin(unittest.TestCase):

    @classmethod
    def setUpClass(self):
        print('\nExecuting gcoin unit tests...\n')

    @classmethod
    def tearDownClass(self):
        print('\n\nCompleted gcoin unit tests.\n')

    def test_send(self):
        pass

    def test_wallets(self):
        pass

    def test_wallet(self):
        pass

    def test_history(self):
        pass

if __name__ == '__main__':
    unittest.main()