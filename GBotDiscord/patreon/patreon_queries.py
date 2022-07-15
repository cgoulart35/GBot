#region IMPORTS
from GBotDiscord.firebase import GBotFirebaseService
#endregion

# tables:
    # patreon_members
        # userId
            # serverId

def getAllPatrons():
    result = GBotFirebaseService.db.child("patreon_members").get(GBotFirebaseService.getAuthToken())
    return result.val()

def getPatronServerId(userId):
    result = GBotFirebaseService.db.child("patreon_members").child(userId).child('serverId').get(GBotFirebaseService.getAuthToken())
    return result.val()

def addPatronEntry(userId, serverId):
    GBotFirebaseService.db.child('patreon_members').child(userId).child('serverId').set(str(serverId))

def removePatronEntry(userId):
    GBotFirebaseService.db.child("patreon_members").child(userId).remove(GBotFirebaseService.getAuthToken())