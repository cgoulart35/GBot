#region IMPORTS
import pathlib
import os
import logging
import json
import pyrebase
from configparser import ConfigParser
from apscheduler.schedulers.background import BackgroundScheduler
#endregion

def refreshToken():
    global user
    user = auth.refresh(user['refreshToken'])

def getAuthToken():
    global user
    return user['idToken']

def getDb():
    global db
    return db

# get parent directory
parentDir = str(pathlib.Path(__file__).parent.parent.absolute())
parentDir = parentDir.replace("\\",'/')

# create and configure root logger
if not os.path.exists('Logs'):
    os.mkdir('Logs')
LOG_FORMAT = "%(levelname)s %(asctime)s - %(message)s"
logging.basicConfig(filename = parentDir + '/Logs/GBot Discord.log', level = logging.INFO, format = LOG_FORMAT)
logger = logging.getLogger()

# get configuration variables
firebaseConfig = ConfigParser()
firebaseConfig.read(parentDir + '/Shared/properties.ini')
firebaseConfigJson = firebaseConfig['properties']['firebaseConfigJson']
firebaseAuthEmail = firebaseConfig['properties']['firebaseAuthEmail']
firebaseAuthPassword = firebaseConfig['properties']['firebaseAuthPassword']

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