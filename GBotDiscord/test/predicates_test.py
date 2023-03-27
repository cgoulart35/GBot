#region IMPORTS
import unittest

#endregion

# to run this test suite:
#   - execute the following command from the GBot directory: python -m unittest GBotDiscord/test/predicates_test.py
#   - or use the "Python: Current File" run configuration to run predicates_test.py
#   - or use the "Python: Current File" run configuration to run tests.py to run all test suites
class TestPredicates(unittest.IsolatedAsyncioTestCase):

    @classmethod
    def setUpClass(self):
        print('\nExecuting predicates unit tests...\n')

    @classmethod
    def tearDownClass(self):
        print('\n\nCompleted predicates unit tests.\n')

if __name__ == '__main__':
    unittest.main()