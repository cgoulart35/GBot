#region IMPORTS
import threading
import time
import unittest
from unittest.mock import MagicMock
from decimal import Decimal

from GBotDiscord.src.firebase import GBotFirebaseService
from GBotDiscord.src.gcoin import gcoin_queries
from GBotDiscord.src.leaderboards import leaderboards_queries
from GBotDiscord.src.exceptions import (
    EnforceRealUsersError,
    EnforceSenderReceiverNotEqual,
    EnforcePositiveTransactions,
    EnforceSenderFundsError,
)
#endregion

# to run this test suite:
#   - execute the following command from the GBot directory: python -m unittest GBotDiscord/test/gcoin/gcoin_queries_test.py
#   - or use the "Python: Current File" run configuration to run gcoin_queries_test.py
#   - or use the "Python: Current File" run configuration to run tests.py to run all test suites

# Snapshot the real module-level functions at import time. The gcoin cog test suite
# replaces several of these with MagicMocks and never restores them — the snapshot
# makes this suite order-independent.
_ORIGINAL_GCOIN_FUNCS = {
    name: getattr(gcoin_queries, name)
    for name in dir(gcoin_queries)
    if callable(getattr(gcoin_queries, name)) and not name.startswith('_')
}

_ORIGINAL_LEADERBOARDS_FUNCS = {
    name: getattr(leaderboards_queries, name)
    for name in dir(leaderboards_queries)
    if callable(getattr(leaderboards_queries, name)) and not name.startswith('_')
}


def _mockResult(value):
    result = MagicMock()
    result.val.return_value = value
    return result


