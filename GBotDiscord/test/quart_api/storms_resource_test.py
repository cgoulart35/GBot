#region IMPORTS
import json
import unittest
from unittest.mock import MagicMock
import nextcord
from nextcord.ext import commands
from werkzeug.exceptions import HTTPException

from GBotDiscord.src.config import config_queries
from GBotDiscord.src.quart_api.storms_resource import StormsStart, StormsState
#endregion

_ORIGINAL_CONFIG_QUERIES = {
    name: getattr(config_queries, name)
    for name in dir(config_queries)
    if callable(getattr(config_queries, name)) and not name.startswith('_')
}


# to run this test suite:
#   - execute the following command from the GBot directory: python -m unittest GBotDiscord/test/quart_api/storms_resource_test.py
#   - or use the "Python: Current File" run configuration to run storms_resource_test.py
#   - or use the "Python: Current File" run configuration to run tests.py to run all test suites
class TestStormsResource(unittest.IsolatedAsyncioTestCase):

    @classmethod
    def setUpClass(self):
        print('\nExecuting storms_resource unit tests...\n')

    @classmethod
    def tearDownClass(self):
        print('\n\nCompleted storms_resource unit tests.\n')

    def setUp(self):
        for name, fn in _ORIGINAL_CONFIG_QUERIES.items():
            setattr(config_queries, name, fn)
        self.client: nextcord.Client = commands.Bot()

        self.stormsCog = MagicMock()
        self.stormsCog.stormStates = {
            '111': {'active': True, 'tier': 1, 'deleteMessages': ['msg-a']},
            '222': {'active': False, 'tier': 2, 'deleteMessages': ['msg-b']},
        }
        self.stormsCog.generateNewStorm = MagicMock()
        self.client.get_cog = MagicMock(return_value=self.stormsCog)

    # region StormsStart.doc / StormsState.doc

    def test_StormsStart_doc_schema(self):
        result = StormsStart.doc()
        self.assertEqual(result['options']['serverId'], ['012345678910111213', 'all'])
        self.assertIn('postBodyTemplate', result)

    def test_StormsState_doc_schema(self):
        result = StormsState.doc()
        self.assertEqual(result['options']['serverId'], ['012345678910111213', 'all'])
        self.assertIn('postBodyTemplate', result)

    # endregion

    # region StormsStart.post

    async def test_StormsStart_post_all_generates_and_strips_deleteMessages(self):
        data = json.dumps({'serverId': 'all'})
        result = await StormsStart.post(self.client, data)

        self.assertEqual(self.stormsCog.generateNewStorm.call_count, 2)
        self.stormsCog.generateNewStorm.assert_any_call('111', True)
        self.stormsCog.generateNewStorm.assert_any_call('222', True)
        self.assertEqual(result, {
            '111': {'active': True, 'tier': 1},
            '222': {'active': False, 'tier': 2},
        })

    async def test_StormsStart_post_single_server(self):
        config_queries.getAllServerValues = MagicMock(return_value={'prefix': '.'})
        data = json.dumps({'serverId': '111'})

        result = await StormsStart.post(self.client, data)

        config_queries.getAllServerValues.assert_called_once_with('111')
        self.stormsCog.generateNewStorm.assert_called_once_with('111', True)
        self.assertEqual(result, {'active': True, 'tier': 1})

    async def test_StormsStart_post_unknown_serverId_returns_invalid_request(self):
        config_queries.getAllServerValues = MagicMock(return_value=None)
        data = json.dumps({'serverId': '999'})

        result = await StormsStart.post(self.client, data)

        self.assertEqual(result, {'status': 'error', 'message': 'Error: Invalid request.'})
        self.stormsCog.generateNewStorm.assert_not_called()

    async def test_StormsStart_post_empty_serverId_returns_invalid_request(self):
        data = json.dumps({'serverId': '   '})
        result = await StormsStart.post(self.client, data)
        self.assertEqual(result, {'status': 'error', 'message': 'Error: Invalid request.'})

    async def test_StormsStart_post_missing_serverId_returns_invalid_request(self):
        data = json.dumps({'noServerId': True})
        result = await StormsStart.post(self.client, data)
        self.assertEqual(result, {'status': 'error', 'message': 'Error: Invalid request.'})

    async def test_StormsStart_post_invalid_json_aborts_400(self):
        with self.assertRaises(HTTPException) as cm:
            await StormsStart.post(self.client, 'not-json')
        self.assertEqual(cm.exception.code, 400)

    # endregion

    # region StormsState.post

    async def test_StormsState_post_all_returns_all_states_without_deleteMessages(self):
        data = json.dumps({'serverId': 'all'})
        result = await StormsState.post(self.client, data)

        # generateNewStorm must NOT be invoked by the state endpoint.
        self.stormsCog.generateNewStorm.assert_not_called()
        self.assertEqual(result, {
            '111': {'active': True, 'tier': 1},
            '222': {'active': False, 'tier': 2},
        })

    async def test_StormsState_post_single_server(self):
        config_queries.getAllServerValues = MagicMock(return_value={'prefix': '.'})
        data = json.dumps({'serverId': '222'})

        result = await StormsState.post(self.client, data)

        config_queries.getAllServerValues.assert_called_once_with('222')
        self.stormsCog.generateNewStorm.assert_not_called()
        self.assertEqual(result, {'active': False, 'tier': 2})

    async def test_StormsState_post_unknown_serverId_returns_invalid_request(self):
        config_queries.getAllServerValues = MagicMock(return_value=None)
        data = json.dumps({'serverId': '999'})

        result = await StormsState.post(self.client, data)

        self.assertEqual(result, {'status': 'error', 'message': 'Error: Invalid request.'})

    async def test_StormsState_post_missing_serverId_returns_invalid_request(self):
        data = json.dumps({'noServerId': True})
        result = await StormsState.post(self.client, data)
        self.assertEqual(result, {'status': 'error', 'message': 'Error: Invalid request.'})

    async def test_StormsState_post_invalid_json_aborts_400(self):
        with self.assertRaises(HTTPException) as cm:
            await StormsState.post(self.client, 'not-json')
        self.assertEqual(cm.exception.code, 400)

    # endregion


if __name__ == '__main__':
    unittest.main()
