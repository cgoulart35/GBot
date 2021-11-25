#region IMPORTS
import pathlib
import importlib.util
#endregion

# get parent directory
parentDir = str(pathlib.Path(__file__).parent.parent.parent.absolute())
parentDir = parentDir.replace("\\",'/')

# get firebase service
spec = importlib.util.spec_from_file_location('Shared', parentDir + '/Shared/firebaseService.py')
firebaseService = importlib.util.module_from_spec(spec)
spec.loader.exec_module(firebaseService)

def getAllServers():
    result = firebaseService.getDb().child("servers").get(firebaseService.getAuthToken())
    return result.val()

def upgradeServerValues(serverId, currentBotVerion):
    serverConfig = getAllServerValues(serverId)
    setServerValue(serverId, 'version', currentBotVerion)    
    # add new database fields here that have default values
    # if 'example_switch' not in serverConfig or serverConfig['example_switch'] == None:
    #     setServerValue(serverId, 'example_switch', True)

def initServerValues(serverId, currentBotVerion):
    defaultConfig = {
        'id': serverId,
        'version': currentBotVerion,
        'prefix': '.'
    }
    firebaseService.getDb().child("servers").child(serverId).set(defaultConfig)

def clearServerValues(serverId):
    firebaseService.getDb().child("servers").child(serverId).remove(firebaseService.getAuthToken())

def getAllServerValues(serverId):
    result = firebaseService.getDb().child("servers").child(serverId).get(firebaseService.getAuthToken())
    return result.val()

def getServerValue(serverId, item):
    result = firebaseService.getDb().child("servers").child(serverId).child(item).get(firebaseService.getAuthToken())
    return result.val()

def setServerValue(serverId, item, value):
    firebaseService.getDb().child("servers").child(serverId).child(item).set(value)