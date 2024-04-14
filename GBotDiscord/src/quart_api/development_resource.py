#region IMPORTS
import logging
import json
import httpx
import nextcord
from quart import abort
from datetime import datetime

from GBotDiscord.src.quart_api import development_queries
from GBotDiscord.src.properties import GBotPropertiesManager
from GBotDiscord.src.presence.presence_cog import Presence
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
                        "name": "changePresence",
                        "type": "<playing/listening/watching>",
                        "value": "my string",
                        "expire": "<%m/%d/%y %I:%M:%S %p>"
                    }
                ]
            },
            "postBodyTemplate": {
                "action": {
                    "name": "changePresence",
                    "type": "listening",
                    "value": "for post requests",
                    "expire": "10/30/24 01:00:00 AM"
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
                
                if value["action"]["name"] == "changePresence" and "type" in value["action"] and "value" in value["action"]:
                    try:
                        message = "Invalid expire. Please format as: %m/%d/%y %I:%M:%S %p"
                        expire = None
                        if "expire" in value["action"]:
                            stringTime = value["action"]["expire"]
                            expire = datetime.strptime(stringTime, "%m/%d/%y %I:%M:%S %p")

                        message = "Invalid type. Please use one of the following: playing listening watching"
                        type = value["action"]["type"]
                        if type != "playing" and type != "listening" and type != "watching":
                            raise Exception
                        
                        message = "Invalid value."
                        value = value["action"]["value"]
                        if type == "playing":
                            activity = nextcord.Game(value)
                        elif type == "listening":
                            activity = nextcord.Activity(type = nextcord.ActivityType.listening, name = value)
                        elif type == "watching":
                            activity = nextcord.Activity(type = nextcord.ActivityType.watching, name = value)

                        message = "Unable to change presence."
                        presence: Presence = client.get_cog('Presence')
                        result = await presence.changePresence(activity, expire)
                        if result:
                            message = f"Presence set to: '{type} {value}'"
                            if expire:
                                message += f" until {stringTime}"
                            return {"action": "changePresence", "status": "success", "message": message}
                        else:
                            raise Exception
                    except:
                        return {"action": "changePresence", "status": "failure", "message": f"Error: {message}"}
                    
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