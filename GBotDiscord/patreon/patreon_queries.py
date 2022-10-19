#region IMPORTS
from GBotDiscord.firebase import GBotFirebaseService
#endregion

# tables:
    # patreon_members
        # userId
            # serverId

def getAllPatrons():
    result = GBotFirebaseService.get(["patreon_members"])
    return result.val()

def getPatronServerId(userId):
    result = GBotFirebaseService.get(["patreon_members", userId, "serverId"])
    return result.val()

def addPatronEntry(userId, serverId):
    GBotFirebaseService.set(["patreon_members", userId, "serverId"], str(serverId))

def removePatronEntry(userId):
    GBotFirebaseService.remove(["patreon_members", userId])