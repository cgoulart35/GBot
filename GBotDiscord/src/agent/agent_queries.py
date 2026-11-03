#region IMPORTS
from cryptography.fernet import Fernet, InvalidToken

from GBotDiscord.src.firebase import GBotFirebaseService
from GBotDiscord.src.properties import GBotPropertiesManager
#endregion

# tables:
    # agent_servers
        # serverId
            # provider (only 'anthropic' today)
            # apiKey (encrypted, see encryptKey; absent on servers that use GBot's key)
            # model
            # supportsEffort (whether model accepts an effort setting, recorded when it is chosen)
            # instructions
            # mode ('addressed', 'always' or 'off')
            # access ('everyone' or 'admins')
            # memoryAccess ('admins' or 'everyone')
            # mentions ('off', 'people' or 'roles')
            # music (whether it can control music, off when missing)
            # limits
                # tokens, cooldown, replyTokens, history, memberMemories
            # usage
                # day (UTC, %Y-%m-%d), tokens
            # channels
                # channelId
                    # instructions, mode, access, images, mentions
            # memories
                # memory (unique id)
                    # text, savedBy, savedById, byAdmin (from Discord roles when saved), date, editedBy, channelId (missing when it's for the whole server)
    # agent_shared
        # usage (what every server on GBot's own key used together)
            # day (UTC, %Y-%m-%d), tokens

PROVIDER = 'anthropic'
MEMORY_SAVED = 'saved'
MEMORY_FULL = 'full'
MEMORY_MEMBER_LIMIT = 'member limit'

def encryptKey(apiKey):
    return Fernet(GBotPropertiesManager.AGENT_KEY_SECRET).encrypt(apiKey.encode()).decode()

def decryptKey(encrypted):
    # None rather than an error: a missing or replaced secret means the server has to enter its key
    # again, which is the same thing the bot does when there is no key at all
    try:
        return Fernet(GBotPropertiesManager.AGENT_KEY_SECRET).decrypt(encrypted.encode()).decode()
    except (InvalidToken, ValueError, TypeError, AttributeError):
        return None

def getServerConfig(serverId):
    return GBotFirebaseService.get(["agent_servers", serverId]).val() or {}

def setServerValues(serverId, values):
    GBotFirebaseService.update(["agent_servers", serverId], values)

def removeServerValue(serverId, name):
    GBotFirebaseService.remove(["agent_servers", serverId, name])

def setChannelValue(serverId, channelId, name, value):
    # the database refuses None, and clearing a value means removing it
    if value is None:
        GBotFirebaseService.remove(["agent_servers", serverId, "channels", channelId, name])
    else:
        GBotFirebaseService.set(["agent_servers", serverId, "channels", channelId, name], value)

def clearServer(serverId):
    GBotFirebaseService.remove(["agent_servers", serverId])

def resetPlace(serverId, channelId, names, deleteMemories):
    # only ever the place named: a server reset leaves every channel's own values and memories alone
    place = ["agent_servers", serverId] if channelId is None else ["agent_servers", serverId, "channels", channelId]
    for name in names:
        GBotFirebaseService.remove(place + [name])
    if deleteMemories:
        memories = GBotFirebaseService.get(["agent_servers", serverId, "memories"]).val() or {}
        wanted = None if channelId is None else str(channelId)
        for memoryId, memory in memories.items():
            if memory.get('channelId') == wanted:
                GBotFirebaseService.remove(["agent_servers", serverId, "memories", memoryId])

def saveMemory(serverId, text, savedBy, savedById, byAdmin, date, channelId = None, memberLimit = None):
    # one function, so two saves can't both pass the counts and land on the worker in turn
    memories = GBotFirebaseService.get(["agent_servers", serverId, "memories"]).val() or {}
    if len(memories) >= GBotPropertiesManager.AGENT_MAX_MEMORIES:
        return MEMORY_FULL
    if memberLimit is not None and sum(memory.get('savedById') == savedById for memory in memories.values()) >= memberLimit:
        return MEMORY_MEMBER_LIMIT
    memory = {'text': text, 'savedBy': savedBy, 'savedById': savedById, 'byAdmin': byAdmin, 'date': date}
    if channelId is not None:
        memory['channelId'] = channelId
    GBotFirebaseService.push(["agent_servers", serverId, "memories"], memory)
    return MEMORY_SAVED

def changeMemory(serverId, memoryId, mayChange, newText = None, editedBy = None):
    # one function, so the memory can't change between the check and the write. The model chose this
    # id, so it is looked up among the keys rather than trusted as part of a database path. An edit
    # leaves byAdmin alone, so changing a member's words can't turn them into an instruction.
    memories = GBotFirebaseService.get(["agent_servers", serverId, "memories"]).val() or {}
    memory = memories.get(memoryId)
    if memory is None or not mayChange(memory):
        return memory, False
    if newText is None:
        GBotFirebaseService.remove(["agent_servers", serverId, "memories", memoryId])
    else:
        GBotFirebaseService.update(["agent_servers", serverId, "memories", memoryId], {'text': newText, 'editedBy': editedBy})
    return memory, True

def getSharedTokensUsed(day):
    usage = GBotFirebaseService.get(["agent_shared", "usage"]).val() or {}
    return usage.get('tokens', 0) if usage.get('day') == day else 0

def addSharedUsage(day, tokens):
    # one function, like addUsage. Dev and prod count together, since they share a key and a database.
    GBotFirebaseService.set(["agent_shared", "usage"], {'day': day, 'tokens': getSharedTokensUsed(day) + tokens})

def addUsage(serverId, day, tokens):
    # one function for the same reason, and only today is kept
    usage = GBotFirebaseService.get(["agent_servers", serverId, "usage"]).val() or {}
    used = usage.get('tokens', 0) if usage.get('day') == day else 0
    GBotFirebaseService.set(["agent_servers", serverId, "usage"], {'day': day, 'tokens': used + tokens})
