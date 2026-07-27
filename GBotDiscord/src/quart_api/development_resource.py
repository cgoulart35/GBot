#region IMPORTS
import logging
import json
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