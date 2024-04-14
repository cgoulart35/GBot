#region IMPORTS
import unittest
#endregion

# to run this test suite:
#   - execute the following command from the GBot directory: python -m unittest GBotDiscord/test/presence/presence_test.py
#   - or use the "Python: Current File" run configuration to run presence_test.py
#   - or use the "Python: Current File" run configuration to run tests.py to run all test suites
class TestPresence(unittest.IsolatedAsyncioTestCase):

    @classmethod
    def setUpClass(self):
        print('\nExecuting presence unit tests...\n')

    @classmethod
    def tearDownClass(self):
        print('\n\nCompleted presence unit tests.\n')

if __name__ == '__main__':
    unittest.main()