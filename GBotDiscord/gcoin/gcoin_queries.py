#region IMPORTS
from decimal import Decimal

from GBotDiscord.firebase import GBotFirebaseService
from exceptions import EnforceRealUsersError, EnforceSenderReceiverNotEqual, EnforcePositiveTransactions, EnforceSenderFundsError
#endregion

# tables:
    # gcoin
        # userId
            # balance
            # history

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
        setUserBalance(sender['id'], previousBalance - gcoin)
        senderTrx = {'gcoin': f'-{gcoin}', 'other': receiver['name'], 'date': date, 'memo': senderMemo}
        addUserTrxHistory(sender['id'], senderTrx)
    # if receiver is a real user, update balance and transaction history
    if receiver['id'] != None:
        previousBalance = getUserBalance(receiver['id'])
        setUserBalance(receiver['id'], previousBalance + gcoin)
        receiverTrx = {'gcoin': f'+{gcoin}', 'other': sender['name'], 'date': date, 'memo': receiverMemo}
        addUserTrxHistory(receiver['id'], receiverTrx)

def validateFunds(gcoin, senderId):
    balance = getUserBalance(senderId)
    return gcoin <= balance

def getUserBalance(userId):
    result = GBotFirebaseService.db.child('gcoin').child(userId).child('balance').get(GBotFirebaseService.getAuthToken())
    if result.val() != None:
        return Decimal(result.val())
    else:
        return Decimal('0.00')

def setUserBalance(userId, balance):
    GBotFirebaseService.db.child('gcoin').child(userId).child('balance').set(str(balance))

def addUserTrxHistory(userId, transaction):
    GBotFirebaseService.db.child('gcoin').child(userId).child('history').push(transaction)

def getUserTransactionHistory(userId):
    result = GBotFirebaseService.db.child('gcoin').child(userId).child('history').get(GBotFirebaseService.getAuthToken())
    return result.val()