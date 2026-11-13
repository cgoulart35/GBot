#region IMPORTS
from GBotDiscord.src.firebase import GBotFirebaseService
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
                    # messageChannelId, messageId, messageShared (where it was announced, once it has been)
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

def createItemChanges(userId, originalName, originalValue, originalCreator, originalServer, dateCreated, name, value, dateObtained, dataType, dataJson):
    # this module's *Changes functions return paths for gcoin_queries.performTransaction's extraChanges,
    # so an item moves in the same atomic write as the money it cost
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
    return {GBotFirebaseService.path('gtrade', 'personal', userId, GBotFirebaseService.newKey()): item}

def setItemImageUrl(userId, itemId, imageUrl):
    # only on an item still theirs: one sold or destroyed while its image uploaded would come back as
    # half an item, an image with no name or value
    if GBotFirebaseService.get(['gtrade', 'personal', userId, itemId]).val() is None:
        return
    GBotFirebaseService.update(['gtrade', 'personal', userId, itemId, 'dataJson'], {'imageUrl': imageUrl})

def renameItem(userId, itemId, newName):
    GBotFirebaseService.update(['gtrade', 'personal', userId, itemId], {'name': newName})

def removeItemChanges(userId, itemId):
    return {GBotFirebaseService.path('gtrade', 'personal', userId, itemId): None}

def getUserItem(userId, itemName):
    allUserItems = getAllUserItems(userId)
    if allUserItems != None:
        for itemId, item in allUserItems.items():
            name = item['name']
            if name == itemName:
                return (itemId, item)
    return None

def getAllUserItems(userId):
    result = GBotFirebaseService.get(['gtrade', 'personal', userId])
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
    return GBotFirebaseService.push(['gtrade', 'trade', serverId], pendingTransaction)

def renameItemRelatedPendingTradeTransactions(sellerId, itemName, newName):
    allServersTransactionsMap = getAllTradeTransactions()
    if allServersTransactionsMap != None:
        for serverId, serverTransactionMap in allServersTransactionsMap.items():
            for trxId, trx in serverTransactionMap.items():
                if trx['sellerId'] == str(sellerId) and trx['item']['name'] == itemName:
                    renameItemPendingTradeTransaction(serverId, trxId, newName)

def renameItemPendingTradeTransaction(serverId, pendingTransactionId, newName):
    GBotFirebaseService.update(['gtrade', 'trade', serverId, pendingTransactionId, 'item'], {'name': newName})

def removeRelatedPendingTradeTransactionsChanges(sellerId, itemName, found = None):
    # every pending transaction for this item, in every server it is listed in. found: given a list,
    # {server: those transactions, each with its trxId} is added to it, from the same read, for
    # whoever tidies the messages they were announced in
    changes = {}
    related = {}
    allServersTransactionsMap = getAllTradeTransactions()
    if allServersTransactionsMap != None:
        for serverId, serverTransactionMap in allServersTransactionsMap.items():
            for trxId, trx in serverTransactionMap.items():
                if trx['sellerId'] == str(sellerId) and trx['item']['name'] == itemName:
                    changes[GBotFirebaseService.path('gtrade', 'trade', serverId, trxId)] = None
                    related.setdefault(serverId, []).append(dict(trx, trxId = trxId))
    if found is not None:
        found.append(related)
    return changes

def removePendingTradeTransaction(serverId, pendingTransactionId):
    GBotFirebaseService.remove(['gtrade', 'trade', serverId, pendingTransactionId])

def removeAllServerPendingTradeTransaction(serverId):
    GBotFirebaseService.remove(['gtrade', 'trade', serverId])

def setTradeMessage(serverId, pendingTransactionId, channelId, messageId, shared = False, line = None):
    # Where a trade was announced, so its message can say so once the trade ends some other way than by
    # its own buttons. shared: one message standing for several trades. Only for a trade still there:
    # an update to one removed a moment before would bring back half a trade.
    if getPendingTradeTransactionWithId(serverId, pendingTransactionId) is None:
        return
    # line: its own line on a message shared by several, kept as posted, as a rename changes the item's name
    GBotFirebaseService.update(['gtrade', 'trade', serverId, pendingTransactionId], {'messageChannelId': str(channelId), 'messageId': str(messageId), 'messageShared': shared, **({'messageLine': line} if line else {})})

def getPendingTradeTransactionWithId(serverId, pendingTransactionId):
    result = GBotFirebaseService.get(['gtrade', 'trade', serverId, pendingTransactionId])
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
                if thisSellerId == str(sellerId) and thisItemName == itemName and thisTrxType == trxType:
                    return (trxId, trx)
            elif 'buyerId' in trx:
                thisBuyerId = trx['buyerId']
                if thisSellerId == str(sellerId) and thisBuyerId == str(buyerId) and thisItemName == itemName and thisTrxType == trxType:
                    return (trxId, trx)
    return None

def getAllServerPendingTradeTransactions(serverId):
    result = GBotFirebaseService.get(['gtrade', 'trade', serverId])
    return result.val()

def getAllTradeTransactions():
    result = GBotFirebaseService.get(['gtrade', 'trade'])
    return result.val()