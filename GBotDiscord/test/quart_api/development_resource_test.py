#region IMPORTS
import json
import unittest
from unittest.mock import MagicMock, AsyncMock, patch
import nextcord
from nextcord.ext import commands
from werkzeug.exceptions import HTTPException

from GBotDiscord.src.quart_api import development_queries
from GBotDiscord.src.quart_api.development_resource import Development
from GBotDiscord.src.properties import GBotPropertiesManager
#endregion

# Snapshot real module-level functions / class methods so tests that monkey-patch them
# don't bleed across tests (and other suites don't bleed in).
_ORIGINAL_DEV_QUERIES = {
    name: getattr(development_queries, name)
    for name in dir(development_queries)
    if callable(getattr(development_queries, name)) and not name.startswith('_')
}
_ORIGINAL_DEVELOPMENT_METHODS = {
    name: getattr(Development, name)
    for name in ('sendRequestToGitUpdaterHost', 'post', 'doc')
}


# to run this test suite:
#   - execute the following command from the GBot directory: python -m unittest GBotDiscord/test/quart_api/development_resource_test.py
#   - or use the "Python: Current File" run configuration to run development_resource_test.py
#   - or use the "Python: Current File" run configuration to run tests.py to run all test suites
class TestDevelopmentResource(unittest.IsolatedAsyncioTestCase):

    @classmethod
    def setUpClass(self):
        print('\nExecuting development_resource unit tests...\n')

    @classmethod
    def tearDownClass(self):
        print('\n\nCompleted development_resource unit tests.\n')

    def setUp(self):
        for name, fn in _ORIGINAL_DEV_QUERIES.items():
            setattr(development_queries, name, fn)
        for name, fn in _ORIGINAL_DEVELOPMENT_METHODS.items():
            setattr(Development, name, fn)
        self._saved_git_updater_host = GBotPropertiesManager.GIT_UPDATER_HOST
        self._saved_setProperty = GBotPropertiesManager.setProperty
        GBotPropertiesManager.GIT_UPDATER_HOST = 'http://git-updater.test'

        self.client: nextcord.Client = commands.Bot()

    def tearDown(self):
        GBotPropertiesManager.GIT_UPDATER_HOST = self._saved_git_updater_host
        GBotPropertiesManager.setProperty = self._saved_setProperty

    # region doc

    def test_doc_returns_expected_schema(self):
        result = Development.doc()
        self.assertIn('options', result)
        self.assertIn('postBodyTemplate', result)
        actionNames = [a['name'] for a in result['options']['action']]
        self.assertEqual(actionNames, ['rebuildLatest', 'runDatabasePatch', 'setProperty', 'syncSubscribers'])
        self.assertEqual(result['postBodyTemplate']['action']['name'], 'setProperty')

    # endregion

    # region post — rebuildLatest

    async def test_post_rebuildLatest_success(self):
        Development.sendRequestToGitUpdaterHost = AsyncMock(return_value={'status': 'success', 'message': 'Rebuild started.'})
        data = json.dumps({'action': {'name': 'rebuildLatest'}})
        result = await Development.post(self.client, data)
        self.assertEqual(result, {'action': 'rebuildLatest', 'status': 'success', 'message': 'Rebuild started.'})

    async def test_post_rebuildLatest_returns_failure_when_response_none(self):
        Development.sendRequestToGitUpdaterHost = AsyncMock(return_value=None)
        data = json.dumps({'action': {'name': 'rebuildLatest'}})
        result = await Development.post(self.client, data)
        self.assertEqual(result['action'], 'rebuildLatest')
        self.assertEqual(result['status'], 'failure')
        self.assertIn("Can't communicate", result['message'])

    async def test_post_rebuildLatest_returns_failure_when_status_missing(self):
        Development.sendRequestToGitUpdaterHost = AsyncMock(return_value={'message': 'whatever'})
        data = json.dumps({'action': {'name': 'rebuildLatest'}})
        result = await Development.post(self.client, data)
        self.assertEqual(result['status'], 'failure')
        self.assertIn('Missing status', result['message'])

    async def test_post_rebuildLatest_returns_failure_when_message_missing(self):
        Development.sendRequestToGitUpdaterHost = AsyncMock(return_value={'status': 'success'})
        data = json.dumps({'action': {'name': 'rebuildLatest'}})
        result = await Development.post(self.client, data)
        self.assertEqual(result['status'], 'failure')
        self.assertIn('Missing message', result['message'])

    # endregion

    # region post — runDatabasePatch

    async def test_post_runDatabasePatch_known_patch_runs_query(self):
        development_queries.create_leaderboard_table_7_0_0 = AsyncMock()
        data = json.dumps({'action': {'name': 'runDatabasePatch', 'patch': '7.0.0_create_leaderboard_table'}})
        result = await Development.post(self.client, data)
        self.assertEqual(result, {
            'action': 'runDatabasePatch',
            'status': 'success',
            'message': 'Ran patch 7.0.0_create_leaderboard_table.',
        })
        development_queries.create_leaderboard_table_7_0_0.assert_awaited_once_with(self.client)

    async def test_post_runDatabasePatch_unknown_patch_returns_failure(self):
        development_queries.create_leaderboard_table_7_0_0 = AsyncMock()
        data = json.dumps({'action': {'name': 'runDatabasePatch', 'patch': 'bogus_patch'}})
        result = await Development.post(self.client, data)
        self.assertEqual(result, {
            'action': 'runDatabasePatch',
            'status': 'failure',
            'message': 'Invalid patch.',
        })
        development_queries.create_leaderboard_table_7_0_0.assert_not_awaited()

    async def test_post_runDatabasePatch_missing_patch_returns_invalid_request(self):
        data = json.dumps({'action': {'name': 'runDatabasePatch'}})
        result = await Development.post(self.client, data)
        self.assertEqual(result, {'status': 'error', 'message': 'Error: Invalid request.'})

    # endregion

    # region post — setProperty

    async def test_post_setProperty_success(self):
        GBotPropertiesManager.setProperty = MagicMock(return_value=True)
        data = json.dumps({'action': {'name': 'setProperty', 'property': 'LOG_LEVEL', 'value': 'DEBUG'}})
        result = await Development.post(self.client, data)
        GBotPropertiesManager.setProperty.assert_called_once_with('LOG_LEVEL', 'DEBUG')
        self.assertEqual(result, {
            'action': 'setProperty',
            'status': 'success',
            'message': "Property 'LOG_LEVEL' set to: DEBUG",
        })

    async def test_post_setProperty_unknown_returns_failure(self):
        GBotPropertiesManager.setProperty = MagicMock(return_value=False)
        data = json.dumps({'action': {'name': 'setProperty', 'property': 'NOT_A_PROP', 'value': 'x'}})
        result = await Development.post(self.client, data)
        self.assertEqual(result, {
            'action': 'setProperty',
            'status': 'failure',
            'message': 'Invalid property.',
        })

    async def test_post_setProperty_missing_value_returns_invalid_request(self):
        data = json.dumps({'action': {'name': 'setProperty', 'property': 'LOG_LEVEL'}})
        result = await Development.post(self.client, data)
        self.assertEqual(result, {'status': 'error', 'message': 'Error: Invalid request.'})

    # endregion

    # region post — syncSubscribers

    async def test_post_syncSubscribers_success(self):
        patreonCog = MagicMock()
        patreonCog.patreon_validation = AsyncMock()
        self.client.get_cog = MagicMock(return_value=patreonCog)
        data = json.dumps({'action': {'name': 'syncSubscribers'}})
        result = await Development.post(self.client, data)
        patreonCog.patreon_validation.assert_awaited_once()
        self.assertEqual(result, {
            'action': 'syncSubscribers',
            'status': 'success',
            'message': 'GBot is synced with current subscribers.',
        })

    async def test_post_syncSubscribers_failure_when_validation_raises(self):
        patreonCog = MagicMock()
        patreonCog.patreon_validation = AsyncMock(side_effect=Exception('boom'))
        self.client.get_cog = MagicMock(return_value=patreonCog)
        data = json.dumps({'action': {'name': 'syncSubscribers'}})
        result = await Development.post(self.client, data)
        self.assertEqual(result, {
            'action': 'syncSubscribers',
            'status': 'failure',
            'message': 'GBot failed to sync with current subscribers.',
        })

    # endregion

    # region post — error & unhandled branches

    async def test_post_unknown_action_returns_invalid_request(self):
        data = json.dumps({'action': {'name': 'nope'}})
        result = await Development.post(self.client, data)
        self.assertEqual(result, {'status': 'error', 'message': 'Error: Invalid request.'})

    async def test_post_missing_action_returns_invalid_request(self):
        data = json.dumps({'noAction': True})
        result = await Development.post(self.client, data)
        self.assertEqual(result, {'status': 'error', 'message': 'Error: Invalid request.'})

    async def test_post_invalid_json_aborts_400(self):
        with self.assertRaises(HTTPException) as cm:
            await Development.post(self.client, 'not-json')
        self.assertEqual(cm.exception.code, 400)

    # endregion

    # region sendRequestToGitUpdaterHost

    async def test_sendRequestToGitUpdaterHost_success(self):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {'status': 'success', 'message': 'ok'}
        httpxClient = MagicMock()
        httpxClient.post = AsyncMock(return_value=response)
        with patch('GBotDiscord.src.quart_api.development_resource.httpx.AsyncClient') as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = httpxClient
            mock_client_class.return_value.__aexit__.return_value = False
            result = await Development.sendRequestToGitUpdaterHost()
        self.assertEqual(result, {'status': 'success', 'message': 'ok'})
        httpxClient.post.assert_awaited_once_with(
            'http://git-updater.test',
            data=json.dumps({'application': 'GBot'}),
            timeout=60,
        )

    async def test_sendRequestToGitUpdaterHost_non_200_returns_none(self):
        response = MagicMock()
        response.status_code = 500
        httpxClient = MagicMock()
        httpxClient.post = AsyncMock(return_value=response)
        with patch('GBotDiscord.src.quart_api.development_resource.httpx.AsyncClient') as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = httpxClient
            mock_client_class.return_value.__aexit__.return_value = False
            result = await Development.sendRequestToGitUpdaterHost()
        self.assertIsNone(result)

    async def test_sendRequestToGitUpdaterHost_exception_returns_none(self):
        httpxClient = MagicMock()
        httpxClient.post = AsyncMock(side_effect=Exception('connection refused'))
        with patch('GBotDiscord.src.quart_api.development_resource.httpx.AsyncClient') as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = httpxClient
            mock_client_class.return_value.__aexit__.return_value = False
            result = await Development.sendRequestToGitUpdaterHost()
        self.assertIsNone(result)

    # endregion


if __name__ == '__main__':
    unittest.main()
