#region IMPORTS
import logging
import json
import httpx
import nextcord
from quart import abort

from GBotDiscord.src.quart_api import development_queries
from GBotDiscord.src.properties import GBotPropertiesManager
from GBotDiscord.src.patreon.patreon_cog import Patreon
#endregion

class Development():
    logger = logging.getLogger()

    def doc():
        return {
            "options": {
                "action": [
                    {
                        "name": "rebuildLatest"
                    },
                    {
                        "name": "runDatabasePatch",
                        "patch": "7.0.0_create_leaderboard_table"
                    },
                    {
                        "name": "setProperty",
                        "property": "LOG_LEVEL",
                        "value": "DEBUG"
                    },
                    {
                        "name": "syncSubscribers"
                    }
                ]
            },
            "postBodyTemplate": {
                "action": {
                    "name": "setProperty",
                    "property": "LOG_LEVEL",
                    "value": "DEBUG"
                }
            }
        }

    async def post(client: nextcord.Client, data):
        try:
            value = json.loads(data)

            if "action" in value and "name" in value["action"]:
                if value["action"]["name"] == "rebuildLatest":
                    response = await Development.sendRequestToGitUpdaterHost()
                    if response == None:
                        return {"action": "rebuildLatest", "status": "failure", "message": "Error: Can't communicate with the Git Project Update Handler API."}
                    if "status" not in response:
                        return {"action": "rebuildLatest", "status": "failure", "message": "Error: Missing status in response from Git Project Update Handler API."}
                    if "message" not in response:
                        return {"action": "rebuildLatest", "status": "failure", "message": "Error: Missing message in response from Git Project Update Handler API."}
                    return {"action": "rebuildLatest", "status": response["status"], "message": response["message"]}

                if value["action"]["name"] == "runDatabasePatch" and "patch" in value["action"]:
                    patch = value["action"]["patch"].strip()
                    status = "failure"
                    message = "Invalid patch."
                    if patch == "7.0.0_create_leaderboard_table":
                        status = "success"
                        message = f"Ran patch {patch}."
                        await development_queries.create_leaderboard_table_7_0_0(client)
                    return {"action": "runDatabasePatch", "status": status, "message": message}

                if value["action"]["name"] == "setProperty" and "property" in value["action"] and "value" in value["action"]:
                    property = value["action"]["property"].strip()
                    value = value["action"]["value"]
                    result = GBotPropertiesManager.setProperty(property, value)
                    status = "failure"
                    message = "Invalid property."
                    if result:
                        status = "success"
                        message = f"Property '{property}' set to: {value}"
                    return {"action": "setProperty", "status": status, "message": message}
                
                if value["action"]["name"] == "syncSubscribers":
                    patreon: Patreon = client.get_cog('Patreon')
                    try:
                        await patreon.patreon_validation()
                        response = {"action": "syncSubscribers", "status": "success", "message": "GBot is synced with current subscribers."}
                    except:
                        response = {"action": "syncSubscribers", "status": "failure", "message": "GBot failed to sync with current subscribers."}
                    return response
                    
            return {"status": "error", "message": "Error: Invalid request."}
        except:
            abort(400, "Error: Unhandled exception.")

    async def sendRequestToGitUpdaterHost():
        try:
            async with httpx.AsyncClient() as httpxClient:
                url = GBotPropertiesManager.GIT_UPDATER_HOST
                response = None
                response = await httpxClient.post(url, data = json.dumps({"application": "GBot"}), timeout = 60)
                if response == None or response.status_code != 200:
                    return None
                return response.json()
        except:
            return None