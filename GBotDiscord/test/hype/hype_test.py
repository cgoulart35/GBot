#region IMPORTS
import unittest

#endregion

# to run this test suite:
#   - execute the following command from the GBot directory: python -m unittest GBotDiscord/test/hype/hype_test.py
#   - or use the "Python: Current File" run configuration to run hype_test.py
#   - or use the "Python: Current File" run configuration to run tests.py to run all test suites
class TestHype(unittest.TestCase):

    @classmethod
    def setUpClass(self):
        print('\nExecuting hype unit tests...\n')

    @classmethod
    def tearDownClass(self):
        print('\n\nCompleted hype unit tests.\n')

    def test_message(self):
        pass

    def test_hype(self):
        pass

    def test_react(self):
        pass

if __name__ == '__main__':
    unittest.main()