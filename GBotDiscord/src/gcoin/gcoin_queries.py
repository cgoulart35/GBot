#region IMPORTS
import threading
from decimal import Decimal

from GBotDiscord.src.leaderboards import leaderboards_queries
from GBotDiscord.src.firebase import GBotFirebaseService
from GBotDiscord.src.exceptions import EnforceRealUsersError, EnforceSenderReceiverNotEqual, EnforcePositiveTransactions, EnforceSenderFundsError
#endregion

# tables:
    # gcoin
        # userId
            # balance
            # history
            # username

# Everything reaches performTransaction through the database worker, which already runs one thing at a
# time. This keeps a balance safe from being overwritten if a future caller ever isn't on it.
transactionLock = threading.Lock()

def validateTransaction(gcoin, sender, receiver, enforceRealUsers = False, enforceSenderFunds = False):
    # Separate so a command can refuse before it defers, which is what keeps its refusals private.
    # performTransaction always runs this too, so nothing depends on a caller remembering to.
    # throw error if a user is not real when enforceRealUsers is true
    if enforceRealUsers and (sender['id'] == None or receiver['id'] == None):
        raise EnforceRealUsersError
    # throw error if sender and receiver are same person when enforceRealUsers is true
    if enforceRealUsers and sender['id'] == receiver['id']:
        raise EnforceSenderReceiverNotEqual
    # throw error if gcoin amount is below zero
    if gcoin <= Decimal('0'):
        raise EnforcePositiveTransactions
    # throw error if sender has insufficient funds when enforceSenderFunds is true
    if enforceSenderFunds and not validateFunds(gcoin, sender['id']):
        raise EnforceSenderFundsError

def performTransaction(gcoin, date, sender, receiver, senderMemo, receiverMemo, enforceRealUsers = False, enforceSenderFunds = False, extraChanges = None):
    # Every change goes in one atomic write, so a failure can't leave money half moved. extraChanges
    # are firebase.updateMany paths that have to succeed or fail with the money, such as the item in a trade.
    # This is safe for one program at a time. Several programs on one database would need a distributed
    # lock around this function first, because two could read the same balance (see Workstream B).
    with transactionLock:
        validateTransaction(gcoin, sender, receiver, enforceRealUsers, enforceSenderFunds)
        changes = dict(extraChanges) if extraChanges else {}
        # if sender is a real user, update balance and transaction history
        if sender['id'] != None:
            senderTrx = {'gcoin': f'-{gcoin}', 'other': receiver['name'], 'date': date, 'memo': senderMemo}
            changes.update(partyChanges(sender, getUserBalance(sender['id']) - gcoin, senderTrx, receiver['id']))
        # if receiver is a real user, update balance and transaction history
        if receiver['id'] != None:
            receiverTrx = {'gcoin': f'+{gcoin}', 'other': sender['name'], 'date': date, 'memo': receiverMemo}
            changes.update(partyChanges(receiver, getUserBalance(receiver['id']) + gcoin, receiverTrx, sender['id']))
        if changes:
            GBotFirebaseService.updateMany(changes)

def partyChanges(user, balance, transaction, otherId):
    # otherId is the counterparty's user id (None for system parties like Storms/Who Dis/GTrade);
    # the leaderboard needs it to tell a real reward from a transfer with a lookalike username
    path = GBotFirebaseService.path
    userId = user['id']
    return {
        path('gcoin', userId, 'balance'): str(balance),
        path('gcoin', userId, 'username'): user['name'],
        path('gcoin', userId, 'history', GBotFirebaseService.newKey()): transaction,
        **leaderboards_queries.balanceChanges(userId, user['name'], balance),
        **leaderboards_queries.processTransactionForLeaderboardRewards(userId, transaction, otherId)
    }

def validateFunds(gcoin, senderId):
    balance = getUserBalance(senderId)
    return gcoin <= balance
    
def getAllUserBalances():
    result = GBotFirebaseService.get(['gcoin'])
    return result.val()

def getUserBalance(userId):
    result = GBotFirebaseService.get(['gcoin', userId, 'balance'])
    if result.val() != None:
        return Decimal(result.val())
    else:
        return Decimal('0.00')

def getUserTransactionHistory(userId):
    result = GBotFirebaseService.get(['gcoin', userId, 'history'])
    return result.val()