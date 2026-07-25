#region IMPORTS
import unittest
from unittest.mock import MagicMock, call

from GBotDiscord.src.firebase import GBotFirebaseService
from GBotDiscord.src.gtrade import gtrade_queries
#endregion

# to run this test suite:
#   - execute the following command from the GBot directory: python -m unittest GBotDiscord/test/gtrade/gtrade_queries_test.py
#   - or use the "Python: Current File" run configuration to run gtrade_queries_test.py
#   - or use the "Python: Current File" run configuration to run tests.py to run all test suites

# Snapshot the real module-level functions at import time. The gtrade cog test suite
# replaces these functions with MagicMocks and never restores them — the snapshot
# makes this suite order-independent.
_ORIGINAL_GTRADE_FUNCS = {
    name: getattr(gtrade_queries, name)
    for name in dir(gtrade_queries)
    if callable(getattr(gtrade_queries, name)) and not name.startswith('_')
}


def _mockResult(value):
    result = MagicMock()
    result.val.return_value = value
    return result


class TestGTradeQueries(unittest.TestCase):

    @classmethod
    def setUpClass(self):
        print('\nExecuting gtrade queries unit tests...\n')

    @classmethod
    def tearDownClass(self):
        print('\n\nCompleted gtrade queries unit tests.\n')

    def setUp(self):
        for name, fn in _ORIGINAL_GTRADE_FUNCS.items():
            setattr(gtrade_queries, name, fn)
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

    # region createItem
    def test_createItem_pushes_serialized_dict(self):
        gtrade_queries.createItem(
            'user1', 'origName', 5, 'origCreator', 'origServer', 'origDate',
            'curName', 7, 'obtDate', 'image', {'imageUrl': 'http://example/img.png'}
        )
        expectedItem = {
            'originalName': 'origName',
            'originalValue': '5',
            'originalCreator': 'origCreator',
            'originalServer': 'origServer',
            'dateCreated': 'origDate',
            'name': 'curName',
            'value': '7',
            'dateObtained': 'obtDate',
            'dataType': 'image',
            'dataJson': {'imageUrl': 'http://example/img.png'}
        }
        GBotFirebaseService.push.assert_called_once_with(['gtrade', 'personal', 'user1'], expectedItem)
    # endregion

    # region renameItem
    def test_renameItem_updates_name_field(self):
        gtrade_queries.renameItem('user1', 'item1', 'newName')
        GBotFirebaseService.update.assert_called_once_with(
            ['gtrade', 'personal', 'user1', 'item1'], {'name': 'newName'}
        )
    # endregion

    # region removeItem
    def test_removeItem_removes_item_node(self):
        gtrade_queries.removeItem('user1', 'item1')
        GBotFirebaseService.remove.assert_called_once_with(['gtrade', 'personal', 'user1', 'item1'])
    # endregion

    # region getUserItem
    def test_getUserItem_returns_tuple_when_found(self):
        GBotFirebaseService.get.return_value = _mockResult({
            'id1': {'name': 'sword'},
            'id2': {'name': 'shield'}
        })
        result = gtrade_queries.getUserItem('user1', 'shield')
        self.assertEqual(result, ('id2', {'name': 'shield'}))

    def test_getUserItem_returns_none_when_name_not_found(self):
        GBotFirebaseService.get.return_value = _mockResult({'id1': {'name': 'sword'}})
        self.assertIsNone(gtrade_queries.getUserItem('user1', 'shield'))

    def test_getUserItem_returns_none_when_no_items(self):
        GBotFirebaseService.get.return_value = _mockResult(None)
        self.assertIsNone(gtrade_queries.getUserItem('user1', 'sword'))
    # endregion

    # region getAllUserItems
    def test_getAllUserItems_returns_val(self):
        GBotFirebaseService.get.return_value = _mockResult({'id1': {'name': 'sword'}})
        self.assertEqual(gtrade_queries.getAllUserItems('user1'), {'id1': {'name': 'sword'}})
        GBotFirebaseService.get.assert_called_once_with(['gtrade', 'personal', 'user1'])

    def test_getAllUserItems_returns_none_when_empty(self):
        GBotFirebaseService.get.return_value = _mockResult(None)
        self.assertIsNone(gtrade_queries.getAllUserItems('user1'))
    # endregion

    # region createPendingTradeTransaction
    def test_createPendingTradeTransaction_with_buyerId(self):
        item = {'name': 'sword', 'value': '5'}
        gtrade_queries.createPendingTradeTransaction(
            'server1', 'time1', 'chan1', item, 'buy', 'sellerA', 'buyerB'
        )
        GBotFirebaseService.push.assert_called_once_with(
            ['gtrade', 'trade', 'server1'],
            {
                'timePosted': 'time1',
                'sourceChannelId': 'chan1',
                'trxType': 'buy',
                'buyerId': 'buyerB',
                'sellerId': 'sellerA',
                'item': item
            }
        )

    def test_createPendingTradeTransaction_market_default_no_buyer(self):
        item = {'name': 'sword', 'value': '5'}
        gtrade_queries.createPendingTradeTransaction(
            'server1', 'time1', 'chan1', item, 'market', 'sellerA'
        )
        GBotFirebaseService.push.assert_called_once_with(
            ['gtrade', 'trade', 'server1'],
            {
                'timePosted': 'time1',
                'sourceChannelId': 'chan1',
                'trxType': 'market',
                'buyerId': None,
                'sellerId': 'sellerA',
                'item': item
            }
        )
    # endregion

    # region renameItemRelatedPendingTradeTransactions
    def test_renameItemRelatedPendingTradeTransactions_renames_matches_only(self):
        # matrix: two servers, multiple trx; only the matching ones (sellerId + itemName) should rename
        GBotFirebaseService.get.return_value = _mockResult({
            'srv1': {
                'trxMatch1': {'sellerId': '1000', 'item': {'name': 'sword'}},
                'trxNoMatch1': {'sellerId': '1000', 'item': {'name': 'shield'}},
            },
            'srv2': {
                'trxMatch2': {'sellerId': '1000', 'item': {'name': 'sword'}},
                'trxOtherSeller': {'sellerId': '2000', 'item': {'name': 'sword'}},
            }
        })
        gtrade_queries.renameItemRelatedPendingTradeTransactions(1000, 'sword', 'blade')
        # Two matches → two updates
        expected_calls = [
            call(['gtrade', 'trade', 'srv1', 'trxMatch1', 'item'], {'name': 'blade'}),
            call(['gtrade', 'trade', 'srv2', 'trxMatch2', 'item'], {'name': 'blade'}),
        ]
        GBotFirebaseService.update.assert_has_calls(expected_calls, any_order=True)
        self.assertEqual(GBotFirebaseService.update.call_count, 2)

    def test_renameItemRelatedPendingTradeTransactions_no_transactions(self):
        GBotFirebaseService.get.return_value = _mockResult(None)
        gtrade_queries.renameItemRelatedPendingTradeTransactions(1000, 'sword', 'blade')
        GBotFirebaseService.update.assert_not_called()
    # endregion

    # region renameItemPendingTradeTransaction
    def test_renameItemPendingTradeTransaction_updates_item_name(self):
        gtrade_queries.renameItemPendingTradeTransaction('srv1', 'trx1', 'newName')
        GBotFirebaseService.update.assert_called_once_with(
            ['gtrade', 'trade', 'srv1', 'trx1', 'item'], {'name': 'newName'}
        )
    # endregion

    # region removePendingTradeTransactionAndOthersAffected
    def test_removePendingTradeTransactionAndOthersAffected_full_path(self):
        # First .get returns the targeted trx, second .get returns the full all-servers map for relatedness scan
        GBotFirebaseService.get.side_effect = [
            _mockResult({'sellerId': '1000', 'item': {'name': 'sword'}}),
            _mockResult({
                'srv1': {
                    'trxA': {'sellerId': '1000', 'item': {'name': 'sword'}},
                    'trxB': {'sellerId': '1000', 'item': {'name': 'shield'}},
                },
                'srv2': {
                    'trxC': {'sellerId': '1000', 'item': {'name': 'sword'}},
                }
            })
        ]
        gtrade_queries.removePendingTradeTransactionAndOthersAffected('srv1', 'targetTrx')
        # First removal is the explicit target, then related sword transactions (matching sellerId 1000 + name 'sword')
        expected_calls = [
            call(['gtrade', 'trade', 'srv1', 'targetTrx']),
            call(['gtrade', 'trade', 'srv1', 'trxA']),
            call(['gtrade', 'trade', 'srv2', 'trxC']),
        ]
        GBotFirebaseService.remove.assert_has_calls(expected_calls, any_order=True)
        self.assertEqual(GBotFirebaseService.remove.call_count, 3)

    def test_removePendingTradeTransactionAndOthersAffected_pending_missing_no_op(self):
        GBotFirebaseService.get.return_value = _mockResult(None)
        gtrade_queries.removePendingTradeTransactionAndOthersAffected('srv1', 'missing')
        GBotFirebaseService.remove.assert_not_called()
    # endregion

    # region removeRelatedPendingTradeTransactions
    def test_removeRelatedPendingTradeTransactions_removes_matches_only(self):
        GBotFirebaseService.get.return_value = _mockResult({
            'srv1': {
                'match1': {'sellerId': '1000', 'item': {'name': 'sword'}},
                'noMatch1': {'sellerId': '1000', 'item': {'name': 'shield'}},
                'noMatch2': {'sellerId': '2000', 'item': {'name': 'sword'}},
            }
        })
        gtrade_queries.removeRelatedPendingTradeTransactions(1000, 'sword')
        GBotFirebaseService.remove.assert_called_once_with(['gtrade', 'trade', 'srv1', 'match1'])

    def test_removeRelatedPendingTradeTransactions_no_transactions(self):
        GBotFirebaseService.get.return_value = _mockResult(None)
        gtrade_queries.removeRelatedPendingTradeTransactions(1000, 'sword')
        GBotFirebaseService.remove.assert_not_called()
    # endregion

    # region removePendingTradeTransaction
    def test_removePendingTradeTransaction_removes_trx_node(self):
        gtrade_queries.removePendingTradeTransaction('srv1', 'trx1')
        GBotFirebaseService.remove.assert_called_once_with(['gtrade', 'trade', 'srv1', 'trx1'])
    # endregion

    # region removeAllServerPendingTradeTransaction
    def test_removeAllServerPendingTradeTransaction_removes_server_node(self):
        gtrade_queries.removeAllServerPendingTradeTransaction('srv1')
        GBotFirebaseService.remove.assert_called_once_with(['gtrade', 'trade', 'srv1'])
    # endregion

    # region getPendingTradeTransactionWithId
    def test_getPendingTradeTransactionWithId_returns_val(self):
        GBotFirebaseService.get.return_value = _mockResult({'trxType': 'market'})
        self.assertEqual(
            gtrade_queries.getPendingTradeTransactionWithId('srv1', 'trx1'),
            {'trxType': 'market'}
        )
        GBotFirebaseService.get.assert_called_once_with(['gtrade', 'trade', 'srv1', 'trx1'])

    def test_getPendingTradeTransactionWithId_returns_none_when_missing(self):
        GBotFirebaseService.get.return_value = _mockResult(None)
        self.assertIsNone(gtrade_queries.getPendingTradeTransactionWithId('srv1', 'trx1'))
    # endregion

    # region getPendingTradeTransaction
    def test_getPendingTradeTransaction_market_match(self):
        GBotFirebaseService.get.return_value = _mockResult({
            'trx1': {'trxType': 'market', 'sellerId': '1000', 'item': {'name': 'sword'}}
        })
        result = gtrade_queries.getPendingTradeTransaction('srv1', 'market', 'sword', 1000)
        self.assertEqual(result, ('trx1', {'trxType': 'market', 'sellerId': '1000', 'item': {'name': 'sword'}}))

    def test_getPendingTradeTransaction_market_mismatch_seller(self):
        GBotFirebaseService.get.return_value = _mockResult({
            'trx1': {'trxType': 'market', 'sellerId': '2000', 'item': {'name': 'sword'}}
        })
        self.assertIsNone(gtrade_queries.getPendingTradeTransaction('srv1', 'market', 'sword', 1000))

    def test_getPendingTradeTransaction_buy_match(self):
        GBotFirebaseService.get.return_value = _mockResult({
            'trx1': {'trxType': 'buy', 'sellerId': '1000', 'buyerId': '2000', 'item': {'name': 'sword'}}
        })
        result = gtrade_queries.getPendingTradeTransaction('srv1', 'buy', 'sword', 1000, 2000)
        self.assertEqual(result[0], 'trx1')

    def test_getPendingTradeTransaction_buy_no_buyerId_in_trx(self):
        # non-market trx with no buyerId key in dict skips it (no match)
        GBotFirebaseService.get.return_value = _mockResult({
            'trx1': {'trxType': 'buy', 'sellerId': '1000', 'item': {'name': 'sword'}}
        })
        self.assertIsNone(gtrade_queries.getPendingTradeTransaction('srv1', 'buy', 'sword', 1000, 2000))

    def test_getPendingTradeTransaction_buy_wrong_buyer(self):
        GBotFirebaseService.get.return_value = _mockResult({
            'trx1': {'trxType': 'buy', 'sellerId': '1000', 'buyerId': '9999', 'item': {'name': 'sword'}}
        })
        self.assertIsNone(gtrade_queries.getPendingTradeTransaction('srv1', 'buy', 'sword', 1000, 2000))

    def test_getPendingTradeTransaction_no_pending(self):
        GBotFirebaseService.get.return_value = _mockResult(None)
        self.assertIsNone(gtrade_queries.getPendingTradeTransaction('srv1', 'market', 'sword', 1000))
    # endregion

    # region getAllServerPendingTradeTransactions
    def test_getAllServerPendingTradeTransactions_returns_val(self):
        GBotFirebaseService.get.return_value = _mockResult({'trx1': {}})
        self.assertEqual(gtrade_queries.getAllServerPendingTradeTransactions('srv1'), {'trx1': {}})
        GBotFirebaseService.get.assert_called_once_with(['gtrade', 'trade', 'srv1'])
    # endregion

    # region getAllTradeTransactions
    def test_getAllTradeTransactions_returns_val(self):
        GBotFirebaseService.get.return_value = _mockResult({'srv1': {}})
        self.assertEqual(gtrade_queries.getAllTradeTransactions(), {'srv1': {}})
        GBotFirebaseService.get.assert_called_once_with(['gtrade', 'trade'])
    # endregion


if __name__ == '__main__':
    unittest.main()
