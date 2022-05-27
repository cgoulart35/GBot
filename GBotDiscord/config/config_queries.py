#region IMPORTS
from GBotDiscord.firebase import GBotFirebaseService
#endregion

def getAllServers():
    result = GBotFirebaseService.db.child("servers").get(GBotFirebaseService.getAuthToken())
    return result.val()

# add new database fields here that have default values
def upgradeServerValues(serverId, currentBotVerion):
    serverConfig = getAllServerValues(serverId)
    setServerValue(serverId, 'version', currentBotVerion)

    # added music in GBot 2.0
    if 'toggle_music' not in serverConfig or serverConfig['toggle_music'] == None:
        setServerValue(serverId, 'toggle_music', False)

    # added gcoin and gtrade in GBot 3.0
    if 'toggle_gcoin' not in serverConfig or serverConfig['toggle_gcoin'] == None:
        setServerValue(serverId, 'toggle_gcoin', False)
    if 'toggle_gtrade' not in serverConfig or serverConfig['toggle_gtrade'] == None:
        setServerValue(serverId, 'toggle_gtrade', False)

def initServerValues(serverId, currentBotVerion):
    defaultConfig = {
        'version': currentBotVerion,
        'prefix': '.',
        'toggle_halo': False,
        'toggle_music': False,
        'toggle_gcoin': False,
        'toggle_gtrade': False
    }
    GBotFirebaseService.db.child("servers").child(serverId).set(defaultConfig)

def clearServerValues(serverId):
    GBotFirebaseService.db.child("servers").child(serverId).remove(GBotFirebaseService.getAuthToken())

def getAllServerValues(serverId):
    result = GBotFirebaseService.db.child("servers").child(serverId).get(GBotFirebaseService.getAuthToken())
    return result.val()

def getServerValue(serverId, item):
    result = GBotFirebaseService.db.child("servers").child(serverId).child(item).get(GBotFirebaseService.getAuthToken())
    return result.val()

def setServerValue(serverId, item, value):
    GBotFirebaseService.db.child("servers").child(serverId).child(item).set(value)