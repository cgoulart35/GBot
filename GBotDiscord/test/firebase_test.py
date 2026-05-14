#region IMPORTS
import unittest
from unittest.mock import MagicMock, patch

from GBotDiscord.src.firebase import GBotFirebaseService
from GBotDiscord.src.properties import GBotPropertiesManager
#endregion

# Snapshot the real GBotFirebaseService static methods at import time. Other suites
# replace these with MagicMocks (e.g. gcoin_test sets `GBotFirebaseService.set = MagicMock()`)
# and never restore — without this snapshot, firebase_test runs against the mocks
# instead of the real implementations.
_ORIGINAL_FIREBASE_FUNCS = {
    name: getattr(GBotFirebaseService, name)
    for name in ('get', 'set', 'push', 'update', 'remove',
                 'loopChildren', 'authenticate', 'startFirebaseScheduler')
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
        self._saved_db = GBotFirebaseService.db
        self._saved_auth = GBotFirebaseService.auth
        self._saved_firebase_config = GBotPropertiesManager.FIREBASE_CONFIG_JSON

    def tearDown(self):
        GBotFirebaseService.db = self._saved_db
        GBotFirebaseService.auth = self._saved_auth
        GBotPropertiesManager.FIREBASE_CONFIG_JSON = self._saved_firebase_config

    # region loopChildren

    def test_loopChildren_chains_child_calls_in_order(self):
        leaf = MagicMock(name='leaf')
        mid = MagicMock(name='mid')
        first = MagicMock(name='first')
        root = MagicMock(name='root')
        root.child.return_value = first
        first.child.return_value = mid
        mid.child.return_value = leaf

        GBotFirebaseService.db = root
        result = GBotFirebaseService.loopChildren(['a', 'b', 'c'])

        root.child.assert_called_once_with('a')
        first.child.assert_called_once_with('b')
        mid.child.assert_called_once_with('c')
        self.assertIs(result, leaf)

    def test_loopChildren_empty_returns_db_root(self):
        root = MagicMock(name='root')
        GBotFirebaseService.db = root
        self.assertIs(GBotFirebaseService.loopChildren([]), root)
        root.child.assert_not_called()

    # endregion

    # region get / set / push / update / remove

    def _stub_single_level_db(self):
        leaf = MagicMock(name='leaf')
        root = MagicMock(name='root')
        root.child.return_value = leaf
        GBotFirebaseService.db = root
        return root, leaf

    def test_get_forwards_to_loopChildren_result(self):
        root, leaf = self._stub_single_level_db()
        leaf.get.return_value = 'sentinel'

        result = GBotFirebaseService.get(['x'])

        root.child.assert_called_once_with('x')
        leaf.get.assert_called_once_with()
        self.assertEqual(result, 'sentinel')

    def test_remove_forwards_to_loopChildren_result(self):
        root, leaf = self._stub_single_level_db()

        GBotFirebaseService.remove(['x'])

        root.child.assert_called_once_with('x')
        leaf.remove.assert_called_once_with()

    def test_set_forwards_payload(self):
        root, leaf = self._stub_single_level_db()

        GBotFirebaseService.set(['x'], {'foo': 1})

        leaf.set.assert_called_once_with({'foo': 1})

    def test_push_forwards_payload(self):
        root, leaf = self._stub_single_level_db()

        GBotFirebaseService.push(['x'], {'foo': 1})

        leaf.push.assert_called_once_with({'foo': 1})

    def test_update_forwards_payload(self):
        root, leaf = self._stub_single_level_db()

        GBotFirebaseService.update(['x'], {'foo': 1})

        leaf.update.assert_called_once_with({'foo': 1})

    # endregion

    # region authenticate

    def test_authenticate_success_returns_true(self):
        auth = MagicMock()
        GBotFirebaseService.auth = auth

        self.assertTrue(GBotFirebaseService.authenticate('user@example.com', 'secret'))
        auth.sign_in_with_email_and_password.assert_called_once_with('user@example.com', 'secret')

    def test_authenticate_exception_returns_false(self):
        auth = MagicMock()
        auth.sign_in_with_email_and_password.side_effect = Exception('bad creds')
        GBotFirebaseService.auth = auth

        self.assertFalse(GBotFirebaseService.authenticate('user@example.com', 'wrong'))

    # endregion

    # region startFirebaseScheduler

    def test_startFirebaseScheduler_initializes_db_and_auth(self):
        GBotPropertiesManager.FIREBASE_CONFIG_JSON = '{"apiKey":"abc","databaseURL":"https://x"}'
        fake_db = MagicMock(name='fake_db')
        fake_auth = MagicMock(name='fake_auth')
        firebase_app = MagicMock(name='firebase_app')
        firebase_app.database.return_value = fake_db
        firebase_app.auth.return_value = fake_auth

        with patch('GBotDiscord.src.firebase.pyrebase.initialize_app', return_value=firebase_app) as mock_init:
            GBotFirebaseService.startFirebaseScheduler()

        mock_init.assert_called_once_with({'apiKey': 'abc', 'databaseURL': 'https://x'})
        self.assertIs(GBotFirebaseService.db, fake_db)
        self.assertIs(GBotFirebaseService.auth, fake_auth)

    # endregion


if __name__ == '__main__':
    unittest.main()
