#region IMPORTS
from GBotDiscord.firebase import GBotFirebaseService
#endregion

# tables:
    # hype_servers
        # serverId
            # match (unique id)
                # regex
                # responses
                # isReaction

def createMatch(serverId, regex, responses, isReaction):
    match = {
        'regex': regex,
        'responses': responses,
        'isReaction': isReaction
    }
    GBotFirebaseService.db.child("hype_servers").child(serverId).push(match)

def removeMatch(serverId, matchId):
    GBotFirebaseService.db.child("hype_servers").child(serverId).child(matchId).remove(GBotFirebaseService.getAuthToken())

def getAllServerMatches(serverId):
    result = GBotFirebaseService.db.child('hype_servers').child(serverId).get(GBotFirebaseService.getAuthToken())
    return result.val()