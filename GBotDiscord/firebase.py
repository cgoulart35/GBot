#region IMPORTS
import os
import json
import pyrebase
from apscheduler.schedulers.background import BackgroundScheduler
#endregion

class GBotFirebaseService:

    firebaseConfigJson = os.getenv("FIREBASE_CONFIG_JSON")
    firebaseAuthEmail = os.getenv("FIREBASE_AUTH_EMAIL")
    firebaseAuthPassword = os.getenv("FIREBASE_AUTH_PASSWORD")
    db = None
    auth = None
    user = None

    def refreshToken():
        GBotFirebaseService.user = GBotFirebaseService.auth.refresh(GBotFirebaseService.user['refreshToken'])

    def getAuthToken():
        return GBotFirebaseService.user['idToken']

    def startFirebaseScheduler():
        # initialize firebase and database
        firebaseConfigJsonObj = json.loads(GBotFirebaseService.firebaseConfigJson)
        firebase = pyrebase.initialize_app(firebaseConfigJsonObj)
        GBotFirebaseService.db = firebase.database()
        GBotFirebaseService.auth = firebase.auth()

        # sign into service account
        GBotFirebaseService.user = GBotFirebaseService.auth.sign_in_with_email_and_password(GBotFirebaseService.firebaseAuthEmail, GBotFirebaseService.firebaseAuthPassword)

        # create event scheduler for refreshing auth token
        sched = BackgroundScheduler(daemon=True)
        sched.add_job(GBotFirebaseService.refreshToken, 'interval', minutes = 30)
        sched.start()