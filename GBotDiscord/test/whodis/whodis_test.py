#region IMPORTS
import unittest

#endregion

# to run this test suite:
#   - execute the following command from the GBot directory: python -m unittest GBotDiscord/test/whodis/whodis_test.py
#   - or use the "Python: Current File" run configuration to run whodis_test.py
#   - or use the "Python: Current File" run configuration to run tests.py to run all test suites
class TestWhoDis(unittest.TestCase):

    @classmethod
    def setUpClass(self):
        print('\nExecuting whodis unit tests...\n')

    @classmethod
    def tearDownClass(self):
        print('\n\nCompleted whodis unit tests.\n')

    def test_whodis(self):
        pass

if __name__ == '__main__':
    unittest.main()