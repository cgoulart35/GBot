#region IMPORTS
import nextcord
from decimal import Decimal

from GBotDiscord.src import utils
from GBotDiscord.src.firebase import GBotFirebaseService
#endregion

async def create_leaderboard_table_7_0_0(client: nextcord.Client):
    allGCoinData: dict = getAllUserGCoin()
    for userId, gcoinData in allGCoinData.items():

        # create new field "name" under all GCoin users
        user = await client.fetch_user(int(userId))
        name = user.name
        GBotFirebaseService.set(['gcoin', userId, 'username'], name)

        # insert user stats into new leaderboard table
        balance = Decimal(gcoinData['balance'])
        numStormWins = 0
        numNetStormRewards = Decimal('0.00')
        numStormStarts = 0
        numStormTier1Multi = 0
        numStormTier2Multi = 0
        numStormTier3Multi = 0
        numStormTier4Multi = 0
        numWhoDisWins = 0
        numWhoDisRewards = Decimal('0.00')

        for transaction in gcoinData['history']:
            memo = gcoinData['history'][transaction]['memo']
            other = gcoinData['history'][transaction]['other']
            gcoinStr = gcoinData['history'][transaction]['gcoin']
            gcoin = Decimal(gcoinStr[1:])
            signStr = gcoinStr[0]
            if signStr == '-':
                gcoin = gcoin * Decimal('-1')

            if "Won Guess" in memo or "Won Bet" in memo:
                numStormWins += 1
            if "Storms" in other:
                numNetStormRewards += gcoin
            if memo == "Started Storm":
                numStormStarts += 1
            if "x10" in memo:
                numStormTier1Multi += 1
            if "x5" in memo:
                numStormTier2Multi += 1
            if "x2.5" in memo:
                numStormTier3Multi += 1
            if "x1.25" in memo:
                numStormTier4Multi += 1
            if "Who Dis" in other:
                numWhoDisWins += 1
                numWhoDisRewards += gcoin

        leaderboardData = {
            "username" : name,
            "balance" : str(balance),
            "numStormWins" : str(numStormWins),
            "numNetStormRewards" : str(utils.roundDecimalPlaces(numNetStormRewards, 2)),
            "numStormStarts" : str(numStormStarts),
            "numStormTier1Multi" : str(numStormTier1Multi),
            "numStormTier2Multi" : str(numStormTier2Multi),
            "numStormTier3Multi" : str(numStormTier3Multi),
            "numStormTier4Multi" : str(numStormTier4Multi),
            "numWhoDisWins" : str(numWhoDisWins),
            "numWhoDisRewards" : str(utils.roundDecimalPlaces(numWhoDisRewards, 2))
        }
        GBotFirebaseService.set(['leaderboards', userId], leaderboardData)

def getAllUserGCoin():
    result = GBotFirebaseService.get(["gcoin"])
    return result.val()