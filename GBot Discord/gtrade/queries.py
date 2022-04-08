#region IMPORTS
import firebase
#endregion

# tables:
    # gtrade
        # personal
            # id
                # item (unique id)
                    # originalName
                    # originalValue
                    # originalCreator
                    # originalServer
                    # dateCreated
                    # name
                    # value
                    # dateObtained
                    # dataType
                    # dataJson
        # trade
            # serverId
                # pendingTransaction (unique id)
                    # timePosted
                    # sourceChannelId
                    # trxType
                    # buyerId
                    # sellerId
                    # item
                        # originalName
                        # originalValue
                        # originalCreator
                        # originalServer
                        # dateCreated
                        # name
                        # value
                        # dateObtained
                        # dataType
                        # dataJson

def createItem(userId, originalName, originalValue, originalCreator, originalServer, dateCreated, name, value, dateObtained, dataType, dataJson):
    item = {
        'originalName': originalName,
        'originalValue': str(originalValue),
        'originalCreator': originalCreator,
        'originalServer': originalServer,
        'dateCreated': dateCreated,
        'name': name,        
        'value': str(value),
        'dateObtained': dateObtained,
        'dataType': dataType,
        'dataJson': dataJson
    }
    firebase.db.child('gtrade').child('personal').child(userId).push(item)

def renameItem(userId, itemId, newName):
    firebase.db.child("gtrade").child('personal').child(userId).child(itemId).update({'name': newName})

def removeItem(userId, itemId):
    firebase.db.child("gtrade").child('personal').child(userId).child(itemId).remove(firebase.getAuthToken())

def getUserItem(userId, itemName):
    allUserItems = getAllUserItems(userId)
    if allUserItems != None:
        for itemId, item in allUserItems.items():
            name = item['name']
            if name == itemName:
                return (itemId, item)
    return None

def getAllUserItems(userId):
    result = firebase.db.child('gtrade').child('personal').child(userId).get(firebase.getAuthToken())
    return result.val()

def createPendingTradeTransaction(serverId, time, channelId, item, trxType, sellerId, buyerId = None):
    # sellerId always needed (market sale and buy/sell requests), but buyerId not needed for market sale (defined on trade completion)
    pendingTransaction = {
        'timePosted': time,
        'sourceChannelId': channelId,
        'trxType': trxType,
        'buyerId': buyerId,
        'sellerId': sellerId,
        'item': item
    }
    firebase.db.child('gtrade').child('trade').child(serverId).push(pendingTransaction)

def renameItemRelatedPendingTradeTransactions(sellerId, itemName, newName):
    allServersTransactionsMap = getAllTradeTransactions()
    if allServersTransactionsMap != None:
        for serverId, serverTransactionMap in allServersTransactionsMap.items():
            for trxId, trx in serverTransactionMap.items():
                if trx['sellerId'] == sellerId and trx['item']['name'] == itemName:
                    renameItemPendingTradeTransaction(serverId, trxId, newName)

def renameItemPendingTradeTransaction(serverId, pendingTransactionId, newName):
    firebase.db.child("gtrade").child('trade').child(serverId).child(pendingTransactionId).child('item').update({'name': newName})

def removePendingTradeTransactionAndOthersAffected(serverId, pendingTransactionId):
    pendingTrx = getPendingTradeTransactionWithId(serverId, pendingTransactionId)
    if pendingTrx != None:
        removePendingTradeTransaction(serverId, pendingTransactionId)
        sellerId = pendingTrx['sellerId']
        itemName = pendingTrx['item']['name']
        removeRelatedPendingTradeTransactions(sellerId, itemName)

def removeRelatedPendingTradeTransactions(sellerId, itemName):
    allServersTransactionsMap = getAllTradeTransactions()
    if allServersTransactionsMap != None:
        for serverId, serverTransactionMap in allServersTransactionsMap.items():
            for trxId, trx in serverTransactionMap.items():
                if trx['sellerId'] == sellerId and trx['item']['name'] == itemName:
                    removePendingTradeTransaction(serverId, trxId)

def removePendingTradeTransaction(serverId, pendingTransactionId):
    firebase.db.child("gtrade").child('trade').child(serverId).child(pendingTransactionId).remove(firebase.getAuthToken())

def removeAllServerPendingTradeTransaction(serverId):
    firebase.db.child("gtrade").child('trade').child(serverId).remove(firebase.getAuthToken())

def getPendingTradeTransactionWithId(serverId, pendingTransactionId):
    result = firebase.db.child('gtrade').child('trade').child(serverId).child(pendingTransactionId).get(firebase.getAuthToken())
    return result.val()

def getPendingTradeTransaction(serverId, trxType, itemName, sellerId, buyerId = None):
    allPending = getAllServerPendingTradeTransactions(serverId)
    if allPending != None:
        for trxId, trx in allPending.items():
            item = trx['item']
            thisItemName = item['name']
            thisSellerId = trx['sellerId']
            thisTrxType = trx['trxType']
            if trxType == 'market':
                if thisSellerId == sellerId and thisItemName == itemName and thisTrxType == trxType:
                    return (trxId, trx)
            elif 'buyerId' in trx:
                thisBuyerId = trx['buyerId']
                if thisSellerId == sellerId and thisBuyerId == buyerId and thisItemName == itemName and thisTrxType == trxType:
                    return (trxId, trx)
    return None

def getAllServerPendingTradeTransactions(serverId):
    result = firebase.db.child('gtrade').child('trade').child(serverId).get(firebase.getAuthToken())
    return result.val()

def getAllTradeTransactions():
    result = firebase.db.child('gtrade').child('trade').get(firebase.getAuthToken())
    return result.val()