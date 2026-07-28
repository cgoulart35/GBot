#region IMPORTS
from decimal import Decimal

from GBotDiscord.src import utils
from GBotDiscord.src.firebase import GBotFirebaseService
#endregion

# tables:
    # leaderboards
        # userId
            # balance
            # numNetStormRewards
            # numStormStarts
            # numStormTier1Multi
            # numStormTier2Multi
            # numStormTier3Multi
            # numStormTier4Multi
            # numStormWins
            # numWhoDisRewards
            # numWhoDisWins
            # username

def getLeaderboard():
    result = GBotFirebaseService.get(["leaderboards"])
    return result.val()

def setUserName(userId, userName):
    GBotFirebaseService.set(['leaderboards', userId, 'username'], userName)

def setUserBalance(userId, userName, balance):
    GBotFirebaseService.set(['leaderboards', userId, 'balance'], str(balance))
    setUserName(userId, userName)

def incrementUserNumValue(userId, userName, item):
    # this needs to be called after an event and NOT at the time of transactions (decouple from GCoin)
    currentIntValue = getUserLeaderboardIntValue(userId, item)
    GBotFirebaseService.set(['leaderboards', userId, item], str(currentIntValue + 1))
    setUserName(userId, userName)

def processTransactionForLeaderboardRewards(userId, transaction, otherId = None):
    # we are only able to update reward-based statistics off of transactions
    # we also don't need to update name here as it was just updated in set balance

    # only system-issued rewards count: those have no counterparty user id. Without this
    # guard the checks below match on the counterparty's *username*, so a real user named
    # "Storms" would credit storm rewards to whoever they transacted with.
    if otherId != None:
        return
    other = transaction['other']
    gcoinStr = transaction['gcoin']
    gcoin = Decimal(gcoinStr[1:])
    signStr = gcoinStr[0]
    if signStr == '-':
        gcoin = gcoin * Decimal('-1')

    if other == "Storms":
        addToUserNumRewardsValue(userId, 'numNetStormRewards', gcoin)
    if other == "Who Dis":
        addToUserNumRewardsValue(userId, 'numWhoDisRewards', gcoin)

def addToUserNumRewardsValue(userId, item, amount):
    currentDecimalValue = getUserLeaderboardDecimalValue(userId, item)
    numRewardsDecimal = currentDecimalValue + amount
    GBotFirebaseService.set(['leaderboards', userId, item], str(utils.roundDecimalPlaces(numRewardsDecimal, 2)))

def getUserLeaderboardIntValue(userId, item):
    result = GBotFirebaseService.get(['leaderboards', userId, item])
    if result.val() != None:
        return int(result.val())
    else:
        return 0
    
def getUserLeaderboardDecimalValue(userId, item):
    result = GBotFirebaseService.get(['leaderboards', userId, item])
    if result.val() != None:
        return Decimal(result.val())
    else:
        return Decimal('0.00')