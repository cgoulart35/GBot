#region IMPORTS
import asyncio
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from functools import partial
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
    # one thread, so database work happens strictly one function at a time, in the order it was asked for
    worker = ThreadPoolExecutor(max_workers = 1, thread_name_prefix = 'database')

    async def run(function, *args):
        # Database calls block, and on the event loop they stop the whole bot for each one. Pass a
        # function that does all of a step's database work, so nothing else lands between its calls.
        # Other commands can run during this await: see CLAUDE.md before using it around money.
        return await asyncio.get_running_loop().run_in_executor(GBotFirebaseService.worker, partial(function, *args))

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
        except httpx.HTTPError:
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

    def updateMany(changes):
        # {'gcoin/1/balance': '5', 'gtrade/personal/1/abc': None, ...}, where None deletes. One request
        # that the database applies completely or not at all, which is what keeps money and items
        # consistent if something fails partway. A path can't sit inside another path in the same call.
        GBotFirebaseService.getReference([]).update(changes)

    def path(*children):
        return "/".join(str(child) for child in children)

    def newKey():
        # for a new child inside updateMany, as push writes straight away. Nothing relies on these
        # sorting by time the way push ids do: history sorts on its own date. Hex is always a legal key.
        return uuid.uuid4().hex

    def getReference(children):
        return db.reference("/" + "/".join(str(child) for child in children))
