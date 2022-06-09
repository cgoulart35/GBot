#region IMPORTS
import os
import logging
import json
import httpx
from quart import abort
#endregion

class Development():
    logger = logging.getLogger()
    GIT_UPDATER_HOST = os.getenv("GIT_UPDATER_HOST")

    def get():
        return { "postBodyTemplate": { "doRebuildLatest": True },
                 "options": ["doRebuildLatest"] }

    async def post(data):
        try:
            value = json.loads(data)

            if "doRebuildLatest" in value and value["doRebuildLatest"] == True:
                response = await Development.sendRequestToGitUpdaterHost()
                if response == None:
                    return {"action": "doRebuildLatest", "status": "failure", "message": "Error: Can't communicate with the Git Project Update Handler API."}
                if "status" not in response:
                    return {"action": "doRebuildLatest", "status": "failure", "message": "Error: Missing status in response from Git Project Update Handler API."}
                if "message" not in response:
                    return {"action": "doRebuildLatest", "status": "failure", "message": "Error: Missing message in response from Git Project Update Handler API."}
                return {"action": "doRebuildLatest", "status": response["status"], "message": response["message"]}

            return {"status": "error", "message": "Error: Invalid request."}
        except:
            abort(400, "Error: Unhandled exception.")

    async def sendRequestToGitUpdaterHost():
        try:
            async with httpx.AsyncClient() as httpxClient:
                url = Development.GIT_UPDATER_HOST
                response = None
                response = await httpxClient.post(url, data = json.dumps({"application": "GBot"}), timeout = 60)
                if response == None or response.status_code != 200:
                    return None
                return response.json()
        except:
            return None