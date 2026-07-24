#region IMPORTS
import unittest
from unittest.mock import MagicMock, patch

from GBotDiscord.src.firebase import GBotFirebaseResult, GBotFirebaseService
from GBotDiscord.src.properties import GBotPropertiesManager
#endregion

# Snapshot the real GBotFirebaseService static methods at import time. Other suites
# replace these with MagicMocks (e.g. gcoin_test sets `GBotFirebaseService.set = MagicMock()`)
# and never restore — without this snapshot, firebase_test runs against the mocks
# instead of the real implementations.
_ORIGINAL_FIREBASE_FUNCS = {
    name: getattr(GBotFirebaseService, name)
    for name in ('get', 'set', 'push', 'update', 'remove',
                 'getReference', 'authenticate', 'startFirebaseScheduler')
}


class TestFirebase(unittest.TestCase):

    @classmethod
    def setUpClass(self):
        print('\nExecuting firebase unit tests...\n')

    @classmethod
    def tearDownClass(self):
        print('\n\nCompleted firebase unit tests.\n')

    def setUp(self):
        for name, fn in _ORIGINAL_FIREBASE_FUNCS.items():
            setattr(GBotFirebaseService, name, fn)
        self._saved_api_key = GBotFirebaseService.apiKey
        self._saved_firebase_config = GBotPropertiesManager.FIREBASE_CONFIG_JSON

    def tearDown(self):
        GBotFirebaseService.apiKey = self._saved_api_key
        GBotPropertiesManager.FIREBASE_CONFIG_JSON = self._saved_firebase_config

    # region getReference

    def test_getReference_joins_children_into_path(self):
        with patch('GBotDiscord.src.firebase.db.reference', return_value = 'ref') as mock_reference:
            result = GBotFirebaseService.getReference(['servers', 123, 'prefix'])

        mock_reference.assert_called_once_with('/servers/123/prefix')
        self.assertEqual(result, 'ref')

    def test_getReference_empty_children_is_root_path(self):
        with patch('GBotDiscord.src.firebase.db.reference', return_value = 'root') as mock_reference:
            result = GBotFirebaseService.getReference([])

        mock_reference.assert_called_once_with('/')
        self.assertEqual(result, 'root')

    # endregion

    # region get / set / push / update / remove

    def _stub_reference(self):
        ref = MagicMock(name = 'ref')
        return ref, patch('GBotDiscord.src.firebase.db.reference', return_value = ref)

    def test_get_wraps_reference_value_in_result(self):
        ref, patcher = self._stub_reference()
        ref.get.return_value = 'sentinel'

        with patcher as mock_reference:
            result = GBotFirebaseService.get(['x'])

        mock_reference.assert_called_once_with('/x')
        ref.get.assert_called_once_with()
        self.assertIsInstance(result, GBotFirebaseResult)
        self.assertEqual(result.val(), 'sentinel')

    def test_remove_deletes_reference(self):
        ref, patcher = self._stub_reference()

        with patcher as mock_reference:
            GBotFirebaseService.remove(['x'])

        mock_reference.assert_called_once_with('/x')
        ref.delete.assert_called_once_with()

    def test_set_forwards_payload(self):
        ref, patcher = self._stub_reference()

        with patcher:
            GBotFirebaseService.set(['x'], {'foo': 1})

        ref.set.assert_called_once_with({'foo': 1})

    def test_push_forwards_payload(self):
        ref, patcher = self._stub_reference()

        with patcher:
            GBotFirebaseService.push(['x'], {'foo': 1})

        ref.push.assert_called_once_with({'foo': 1})

    def test_update_forwards_payload(self):
        ref, patcher = self._stub_reference()

        with patcher:
            GBotFirebaseService.update(['x'], {'foo': 1})

        ref.update.assert_called_once_with({'foo': 1})

    def test_result_val_returns_wrapped_value(self):
        self.assertEqual(GBotFirebaseResult('v').val(), 'v')
        self.assertIsNone(GBotFirebaseResult(None).val())

    # endregion

    # region authenticate

    def test_authenticate_success_returns_true(self):
        GBotFirebaseService.apiKey = 'abc'
        response = MagicMock(status_code = 200)

        with patch('GBotDiscord.src.firebase.httpx.post', return_value = response) as mock_post:
            self.assertTrue(GBotFirebaseService.authenticate('user@example.com', 'secret'))

        mock_post.assert_called_once_with(
            'https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=abc',
            json = {'email': 'user@example.com', 'password': 'secret', 'returnSecureToken': True})

    def test_authenticate_rejected_returns_false(self):
        GBotFirebaseService.apiKey = 'abc'
        response = MagicMock(status_code = 400)

        with patch('GBotDiscord.src.firebase.httpx.post', return_value = response):
            self.assertFalse(GBotFirebaseService.authenticate('user@example.com', 'wrong'))

    def test_authenticate_exception_returns_false(self):
        GBotFirebaseService.apiKey = 'abc'

        with patch('GBotDiscord.src.firebase.httpx.post', side_effect = Exception('network down')):
            self.assertFalse(GBotFirebaseService.authenticate('user@example.com', 'secret'))

    # endregion

    # region startFirebaseScheduler

    def test_startFirebaseScheduler_initializes_admin_app(self):
        GBotPropertiesManager.FIREBASE_CONFIG_JSON = '{"apiKey":"abc","databaseURL":"https://x","serviceAccount":"/GBot/Shared/serviceAccountKey.json"}'
        fake_credential = MagicMock(name = 'credential')

        with patch('GBotDiscord.src.firebase.credentials.Certificate', return_value = fake_credential) as mock_certificate, \
             patch('GBotDiscord.src.firebase.firebase_admin.initialize_app') as mock_initialize_app:
            GBotFirebaseService.startFirebaseScheduler()

        mock_certificate.assert_called_once_with('/GBot/Shared/serviceAccountKey.json')
        mock_initialize_app.assert_called_once_with(fake_credential, {'databaseURL': 'https://x'})
        self.assertEqual(GBotFirebaseService.apiKey, 'abc')

    # endregion


if __name__ == '__main__':
    unittest.main()
