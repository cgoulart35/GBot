#region IMPORTS
from GBotDiscord.src.firebase import GBotFirebaseService
#endregion

# tables:
    # patreon_members
        # userId
            # serverId
            # lapsed: when the daily check found they'd lost the patron role, ISO 8601 in UTC
            # lapseNotified: true once that server's admins were told
    # trials: one per server ever on a free trial, kept after GBot leaves so re-adding it starts none
        # serverId
            # started: when it began, ISO 8601 in UTC
            # reminded: the last reminder sent (access.REMINDER_*), absent before the first

def getAllPatrons():
    result = GBotFirebaseService.get(["patreon_members"])
    return result.val()

def getPatronServerId(userId):
    result = GBotFirebaseService.get(["patreon_members", userId, "serverId"])
    return result.val()

def addPatronEntry(userId, serverId):
    # the whole entry, so registering again clears a lapse
    GBotFirebaseService.set(["patreon_members", userId], {"serverId": str(serverId)})

def setPatronLapsed(userId, lapsed):
    GBotFirebaseService.set(["patreon_members", userId, "lapsed"], lapsed)

def setPatronLapseNotified(userId):
    GBotFirebaseService.set(["patreon_members", userId, "lapseNotified"], True)

def removePatronEntry(userId):
    GBotFirebaseService.remove(["patreon_members", userId])

def getTrial(serverId):
    result = GBotFirebaseService.get(["trials", str(serverId)])
    return result.val()

def getAllTrials():
    result = GBotFirebaseService.get(["trials"])
    return result.val()

def setTrial(serverId, started):
    GBotFirebaseService.set(["trials", str(serverId)], {"started": started})

def setTrialReminded(serverId, reminder):
    GBotFirebaseService.set(["trials", str(serverId), "reminded"], reminder)
