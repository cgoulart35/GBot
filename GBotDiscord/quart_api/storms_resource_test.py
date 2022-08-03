#region IMPORTS
import unittest

#endregion

# to run this test suite:
#   - execute the following command from the GBot directory: python -m unittest GBotDiscord/quart_api/storms_resource_test.py
#   - or use the "Python: Current File" run configuration to run storms_resource_test.py
#   - or use the "Python: Current File" run configuration to run tests.py to run all test suites
class TestStormsResource(unittest.TestCase):

    @classmethod
    def setUpClass(self):
        print('\nExecuting storms_resource unit tests...\n')

    @classmethod
    def tearDownClass(self):
        print('\n\nCompleted storms_resource unit tests.\n')

    def test_get(self):
        pass

    def test_post(self):
        pass

if __name__ == '__main__':
    unittest.main()