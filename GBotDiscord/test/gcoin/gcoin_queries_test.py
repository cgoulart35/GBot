#region IMPORTS
import unittest
from unittest.mock import MagicMock, call
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
            for name in ('get', 'set', 'push', 'update', 'remove')
        }
        GBotFirebaseService.get = MagicMock()
        GBotFirebaseService.set = MagicMock()
        GBotFirebaseService.push = MagicMock()
        GBotFirebaseService.update = MagicMock()
        GBotFirebaseService.remove = MagicMock()
        # Isolate gcoin_queries from leaderboards_queries side-effects.
        leaderboards_queries.setUserBalance = MagicMock()
        leaderboards_queries.processTransactionForLeaderboardRewards = MagicMock()

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
    def test_performTransaction_real_to_real(self):
        # Two reads (sender + receiver balance), two sets (balances), two name sets,
        # two pushes (history), two leaderboards.setUserBalance, two leaderboards.processTrx
        GBotFirebaseService.get.return_value = _mockResult('100.00')
        sender = {'id': '1000', 'name': 'alice'}
        receiver = {'id': '2000', 'name': 'bob'}
        gcoin_queries.performTransaction(
            Decimal('25'), self.date, sender, receiver, 'sentMemo', 'recvMemo'
        )
        # balance writes — Decimal subtraction preserves operand precision (100.00 - 25 → 75.00)
        GBotFirebaseService.set.assert_any_call(['gcoin', '1000', 'balance'], '75.00')
        GBotFirebaseService.set.assert_any_call(['gcoin', '2000', 'balance'], '125.00')
        # username writes (via setUserName)
        GBotFirebaseService.set.assert_any_call(['gcoin', '1000', 'username'], 'alice')
        GBotFirebaseService.set.assert_any_call(['gcoin', '2000', 'username'], 'bob')
        # history pushes
        GBotFirebaseService.push.assert_any_call(
            ['gcoin', '1000', 'history'],
            {'gcoin': '-25', 'other': 'bob', 'date': self.date, 'memo': 'sentMemo'}
        )
        GBotFirebaseService.push.assert_any_call(
            ['gcoin', '2000', 'history'],
            {'gcoin': '+25', 'other': 'alice', 'date': self.date, 'memo': 'recvMemo'}
        )
        # leaderboards setUserBalance called for both
        leaderboards_queries.setUserBalance.assert_has_calls([
            call('1000', 'alice', Decimal('75.00')),
            call('2000', 'bob', Decimal('125.00')),
        ], any_order=True)
        self.assertEqual(leaderboards_queries.setUserBalance.call_count, 2)
        # leaderboards processTrx called for both pushed trx
        self.assertEqual(leaderboards_queries.processTransactionForLeaderboardRewards.call_count, 2)

    def test_performTransaction_real_to_virtual(self):
        GBotFirebaseService.get.return_value = _mockResult('50.00')
        sender = {'id': '1000', 'name': 'alice'}
        receiver = {'id': None, 'name': 'BankOfGCoin'}
        gcoin_queries.performTransaction(
            Decimal('10'), self.date, sender, receiver, 'sentMemo', 'recvMemo'
        )
        # Only sender side touched
        GBotFirebaseService.set.assert_any_call(['gcoin', '1000', 'balance'], '40.00')
        GBotFirebaseService.push.assert_called_once_with(
            ['gcoin', '1000', 'history'],
            {'gcoin': '-10', 'other': 'BankOfGCoin', 'date': self.date, 'memo': 'sentMemo'}
        )
        leaderboards_queries.setUserBalance.assert_called_once_with('1000', 'alice', Decimal('40.00'))
        self.assertEqual(leaderboards_queries.processTransactionForLeaderboardRewards.call_count, 1)

    def test_performTransaction_virtual_to_real(self):
        GBotFirebaseService.get.return_value = _mockResult('20.00')
        sender = {'id': None, 'name': 'BankOfGCoin'}
        receiver = {'id': '2000', 'name': 'bob'}
        gcoin_queries.performTransaction(
            Decimal('5'), self.date, sender, receiver, 'sentMemo', 'recvMemo'
        )
        # Only receiver side touched
        GBotFirebaseService.set.assert_any_call(['gcoin', '2000', 'balance'], '25.00')
        GBotFirebaseService.push.assert_called_once_with(
            ['gcoin', '2000', 'history'],
            {'gcoin': '+5', 'other': 'BankOfGCoin', 'date': self.date, 'memo': 'recvMemo'}
        )
        leaderboards_queries.setUserBalance.assert_called_once_with('2000', 'bob', Decimal('25.00'))
        self.assertEqual(leaderboards_queries.processTransactionForLeaderboardRewards.call_count, 1)

    def test_performTransaction_virtual_to_virtual_noop(self):
        sender = {'id': None, 'name': 'BankA'}
        receiver = {'id': None, 'name': 'BankB'}
        gcoin_queries.performTransaction(
            Decimal('3'), self.date, sender, receiver, 'sentMemo', 'recvMemo'
        )
        GBotFirebaseService.set.assert_not_called()
        GBotFirebaseService.push.assert_not_called()
        leaderboards_queries.setUserBalance.assert_not_called()
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
        GBotFirebaseService.set.assert_any_call(['gcoin', '1000', 'balance'], '50.00')
        GBotFirebaseService.set.assert_any_call(['gcoin', '2000', 'balance'], '150.00')
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

    # region setUserBalance
    def test_setUserBalance_writes_balance_username_and_leaderboard(self):
        gcoin_queries.setUserBalance('1000', 'alice', Decimal('42.50'))
        GBotFirebaseService.set.assert_any_call(['gcoin', '1000', 'balance'], '42.50')
        GBotFirebaseService.set.assert_any_call(['gcoin', '1000', 'username'], 'alice')
        leaderboards_queries.setUserBalance.assert_called_once_with('1000', 'alice', Decimal('42.50'))
    # endregion

    # region setUserName
    def test_setUserName_writes_username(self):
        gcoin_queries.setUserName('1000', 'alice')
        GBotFirebaseService.set.assert_called_once_with(['gcoin', '1000', 'username'], 'alice')
    # endregion

    # region addUserTrxHistory
    def test_addUserTrxHistory_pushes_and_processes_rewards(self):
        trx = {'gcoin': '+5', 'other': 'Storms', 'date': self.date, 'memo': 'win'}
        gcoin_queries.addUserTrxHistory('1000', trx)
        GBotFirebaseService.push.assert_called_once_with(['gcoin', '1000', 'history'], trx)
        leaderboards_queries.processTransactionForLeaderboardRewards.assert_called_once_with('1000', trx, None)

    def test_addUserTrxHistory_forwards_counterparty_id(self):
        # the counterparty id is what lets the leaderboard tell a system reward from a
        # user-to-user transfer with a lookalike username (A-10)
        trx = {'gcoin': '+5', 'other': 'Storms', 'date': self.date, 'memo': 'received'}
        gcoin_queries.addUserTrxHistory('1000', trx, '2000')
        leaderboards_queries.processTransactionForLeaderboardRewards.assert_called_once_with('1000', trx, '2000')
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
