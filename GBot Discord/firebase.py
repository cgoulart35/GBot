#region IMPORTS
import os
import json
import pyrebase
from apscheduler.schedulers.background import BackgroundScheduler
#endregion

db = None
auth = None
user = None

def refreshToken():
    global user
    user = auth.refresh(user['refreshToken'])

def getAuthToken():
    return user['idToken']

def startFirebaseScheduler(parentDir):
    global db, auth, user

    # get configuration variables
    firebaseConfigJson = os.getenv("FIREBASE_CONFIG_JSON")
    firebaseAuthEmail = os.getenv("FIREBASE_AUTH_EMAIL")
    firebaseAuthPassword = os.getenv("FIREBASE_AUTH_PASSWORD")

    # initialize firebase and database
    firebaseConfigJsonObj = json.loads(firebaseConfigJson)
    firebase = pyrebase.initialize_app(firebaseConfigJsonObj)
    db = firebase.database()
    auth = firebase.auth()

    # sign into service account
    user = auth.sign_in_with_email_and_password(firebaseAuthEmail, firebaseAuthPassword)

    # create event scheduler for refreshing auth token
    sched = BackgroundScheduler(daemon=True)
    sched.add_job(refreshToken, 'interval', minutes = 30)
    sched.start()