class TestGCoinQueries(unittest.TestCase):

    @classmethod
    def setUpClass(self):
        print('\nExecuting gcoin queries unit tests...\n')

    @classmethod
    def tearDownClass(self):
        print('\n\nCompleted gcoin queries unit tests.\n')

    def setUp(self):
        for name, fn in _ORIGINAL_GCOIN_FUNCS.items():
            setattr(gcoin_queries, name, fn)
        for name, fn in _ORIGINAL_LEADERBOARDS_FUNCS.items():
            setattr(leaderboards_queries, name, fn)
        self._saved = {
            name: getattr(GBotFirebaseService, name)
            for name in ('get', 'set', 'push', 'update', 'remove', 'updateMany', 'newKey')
        }
        GBotFirebaseService.get = MagicMock()
        GBotFirebaseService.set = MagicMock()
        GBotFirebaseService.push = MagicMock()
        GBotFirebaseService.update = MagicMock()
        GBotFirebaseService.remove = MagicMock()
        GBotFirebaseService.updateMany = MagicMock()
        GBotFirebaseService.newKey = MagicMock(side_effect = ['key1', 'key2'])
        # Isolate gcoin_queries from leaderboards_queries' own reads.
        leaderboards_queries.processTransactionForLeaderboardRewards = MagicMock(return_value = {})

        self.date = '01/01/26 12:00:00 PM'

    def tearDown(self):
        for name, fn in self._saved.items():
            setattr(GBotFirebaseService, name, fn)
        for name, fn in _ORIGINAL_LEADERBOARDS_FUNCS.items():
            setattr(leaderboards_queries, name, fn)

    # region performTransaction — error paths
    def test_performTransaction_real_users_sender_id_none_raises(self):
        sender = {'id': None, 'name': 'virtual'}
        receiver = {'id': '2000', 'name': 'real'}
        with self.assertRaises(EnforceRealUsersError):
            gcoin_queries.performTransaction(
                Decimal('5'), self.date, sender, receiver, 'memoS', 'memoR',
                enforceRealUsers=True
            )

    def test_performTransaction_real_users_receiver_id_none_raises(self):
        sender = {'id': '1000', 'name': 'real'}
        receiver = {'id': None, 'name': 'virtual'}
        with self.assertRaises(EnforceRealUsersError):
            gcoin_queries.performTransaction(
                Decimal('5'), self.date, sender, receiver, 'memoS', 'memoR',
                enforceRealUsers=True
            )

    def test_performTransaction_sender_equals_receiver_raises(self):
        sender = {'id': '1000', 'name': 'same'}
        receiver = {'id': '1000', 'name': 'same'}
        with self.assertRaises(EnforceSenderReceiverNotEqual):
            gcoin_queries.performTransaction(
                Decimal('5'), self.date, sender, receiver, 'memoS', 'memoR',
                enforceRealUsers=True
            )

    def test_performTransaction_zero_amount_raises(self):
        sender = {'id': '1000', 'name': 'a'}
        receiver = {'id': '2000', 'name': 'b'}
        with self.assertRaises(EnforcePositiveTransactions):
            gcoin_queries.performTransaction(
                Decimal('0'), self.date, sender, receiver, 'memoS', 'memoR'
            )

    def test_performTransaction_negative_amount_raises(self):
        sender = {'id': '1000', 'name': 'a'}
        receiver = {'id': '2000', 'name': 'b'}
        with self.assertRaises(EnforcePositiveTransactions):
            gcoin_queries.performTransaction(
                Decimal('-1'), self.date, sender, receiver, 'memoS', 'memoR'
            )

    def test_performTransaction_insufficient_funds_raises(self):
        # Sender has 4.00 balance, tries to send 5
        GBotFirebaseService.get.return_value = _mockResult('4.00')
        sender = {'id': '1000', 'name': 'a'}
        receiver = {'id': '2000', 'name': 'b'}
        with self.assertRaises(EnforceSenderFundsError):
            gcoin_queries.performTransaction(
                Decimal('5'), self.date, sender, receiver, 'memoS', 'memoR',
                enforceSenderFunds=True
            )
    # endregion

    # region performTransaction — valid permutations
    def _writtenChanges(self):
        # everything has to arrive in one call, or a failure partway could lose money
        GBotFirebaseService.updateMany.assert_called_once()
        GBotFirebaseService.set.assert_not_called()
        GBotFirebaseService.push.assert_not_called()
        GBotFirebaseService.remove.assert_not_called()
        return GBotFirebaseService.updateMany.call_args.args[0]

    def test_performTransaction_real_to_real(self):
        GBotFirebaseService.get.return_value = _mockResult('100.00')
        sender = {'id': '1000', 'name': 'alice'}
        receiver = {'id': '2000', 'name': 'bob'}
        gcoin_queries.performTransaction(
            Decimal('25'), self.date, sender, receiver, 'sentMemo', 'recvMemo'
        )
        # the stored shape is the one everything already reads. Decimal subtraction preserves
        # operand precision (100.00 - 25 → 75.00)
        self.assertEqual(self._writtenChanges(), {
            'gcoin/1000/balance': '75.00',
            'gcoin/1000/username': 'alice',
            'gcoin/1000/history/key1': {'gcoin': '-25', 'other': 'bob', 'date': self.date, 'memo': 'sentMemo'},
            'leaderboards/1000/balance': '75.00',
            'leaderboards/1000/username': 'alice',
            'gcoin/2000/balance': '125.00',
            'gcoin/2000/username': 'bob',
            'gcoin/2000/history/key2': {'gcoin': '+25', 'other': 'alice', 'date': self.date, 'memo': 'recvMemo'},
            'leaderboards/2000/balance': '125.00',
            'leaderboards/2000/username': 'bob',
        })
        self.assertEqual(leaderboards_queries.processTransactionForLeaderboardRewards.call_count, 2)

    def test_performTransaction_real_to_virtual(self):
        GBotFirebaseService.get.return_value = _mockResult('50.00')
        sender = {'id': '1000', 'name': 'alice'}
        receiver = {'id': None, 'name': 'BankOfGCoin'}
        gcoin_queries.performTransaction(
            Decimal('10'), self.date, sender, receiver, 'sentMemo', 'recvMemo'
        )
        # Only sender side touched
        changes = self._writtenChanges()
        self.assertEqual(changes['gcoin/1000/balance'], '40.00')
        self.assertEqual(changes['gcoin/1000/history/key1'], {'gcoin': '-10', 'other': 'BankOfGCoin', 'date': self.date, 'memo': 'sentMemo'})
        self.assertEqual(len(changes), 5)
        leaderboards_queries.processTransactionForLeaderboardRewards.assert_called_once_with('1000', changes['gcoin/1000/history/key1'], None)

    def test_performTransaction_virtual_to_real(self):
        GBotFirebaseService.get.return_value = _mockResult('20.00')
        sender = {'id': None, 'name': 'BankOfGCoin'}
        receiver = {'id': '2000', 'name': 'bob'}
        gcoin_queries.performTransaction(
            Decimal('5'), self.date, sender, receiver, 'sentMemo', 'recvMemo'
        )
        # Only receiver side touched
        changes = self._writtenChanges()
        self.assertEqual(changes['gcoin/2000/balance'], '25.00')
        self.assertEqual(changes['gcoin/2000/history/key1'], {'gcoin': '+5', 'other': 'BankOfGCoin', 'date': self.date, 'memo': 'recvMemo'})
        self.assertEqual(len(changes), 5)

    def test_performTransaction_virtual_to_virtual_noop(self):
        sender = {'id': None, 'name': 'BankA'}
        receiver = {'id': None, 'name': 'BankB'}
        gcoin_queries.performTransaction(
            Decimal('3'), self.date, sender, receiver, 'sentMemo', 'recvMemo'
        )
        # an empty update is refused by firebase-admin, so nothing to write means no call
        GBotFirebaseService.updateMany.assert_not_called()
        leaderboards_queries.processTransactionForLeaderboardRewards.assert_not_called()

    def test_performTransaction_sufficient_funds_passes(self):
        # Sender has 100, sends 50 — passes validateFunds when enforceSenderFunds=True
        GBotFirebaseService.get.return_value = _mockResult('100.00')
        sender = {'id': '1000', 'name': 'alice'}
        receiver = {'id': '2000', 'name': 'bob'}
        gcoin_queries.performTransaction(
            Decimal('50'), self.date, sender, receiver, 'sentMemo', 'recvMemo',
            enforceSenderFunds=True
        )
        changes = self._writtenChanges()
        self.assertEqual(changes['gcoin/1000/balance'], '50.00')
        self.assertEqual(changes['gcoin/2000/balance'], '150.00')

    def test_performTransaction_includes_rewards_and_extra_changes(self):
        # a reward statistic and a trade's item have to succeed or fail with the money
        GBotFirebaseService.get.return_value = _mockResult('20.00')
        leaderboards_queries.processTransactionForLeaderboardRewards = MagicMock(return_value = {'leaderboards/2000/numNetStormRewards': '5.00'})
        extra = {'gtrade/personal/2000/item': None}
        gcoin_queries.performTransaction(
            Decimal('5'), self.date, {'id': None, 'name': 'Storms'}, {'id': '2000', 'name': 'bob'}, '', 'won', extraChanges = extra
        )
        changes = self._writtenChanges()
        self.assertEqual(changes['leaderboards/2000/numNetStormRewards'], '5.00')
        self.assertIsNone(changes['gtrade/personal/2000/item'])
        self.assertIn('gtrade/personal/2000/item', changes)
        # the caller's dict is theirs
        self.assertEqual(extra, {'gtrade/personal/2000/item': None})

    def test_performTransaction_from_two_threads_loses_no_money(self):
        # games pay out on the database worker while GCoin and GTrade still run on the event loop. Each
        # reads a balance and writes a new one, so without the lock the second overwrites the first.
        balances = {'1000': Decimal('100.00')}
        def readBalance(path):
            result = _mockResult(str(balances.get(path[1])) if path[1] in balances else None)
            time.sleep(0.01)
            return result
        def write(changes):
            for path, value in changes.items():
                if path.endswith('/balance') and path.startswith('gcoin/'):
                    balances[path.split('/')[1]] = Decimal(value)
        GBotFirebaseService.get = MagicMock(side_effect = readBalance)
        GBotFirebaseService.updateMany = MagicMock(side_effect = write)
        GBotFirebaseService.newKey = MagicMock(side_effect = lambda: 'key')
        receiver = {'id': '1000', 'name': 'alice'}
        def pay():
            for _ in range(5):
                gcoin_queries.performTransaction(Decimal('1.00'), self.date, {'id': None, 'name': 'Bank'}, receiver, '', '')
        threads = [threading.Thread(target = pay) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(balances['1000'], Decimal('110.00'))

    def test_performTransaction_refused_writes_nothing(self):
        GBotFirebaseService.get.return_value = _mockResult('1.00')
        with self.assertRaises(EnforceSenderFundsError):
            gcoin_queries.performTransaction(Decimal('5'), self.date, {'id': '1000', 'name': 'a'}, {'id': '2000', 'name': 'b'}, '', '', False, True, {'gtrade/x': None})
        GBotFirebaseService.updateMany.assert_not_called()
    # endregion

    # region validateFunds
    def test_validateFunds_sufficient(self):
        GBotFirebaseService.get.return_value = _mockResult('10.00')
        self.assertTrue(gcoin_queries.validateFunds(Decimal('5'), '1000'))

    def test_validateFunds_exact(self):
        GBotFirebaseService.get.return_value = _mockResult('10.00')
        self.assertTrue(gcoin_queries.validateFunds(Decimal('10'), '1000'))

    def test_validateFunds_insufficient(self):
        GBotFirebaseService.get.return_value = _mockResult('4.00')
        self.assertFalse(gcoin_queries.validateFunds(Decimal('5'), '1000'))
    # endregion

    # region getAllUserBalances
    def test_getAllUserBalances_returns_val(self):
        GBotFirebaseService.get.return_value = _mockResult({'1000': {'balance': '5.00'}})
        self.assertEqual(gcoin_queries.getAllUserBalances(), {'1000': {'balance': '5.00'}})
        GBotFirebaseService.get.assert_called_once_with(['gcoin'])

    def test_getAllUserBalances_returns_none_when_empty(self):
        GBotFirebaseService.get.return_value = _mockResult(None)
        self.assertIsNone(gcoin_queries.getAllUserBalances())
    # endregion

    # region getUserBalance
    def test_getUserBalance_present(self):
        GBotFirebaseService.get.return_value = _mockResult('12.34')
        result = gcoin_queries.getUserBalance('1000')
        self.assertEqual(result, Decimal('12.34'))
        GBotFirebaseService.get.assert_called_once_with(['gcoin', '1000', 'balance'])

    def test_getUserBalance_absent_returns_zero(self):
        GBotFirebaseService.get.return_value = _mockResult(None)
        result = gcoin_queries.getUserBalance('1000')
        self.assertEqual(result, Decimal('0.00'))
    # endregion

    # region getUserTransactionHistory
    def test_getUserTransactionHistory_returns_val(self):
        GBotFirebaseService.get.return_value = _mockResult({'pushKey1': {'gcoin': '+5'}})
        self.assertEqual(gcoin_queries.getUserTransactionHistory('1000'), {'pushKey1': {'gcoin': '+5'}})
        GBotFirebaseService.get.assert_called_once_with(['gcoin', '1000', 'history'])

    def test_getUserTransactionHistory_returns_none_when_empty(self):
        GBotFirebaseService.get.return_value = _mockResult(None)
        self.assertIsNone(gcoin_queries.getUserTransactionHistory('1000'))
    # endregion


if __name__ == '__main__':
    unittest.main()
