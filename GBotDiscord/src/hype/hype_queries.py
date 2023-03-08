#region IMPORTS
from GBotDiscord.src.firebase import GBotFirebaseService
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
    GBotFirebaseService.push(["hype_servers", serverId], match)

def removeMatch(serverId, matchId):
    GBotFirebaseService.remove(["hype_servers", serverId, matchId])

def getAllServerMatches(serverId):
    result = GBotFirebaseService.get(["hype_servers", serverId])
    return result.val()