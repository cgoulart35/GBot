#region IMPORTS
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

def performTransaction(gcoin, date, sender, receiver, senderMemo, receiverMemo, enforceRealUsers = False, enforceSenderFunds = False):
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
    # if sender is a real user, update balance and transaction history
    if sender['id'] != None:
        previousBalance = getUserBalance(sender['id'])
        setUserBalance(sender['id'], sender['name'], previousBalance - gcoin)
        senderTrx = {'gcoin': f'-{gcoin}', 'other': receiver['name'], 'date': date, 'memo': senderMemo}
        addUserTrxHistory(sender['id'], senderTrx)
    # if receiver is a real user, update balance and transaction history
    if receiver['id'] != None:
        previousBalance = getUserBalance(receiver['id'])
        setUserBalance(receiver['id'], receiver['name'], previousBalance + gcoin)
        receiverTrx = {'gcoin': f'+{gcoin}', 'other': sender['name'], 'date': date, 'memo': receiverMemo}
        addUserTrxHistory(receiver['id'], receiverTrx)

def validateFunds(gcoin, senderId):
    balance = getUserBalance(senderId)
    return gcoin <= balance

def getUserBalance(userId):
    result = GBotFirebaseService.get(['gcoin', userId, 'balance'])
    if result.val() != None:
        return Decimal(result.val())
    else:
        return Decimal('0.00')

def setUserBalance(userId, userName, balance):
    GBotFirebaseService.set(['gcoin', userId, 'balance'], str(balance))
    setUserName(userId, userName)
    leaderboards_queries.setUserBalance(userId, userName, balance)

def setUserName(userId, userName):
    GBotFirebaseService.set(['gcoin', userId, 'username'], userName)

def addUserTrxHistory(userId, transaction):
    GBotFirebaseService.push(['gcoin', userId, 'history'], transaction)
    leaderboards_queries.processTransactionForLeaderboardRewards(userId, transaction)

def getUserTransactionHistory(userId):
    result = GBotFirebaseService.get(['gcoin', userId, 'history'])
    return result.val()