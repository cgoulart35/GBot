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

def updateMatch(serverId, matchId, regex, responses):
    # a reply stays a reply and a reaction a reaction: only what it matches and says can change.
    # Whether it was there to change: an update to one deleted meanwhile would leave half a match,
    # with no isReaction, which would then fail on every message in its server.
    if GBotFirebaseService.get(["hype_servers", serverId, matchId]).val() is None:
        return False
    GBotFirebaseService.update(["hype_servers", serverId, matchId], {'regex': regex, 'responses': responses})
    return True

def removeMatch(serverId, matchId):
    GBotFirebaseService.remove(["hype_servers", serverId, matchId])

def getAllServerMatches(serverId):
    result = GBotFirebaseService.get(["hype_servers", serverId])
    return result.val()