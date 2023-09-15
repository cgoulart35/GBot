#region IMPORTS
import json
import pyrebase

from GBotDiscord.src.properties import GBotPropertiesManager
#endregion

class GBotFirebaseService:
    db = None
    auth = None

    def startFirebaseScheduler():
        # initialize firebase and database
        firebaseConfigJsonObj = json.loads(GBotPropertiesManager.FIREBASE_CONFIG_JSON)
        firebase = pyrebase.initialize_app(firebaseConfigJsonObj)
        GBotFirebaseService.db = firebase.database()
        GBotFirebaseService.auth = firebase.auth()

    def authenticate(username, password):
        try:
            GBotFirebaseService.auth.sign_in_with_email_and_password(username, password)
            return True
        except:
            return False

    def get(children):
        dbObj = GBotFirebaseService.loopChildren(children)
        return dbObj.get()

    def remove(children):
        dbObj = GBotFirebaseService.loopChildren(children)
        dbObj.remove()

    def set(children, object):
        dbObj = GBotFirebaseService.loopChildren(children)
        dbObj.set(object)

    def push(children, object):
        dbObj = GBotFirebaseService.loopChildren(children)
        dbObj.push(object)

    def update(children, object):
        dbObj = GBotFirebaseService.loopChildren(children)
        dbObj.update(object)
    
    def loopChildren(children):
        dbObj = GBotFirebaseService.db
        for child in children:
            dbObj = dbObj.child(child)
        return dbObj
