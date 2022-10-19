#region IMPORTS
import json
import pyrebase
from apscheduler.schedulers.background import BackgroundScheduler

from GBotDiscord.properties import GBotPropertiesManager
#endregion

class GBotFirebaseService:
    db = None
    auth = None
    user = None

    def refreshToken():
        GBotFirebaseService.user = GBotFirebaseService.auth.refresh(GBotFirebaseService.user['refreshToken'])

    def getAuthToken():
        return GBotFirebaseService.user['idToken']

    def startFirebaseScheduler():
        # initialize firebase and database
        firebaseConfigJsonObj = json.loads(GBotPropertiesManager.FIREBASE_CONFIG_JSON)
        firebase = pyrebase.initialize_app(firebaseConfigJsonObj)
        GBotFirebaseService.db = firebase.database()
        GBotFirebaseService.auth = firebase.auth()

        # sign into service account
        GBotFirebaseService.user = GBotFirebaseService.auth.sign_in_with_email_and_password(GBotPropertiesManager.FIREBASE_AUTH_EMAIL, GBotPropertiesManager.FIREBASE_AUTH_PASSWORD)

        # create event scheduler for refreshing auth token
        sched = BackgroundScheduler(daemon=True)
        sched.add_job(GBotFirebaseService.refreshToken, 'interval', minutes = 30)
        sched.start()

    def get(children):
        dbObj = GBotFirebaseService.loopChildren(children)
        return dbObj.get(GBotFirebaseService.getAuthToken())

    def remove(children):
        dbObj = GBotFirebaseService.loopChildren(children)
        dbObj.remove(GBotFirebaseService.getAuthToken())

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
