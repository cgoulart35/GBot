#region IMPORTS
from GBotDiscord import firebase
#endregion

def getAllServers():
    result = firebase.db.child("servers").get(firebase.getAuthToken())
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
    firebase.db.child("servers").child(serverId).set(defaultConfig)

def clearServerValues(serverId):
    firebase.db.child("servers").child(serverId).remove(firebase.getAuthToken())

def getAllServerValues(serverId):
    result = firebase.db.child("servers").child(serverId).get(firebase.getAuthToken())
    return result.val()

def getServerValue(serverId, item):
    result = firebase.db.child("servers").child(serverId).child(item).get(firebase.getAuthToken())
    return result.val()

def setServerValue(serverId, item, value):
    firebase.db.child("servers").child(serverId).child(item).set(value)