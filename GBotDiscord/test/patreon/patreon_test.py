#region IMPORTS
import unittest

#endregion

# to run this test suite:
#   - execute the following command from the GBot directory: python -m unittest GBotDiscord/test/patreon/patreon_test.py
#   - or use the "Python: Current File" run configuration to run patreon_test.py
#   - or use the "Python: Current File" run configuration to run tests.py to run all test suites
class TestPatreon(unittest.TestCase):

    @classmethod
    def setUpClass(self):
        print('\nExecuting patreon unit tests...\n')

    @classmethod
    def tearDownClass(self):
        print('\n\nCompleted patreon unit tests.\n')

    def test_on_ready(self):
        pass

    def test_patreon_validation(self):
        pass

    def test_patreon(self):
        pass

if __name__ == '__main__':
    unittest.main()