#region IMPORTS
import base64
import json
import unittest
from unittest.mock import MagicMock, AsyncMock, patch

import nextcord
from nextcord.ext import commands

from GBotDiscord.src.quart_api import api as api_module
from GBotDiscord.src.quart_api.api import GBotAPIService
from GBotDiscord.src.firebase import GBotFirebaseService
#endregion


def _basic_auth_header(user='admin', password='pw'):
    token = base64.b64encode(f'{user}:{password}'.encode()).decode()
    return {'Authorization': f'Basic {token}'}


_ORIGINAL_AUTHENTICATE = GBotFirebaseService.authenticate


# to run this test suite:
#   - execute the following command from the GBot directory: python -m unittest GBotDiscord/test/quart_api/api_test.py
#   - or use the "Python: Current File" run configuration to run api_test.py
#   - or use the "Python: Current File" run configuration to run tests.py to run all test suites
class TestAPI(unittest.IsolatedAsyncioTestCase):

    @classmethod
    def setUpClass(self):
        print('\nExecuting api unit tests...\n')

    @classmethod
    def tearDownClass(self):
        print('\n\nCompleted api unit tests.\n')

    def setUp(self):
        GBotFirebaseService.authenticate = _ORIGINAL_AUTHENTICATE
        self._saved_resources = {
            name: getattr(api_module, name)
            for name in ('Development', 'Discord', 'StormsStart', 'StormsState', 'Leaderboard')
        }

        self.devMock = MagicMock()
        self.devMock.doc = MagicMock(return_value={'dev': 'doc'})
        self.devMock.post = AsyncMock(return_value={'dev': 'post'})
        api_module.Development = self.devMock

        self.discordMock = MagicMock()
        self.discordMock.doc = MagicMock(return_value={'discord': 'doc'})
        self.discordMock.post = AsyncMock(return_value={'discord': 'post'})
        api_module.Discord = self.discordMock

        self.stormsStartMock = MagicMock()
        self.stormsStartMock.doc = MagicMock(return_value={'storms_start': 'doc'})
        self.stormsStartMock.post = AsyncMock(return_value={'storms_start': 'post'})
        api_module.StormsStart = self.stormsStartMock

        self.stormsStateMock = MagicMock()
        self.stormsStateMock.doc = MagicMock(return_value={'storms_state': 'doc'})
        self.stormsStateMock.post = AsyncMock(return_value={'storms_state': 'post'})
        api_module.StormsState = self.stormsStateMock

        self.leaderboardMock = MagicMock()
        self.leaderboardMock.get = MagicMock(return_value={'leaderboard': 'data'})
        api_module.Leaderboard = self.leaderboardMock

        # Default: authenticate succeeds. Individual tests override to False.
        GBotFirebaseService.authenticate = MagicMock(return_value=True)

        # Capture the Quart instance created by registerAPI, and replace its
        # run_task with a sync no-op so the cert-bound HTTPS server is never bound
        # and no orphaned coroutine warnings appear.
        self._captured_app = []
        real_Quart = api_module.Quart

        def quart_factory(*args, **kwargs):
            inst = real_Quart(*args, **kwargs)
            inst.run_task = MagicMock(return_value=None)
            self._captured_app.append(inst)
            return inst

        # Spy on cors() but pass through to the real implementation so the
        # public leaderboard endpoint remains CORS-enabled.
        self._cors_calls = []
        real_cors = api_module.cors

        def cors_spy(app, **kwargs):
            self._cors_calls.append(kwargs)
            return real_cors(app, **kwargs)

        self._patch_quart = patch.object(api_module, 'Quart', side_effect=quart_factory)
        self._patch_quart.start()
        self._patch_cors = patch.object(api_module, 'cors', side_effect=cors_spy)
        self._patch_cors.start()

        self.client: nextcord.Client = commands.Bot()
        # `gbotClient.loop.create_task(...)` is fire-and-forget; stub the loop so
        # we don't actually schedule the server on a real event loop.
        self.client.loop = MagicMock()

        GBotAPIService.registerAPI(self.client)
        self.app = self._captured_app[0]
        self.testClient = self.app.test_client()

    def tearDown(self):
        self._patch_quart.stop()
        self._patch_cors.stop()
        for name, original in self._saved_resources.items():
            setattr(api_module, name, original)
        GBotFirebaseService.authenticate = _ORIGINAL_AUTHENTICATE

    # region authorize — sync wrapper (GET routes)

    async def test_authorize_sync_missing_auth_returns_401(self):
        response = await self.testClient.get('/GBot/private/development/doc/')
        self.assertEqual(response.status_code, 401)
        self.devMock.doc.assert_not_called()

    async def test_authorize_sync_non_basic_returns_401(self):
        response = await self.testClient.get(
            '/GBot/private/development/doc/',
            headers={'Authorization': 'Bearer abc'},
        )
        self.assertEqual(response.status_code, 401)
        self.devMock.doc.assert_not_called()

    async def test_authorize_sync_invalid_credentials_returns_401(self):
        GBotFirebaseService.authenticate = MagicMock(return_value=False)
        response = await self.testClient.get(
            '/GBot/private/development/doc/',
            headers=_basic_auth_header('bad', 'creds'),
        )
        self.assertEqual(response.status_code, 401)
        GBotFirebaseService.authenticate.assert_called_once_with('bad', 'creds')
        self.devMock.doc.assert_not_called()

    async def test_authorize_sync_valid_credentials_forwards(self):
        response = await self.testClient.get(
            '/GBot/private/development/doc/',
            headers=_basic_auth_header(),
        )
        self.assertEqual(response.status_code, 200)
        self.devMock.doc.assert_called_once_with()

    # endregion

    # region authorize — async wrapper (POST routes)

    async def test_authorize_async_missing_auth_returns_401(self):
        response = await self.testClient.post(
            '/GBot/private/development/',
            data=json.dumps({}),
        )
        self.assertEqual(response.status_code, 401)
        self.devMock.post.assert_not_called()

    async def test_authorize_async_non_basic_returns_401(self):
        response = await self.testClient.post(
            '/GBot/private/development/',
            data=json.dumps({}),
            headers={'Authorization': 'Bearer abc'},
        )
        self.assertEqual(response.status_code, 401)
        self.devMock.post.assert_not_called()

    async def test_authorize_async_invalid_credentials_returns_401(self):
        GBotFirebaseService.authenticate = MagicMock(return_value=False)
        response = await self.testClient.post(
            '/GBot/private/development/',
            data=json.dumps({}),
            headers=_basic_auth_header(),
        )
        self.assertEqual(response.status_code, 401)
        self.devMock.post.assert_not_called()

    async def test_authorize_async_valid_credentials_forwards(self):
        body = json.dumps({'foo': 'bar'})
        response = await self.testClient.post(
            '/GBot/private/development/',
            data=body,
            headers=_basic_auth_header(),
        )
        self.assertEqual(response.status_code, 200)
        self.devMock.post.assert_awaited_once()
        call_args = self.devMock.post.await_args
        self.assertIs(call_args.args[0], self.client)
        self.assertEqual(call_args.args[1].decode('utf-8'), body)

    # endregion

    # region route dispatch — covers every registered route's handler body

    async def test_development_doc_route_dispatches_to_resource(self):
        response = await self.testClient.get(
            '/GBot/private/development/doc/', headers=_basic_auth_header()
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(await response.get_json(), {'dev': 'doc'})

    async def test_development_post_route_dispatches_to_resource(self):
        body = json.dumps({'action': {'name': 'setProperty', 'property': 'LOG_LEVEL', 'value': 'DEBUG'}})
        response = await self.testClient.post(
            '/GBot/private/development/', data=body, headers=_basic_auth_header()
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(await response.get_json(), {'dev': 'post'})

    async def test_discord_doc_route_dispatches_to_resource(self):
        response = await self.testClient.get(
            '/GBot/private/discord/doc/', headers=_basic_auth_header()
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(await response.get_json(), {'discord': 'doc'})
        self.discordMock.doc.assert_called_once_with()

    async def test_discord_post_route_dispatches_to_resource(self):
        body = json.dumps({'action': {'name': 'sendMessage'}})
        response = await self.testClient.post(
            '/GBot/private/discord/', data=body, headers=_basic_auth_header()
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(await response.get_json(), {'discord': 'post'})
        self.discordMock.post.assert_awaited_once()
        call_args = self.discordMock.post.await_args
        self.assertIs(call_args.args[0], self.client)
        self.assertEqual(call_args.args[1].decode('utf-8'), body)

    async def test_storms_start_doc_route_dispatches_to_resource(self):
        response = await self.testClient.get(
            '/GBot/private/storms/start/doc/', headers=_basic_auth_header()
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(await response.get_json(), {'storms_start': 'doc'})
        self.stormsStartMock.doc.assert_called_once_with()

    async def test_storms_start_post_route_dispatches_to_resource(self):
        body = json.dumps({'serverId': 'all'})
        response = await self.testClient.post(
            '/GBot/private/storms/start/', data=body, headers=_basic_auth_header()
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(await response.get_json(), {'storms_start': 'post'})
        self.stormsStartMock.post.assert_awaited_once()
        call_args = self.stormsStartMock.post.await_args
        self.assertIs(call_args.args[0], self.client)
        self.assertEqual(call_args.args[1].decode('utf-8'), body)

    async def test_storms_state_doc_route_dispatches_to_resource(self):
        response = await self.testClient.get(
            '/GBot/private/storms/state/doc/', headers=_basic_auth_header()
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(await response.get_json(), {'storms_state': 'doc'})
        self.stormsStateMock.doc.assert_called_once_with()

    async def test_storms_state_post_route_dispatches_to_resource(self):
        body = json.dumps({'serverId': 'all'})
        response = await self.testClient.post(
            '/GBot/private/storms/state/', data=body, headers=_basic_auth_header()
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(await response.get_json(), {'storms_state': 'post'})
        self.stormsStateMock.post.assert_awaited_once()
        call_args = self.stormsStateMock.post.await_args
        self.assertIs(call_args.args[0], self.client)
        self.assertEqual(call_args.args[1].decode('utf-8'), body)

    async def test_public_leaderboard_route_does_not_require_auth(self):
        response = await self.testClient.get('/GBot/public/leaderboard/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(await response.get_json(), {'leaderboard': 'data'})
        self.leaderboardMock.get.assert_called_once_with()

    # endregion

    # region logPayloadAndResponse

    def test_logPayloadAndResponse_without_data_omits_requestPayload(self):
        with patch.object(GBotAPIService.logger, 'info') as mock_info:
            GBotAPIService.logPayloadAndResponse({'a': 1})
        mock_info.assert_called_once()
        logged = json.loads(mock_info.call_args.args[0])
        self.assertEqual(logged, {'response': {'a': 1}})
        self.assertNotIn('requestPayload', logged)

    def test_logPayloadAndResponse_with_data_includes_requestPayload(self):
        payload = json.dumps({'k': 'v'}).encode('utf-8')
        with patch.object(GBotAPIService.logger, 'info') as mock_info:
            GBotAPIService.logPayloadAndResponse({'a': 1}, payload)
        mock_info.assert_called_once()
        logged = json.loads(mock_info.call_args.args[0])
        self.assertEqual(logged, {'response': {'a': 1}, 'requestPayload': {'k': 'v'}})

    # endregion

    # region registerAPI wiring sanity

    def test_registerAPI_sets_client_on_service(self):
        self.assertIs(GBotAPIService.client, self.client)

    def test_registerAPI_calls_cors_with_wildcard(self):
        self.assertEqual(self._cors_calls, [{'allow_origin': '*'}])

    def test_registerAPI_schedules_run_task_on_bot_loop(self):
        self.client.loop.create_task.assert_called_once()

    # endregion


if __name__ == '__main__':
    unittest.main()
