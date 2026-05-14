#region IMPORTS
import unittest
from decimal import Decimal
from unittest.mock import MagicMock, call

from GBotDiscord.src.firebase import GBotFirebaseService
from GBotDiscord.src.leaderboards import leaderboards_queries
#endregion

# to run this test suite:
#   - execute the following command from the GBot directory: python -m unittest GBotDiscord/test/leaderboards/leaderboards_queries_test.py
#   - or use the "Python: Current File" run configuration to run leaderboards_queries_test.py
#   - or use the "Python: Current File" run configuration to run tests.py to run all test suites

# Snapshot the real module-level functions at import time. Other suites (storms, whodis)
# replace `leaderboards_queries.incrementUserNumValue` with a MagicMock and never restore —
# the snapshot makes this suite order-independent.
_ORIGINAL_LEADERBOARDS_FUNCS = {
    name: getattr(leaderboards_queries, name)
    for name in dir(leaderboards_queries)
    if callable(getattr(leaderboards_queries, name)) and not name.startswith('_')
}


def _mockResult(value):
    """Build a Firebase-style result whose .val() returns `value`."""
    result = MagicMock()
    result.val.return_value = value
    return result


class TestLeaderboardsQueries(unittest.TestCase):

    @classmethod
    def setUpClass(self):
        print('\nExecuting leaderboards queries unit tests...\n')

    @classmethod
    def tearDownClass(self):
        print('\n\nCompleted leaderboards queries unit tests.\n')

    def setUp(self):
        for name, fn in _ORIGINAL_LEADERBOARDS_FUNCS.items():
            setattr(leaderboards_queries, name, fn)
        # Snapshot Firebase primitives so other suites that mutate them don't bleed in.
        self._saved = {
            name: getattr(GBotFirebaseService, name)
            for name in ('get', 'set', 'push', 'update', 'remove')
        }
        GBotFirebaseService.get = MagicMock()
        GBotFirebaseService.set = MagicMock()
        GBotFirebaseService.push = MagicMock()
        GBotFirebaseService.update = MagicMock()
        GBotFirebaseService.remove = MagicMock()

    def tearDown(self):
        for name, fn in self._saved.items():
            setattr(GBotFirebaseService, name, fn)

    # region getLeaderboard

    def test_getLeaderboard_returns_val(self):
        GBotFirebaseService.get.return_value = _mockResult({'u1': {'balance': '10.00'}})
        self.assertEqual(leaderboards_queries.getLeaderboard(), {'u1': {'balance': '10.00'}})
        GBotFirebaseService.get.assert_called_once_with(['leaderboards'])

    def test_getLeaderboard_returns_none_when_empty(self):
        GBotFirebaseService.get.return_value = _mockResult(None)
        self.assertIsNone(leaderboards_queries.getLeaderboard())

    # endregion

    # region setUserName

    def test_setUserName_writes_to_username_path(self):
        leaderboards_queries.setUserName('123', 'alice')
        GBotFirebaseService.set.assert_called_once_with(['leaderboards', '123', 'username'], 'alice')

    # endregion

    # region setUserBalance

    def test_setUserBalance_writes_balance_then_username(self):
        leaderboards_queries.setUserBalance('123', 'alice', Decimal('21.00'))
        self.assertEqual(GBotFirebaseService.set.call_args_list, [
            call(['leaderboards', '123', 'balance'], '21.00'),
            call(['leaderboards', '123', 'username'], 'alice'),
        ])

    def test_setUserBalance_stringifies_non_decimal_balance(self):
        leaderboards_queries.setUserBalance('123', 'alice', 5)
        self.assertEqual(GBotFirebaseService.set.call_args_list[0],
                         call(['leaderboards', '123', 'balance'], '5'))

    # endregion

    # region incrementUserNumValue

    def test_incrementUserNumValue_increments_existing_value(self):
        GBotFirebaseService.get.return_value = _mockResult('4')
        leaderboards_queries.incrementUserNumValue('123', 'alice', 'numStormWins')

        GBotFirebaseService.get.assert_called_once_with(['leaderboards', '123', 'numStormWins'])
        self.assertEqual(GBotFirebaseService.set.call_args_list, [
            call(['leaderboards', '123', 'numStormWins'], '5'),
            call(['leaderboards', '123', 'username'], 'alice'),
        ])

    def test_incrementUserNumValue_missing_starts_at_one(self):
        GBotFirebaseService.get.return_value = _mockResult(None)
        leaderboards_queries.incrementUserNumValue('123', 'alice', 'numStormWins')

        self.assertEqual(GBotFirebaseService.set.call_args_list[0],
                         call(['leaderboards', '123', 'numStormWins'], '1'))

    # endregion

    # region getUserLeaderboardIntValue

    def test_getUserLeaderboardIntValue_present_coerces_to_int(self):
        GBotFirebaseService.get.return_value = _mockResult('7')
        self.assertEqual(leaderboards_queries.getUserLeaderboardIntValue('123', 'numStormWins'), 7)

    def test_getUserLeaderboardIntValue_absent_returns_zero(self):
        GBotFirebaseService.get.return_value = _mockResult(None)
        self.assertEqual(leaderboards_queries.getUserLeaderboardIntValue('123', 'numStormWins'), 0)

    # endregion

    # region getUserLeaderboardDecimalValue

    def test_getUserLeaderboardDecimalValue_present_coerces_to_decimal(self):
        GBotFirebaseService.get.return_value = _mockResult('21.50')
        self.assertEqual(
            leaderboards_queries.getUserLeaderboardDecimalValue('123', 'numNetStormRewards'),
            Decimal('21.50'),
        )

    def test_getUserLeaderboardDecimalValue_absent_returns_zero_decimal(self):
        GBotFirebaseService.get.return_value = _mockResult(None)
        self.assertEqual(
            leaderboards_queries.getUserLeaderboardDecimalValue('123', 'numNetStormRewards'),
            Decimal('0.00'),
        )

    # endregion

    # region addToUserNumRewardsValue

    def test_addToUserNumRewardsValue_adds_and_rounds_to_two_places(self):
        GBotFirebaseService.get.return_value = _mockResult('10.00')
        leaderboards_queries.addToUserNumRewardsValue('123', 'numNetStormRewards', Decimal('5.555'))
        # 10.00 + 5.555 = 15.555 → ROUND_HALF_UP to 2 places → 15.56
        GBotFirebaseService.set.assert_called_once_with(
            ['leaderboards', '123', 'numNetStormRewards'], '15.56'
        )

    def test_addToUserNumRewardsValue_missing_existing_starts_at_zero(self):
        GBotFirebaseService.get.return_value = _mockResult(None)
        leaderboards_queries.addToUserNumRewardsValue('123', 'numWhoDisRewards', Decimal('3.5'))
        GBotFirebaseService.set.assert_called_once_with(
            ['leaderboards', '123', 'numWhoDisRewards'], '3.50'
        )

    def test_addToUserNumRewardsValue_supports_negative_amount(self):
        GBotFirebaseService.get.return_value = _mockResult('10.00')
        leaderboards_queries.addToUserNumRewardsValue('123', 'numNetStormRewards', Decimal('-4.25'))
        GBotFirebaseService.set.assert_called_once_with(
            ['leaderboards', '123', 'numNetStormRewards'], '5.75'
        )

    # endregion

    # region processTransactionForLeaderboardRewards

    def test_processTransactionForLeaderboardRewards_storms_positive(self):
        GBotFirebaseService.get.return_value = _mockResult('0.00')
        leaderboards_queries.processTransactionForLeaderboardRewards(
            '123', {'other': 'Storms reward', 'gcoin': '+2.50'}
        )
        GBotFirebaseService.set.assert_called_once_with(
            ['leaderboards', '123', 'numNetStormRewards'], '2.50'
        )

    def test_processTransactionForLeaderboardRewards_storms_negative_sign_flip(self):
        GBotFirebaseService.get.return_value = _mockResult('10.00')
        leaderboards_queries.processTransactionForLeaderboardRewards(
            '123', {'other': 'Storms entry fee', 'gcoin': '-3.00'}
        )
        # -3.00 added to 10.00 → 7.00
        GBotFirebaseService.set.assert_called_once_with(
            ['leaderboards', '123', 'numNetStormRewards'], '7.00'
        )

    def test_processTransactionForLeaderboardRewards_who_dis_positive(self):
        GBotFirebaseService.get.return_value = _mockResult('1.00')
        leaderboards_queries.processTransactionForLeaderboardRewards(
            '123', {'other': 'Who Dis win', 'gcoin': '+4.00'}
        )
        GBotFirebaseService.set.assert_called_once_with(
            ['leaderboards', '123', 'numWhoDisRewards'], '5.00'
        )

    def test_processTransactionForLeaderboardRewards_unrelated_other_no_writes(self):
        GBotFirebaseService.get.return_value = _mockResult('0.00')
        leaderboards_queries.processTransactionForLeaderboardRewards(
            '123', {'other': 'GTrade purchase', 'gcoin': '+1.00'}
        )
        GBotFirebaseService.set.assert_not_called()

    # endregion


if __name__ == '__main__':
    unittest.main()
