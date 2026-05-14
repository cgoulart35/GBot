#region IMPORTS
import unittest
from unittest.mock import MagicMock, AsyncMock, call

import nextcord
from nextcord.ext import commands

from GBotDiscord.src.firebase import GBotFirebaseService
from GBotDiscord.src.quart_api import development_queries
#endregion

# Snapshot the real module-level functions at import time so monkey-patching across
# tests (and other suites mutating these names) does not bleed in.
_ORIGINAL_DEV_QUERIES = {
    name: getattr(development_queries, name)
    for name in dir(development_queries)
    if callable(getattr(development_queries, name)) and not name.startswith('_')
}


def _mockResult(value):
    """Build a Firebase-style result whose .val() returns `value`."""
    result = MagicMock()
    result.val.return_value = value
    return result


# to run this test suite:
#   - execute the following command from the GBot directory: python -m unittest GBotDiscord/test/quart_api/development_queries_test.py
#   - or use the "Python: Current File" run configuration to run development_queries_test.py
#   - or use the "Python: Current File" run configuration to run tests.py to run all test suites
class TestDevelopmentQueries(unittest.IsolatedAsyncioTestCase):

    @classmethod
    def setUpClass(self):
        print('\nExecuting development_queries unit tests...\n')

    @classmethod
    def tearDownClass(self):
        print('\n\nCompleted development_queries unit tests.\n')

    def setUp(self):
        for name, fn in _ORIGINAL_DEV_QUERIES.items():
            setattr(development_queries, name, fn)
        self._saved = {
            name: getattr(GBotFirebaseService, name)
            for name in ('get', 'set', 'push', 'update', 'remove')
        }
        GBotFirebaseService.get = MagicMock()
        GBotFirebaseService.set = MagicMock()
        GBotFirebaseService.push = MagicMock()
        GBotFirebaseService.update = MagicMock()
        GBotFirebaseService.remove = MagicMock()

        self.client: nextcord.Client = commands.Bot()

    def tearDown(self):
        for name, fn in self._saved.items():
            setattr(GBotFirebaseService, name, fn)

    # region getAllUserGCoin

    def test_getAllUserGCoin_returns_val_of_gcoin_root(self):
        payload = {'123': {'balance': '10.00', 'history': {}}}
        GBotFirebaseService.get.return_value = _mockResult(payload)

        result = development_queries.getAllUserGCoin()

        GBotFirebaseService.get.assert_called_once_with(['gcoin'])
        self.assertEqual(result, payload)

    def test_getAllUserGCoin_returns_none_when_empty(self):
        GBotFirebaseService.get.return_value = _mockResult(None)
        self.assertIsNone(development_queries.getAllUserGCoin())

    # endregion

    # region create_leaderboard_table_7_0_0

    async def test_create_leaderboard_table_7_0_0_empty_users_no_writes(self):
        development_queries.getAllUserGCoin = MagicMock(return_value={})
        self.client.fetch_user = AsyncMock()

        await development_queries.create_leaderboard_table_7_0_0(self.client)

        self.client.fetch_user.assert_not_awaited()
        GBotFirebaseService.set.assert_not_called()

    async def test_create_leaderboard_table_7_0_0_covers_every_memo_branch(self):
        # Each transaction is crafted to hit exactly one memo/other branch (and
        # nothing else accidentally — e.g. "Storm x5" does not contain "x10",
        # "Storm x2.5" does not contain "x5", and "Storm x1.25" does not contain
        # "x5" as a substring).
        development_queries.getAllUserGCoin = MagicMock(return_value={
            '123': {
                'balance': '100.00',
                'history': {
                    't1': {'memo': 'Won Guess',    'other': 'Storms',  'gcoin': '+5.00'},
                    't2': {'memo': 'Won Bet',      'other': 'Storms',  'gcoin': '+3.00'},
                    't3': {'memo': 'Started Storm','other': 'Storms',  'gcoin': '-2.00'},
                    't4': {'memo': 'Storm x10',    'other': 'Storms',  'gcoin': '+10.00'},
                    't5': {'memo': 'Storm x5',     'other': 'Storms',  'gcoin': '+5.00'},
                    't6': {'memo': 'Storm x2.5',   'other': 'Storms',  'gcoin': '+2.50'},
                    't7': {'memo': 'Storm x1.25',  'other': 'Storms',  'gcoin': '+1.25'},
                    't8': {'memo': 'Reward',       'other': 'Who Dis', 'gcoin': '+4.00'},
                },
            },
        })
        user = MagicMock()
        user.name = 'alice'
        self.client.fetch_user = AsyncMock(return_value=user)

        await development_queries.create_leaderboard_table_7_0_0(self.client)

        self.client.fetch_user.assert_awaited_once_with(123)

        expectedLeaderboardData = {
            'username': 'alice',
            'balance': '100.00',
            'numStormWins': '2',
            'numNetStormRewards': '24.75',
            'numStormStarts': '1',
            'numStormTier1Multi': '1',
            'numStormTier2Multi': '1',
            'numStormTier3Multi': '1',
            'numStormTier4Multi': '1',
            'numWhoDisWins': '1',
            'numWhoDisRewards': '4.00',
        }
        self.assertEqual(GBotFirebaseService.set.call_args_list, [
            call(['gcoin', '123', 'username'], 'alice'),
            call(['leaderboards', '123'], expectedLeaderboardData),
        ])

    async def test_create_leaderboard_table_7_0_0_negative_gcoin_sign_flip_for_who_dis(self):
        # Negative "Who Dis" entry still increments numWhoDisWins (the code does
        # not gate on sign), and the sign-flipped gcoin reduces numWhoDisRewards.
        development_queries.getAllUserGCoin = MagicMock(return_value={
            '456': {
                'balance': '0.00',
                'history': {
                    't1': {'memo': 'Win',  'other': 'Who Dis', 'gcoin': '+10.00'},
                    't2': {'memo': 'Fine', 'other': 'Who Dis', 'gcoin': '-2.50'},
                },
            },
        })
        user = MagicMock()
        user.name = 'bob'
        self.client.fetch_user = AsyncMock(return_value=user)

        await development_queries.create_leaderboard_table_7_0_0(self.client)

        leaderboardCall = GBotFirebaseService.set.call_args_list[1]
        leaderboardData = leaderboardCall.args[1]
        self.assertEqual(leaderboardData['numWhoDisWins'], '2')
        self.assertEqual(leaderboardData['numWhoDisRewards'], '7.50')

    async def test_create_leaderboard_table_7_0_0_iterates_every_user(self):
        development_queries.getAllUserGCoin = MagicMock(return_value={
            '111': {'balance': '1.00', 'history': {}},
            '222': {'balance': '2.00', 'history': {}},
        })
        users = {
            111: MagicMock(name='alice_user'),
            222: MagicMock(name='bob_user'),
        }
        users[111].name = 'alice'
        users[222].name = 'bob'
        self.client.fetch_user = AsyncMock(side_effect=lambda uid: users[uid])

        await development_queries.create_leaderboard_table_7_0_0(self.client)

        self.assertEqual(self.client.fetch_user.await_count, 2)
        usernameSetCalls = [
            c for c in GBotFirebaseService.set.call_args_list
            if c.args[0][0] == 'gcoin'
        ]
        leaderboardSetCalls = [
            c for c in GBotFirebaseService.set.call_args_list
            if c.args[0][0] == 'leaderboards'
        ]
        self.assertEqual(len(usernameSetCalls), 2)
        self.assertEqual(len(leaderboardSetCalls), 2)

    # endregion


if __name__ == '__main__':
    unittest.main()
