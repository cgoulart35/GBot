#region IMPORTS
import json
import httpx
import firebase_admin
from firebase_admin import credentials, db

from GBotDiscord.src.properties import GBotPropertiesManager
#endregion

class GBotFirebaseResult:

    def __init__(self, value):
        self.value = value

    def val(self):
        return self.value

class GBotFirebaseService:
    apiKey = None

    def startFirebaseScheduler():
        # initialize the firebase-admin app and realtime database
        firebaseConfigJsonObj = json.loads(GBotPropertiesManager.FIREBASE_CONFIG_JSON)
        GBotFirebaseService.apiKey = firebaseConfigJsonObj["apiKey"]
        credential = credentials.Certificate(firebaseConfigJsonObj["serviceAccount"])
        firebase_admin.initialize_app(credential, {"databaseURL": firebaseConfigJsonObj["databaseURL"]})

    def authenticate(username, password):
        # firebase-admin is a server SDK with no password sign-in; use the Identity Toolkit REST API
        try:
            url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={GBotFirebaseService.apiKey}"
            response = httpx.post(url, json = {"email": username, "password": password, "returnSecureToken": True})
            return response.status_code == 200
        except:
            return False

    def get(children):
        dbObj = GBotFirebaseService.getReference(children)
        return GBotFirebaseResult(dbObj.get())

    def remove(children):
        dbObj = GBotFirebaseService.getReference(children)
        dbObj.delete()

    def set(children, object):
        dbObj = GBotFirebaseService.getReference(children)
        dbObj.set(object)

    def push(children, object):
        dbObj = GBotFirebaseService.getReference(children)
        dbObj.push(object)

    def update(children, object):
        dbObj = GBotFirebaseService.getReference(children)
        dbObj.update(object)

    def getReference(children):
        return db.reference("/" + "/".join(str(child) for child in children))
