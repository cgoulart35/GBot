#region IMPORTS
import logging
import json
import nextcord
from quart import abort

from GBotDiscord.config import config_queries
from GBotDiscord.storms.storms_cog import Storms
#endregion

class StormsStart():
    logger = logging.getLogger()

    def get():
        return {
            "options": {
                "serverId": [
                    "012345678910111213",
                    "all"
                ]
            },
            "postBodyTemplate": {
                "serverId": "012345678910111213"
            }
        }

    async def post(client: nextcord.Client, data):
        try:
            value = json.loads(data)

            if "serverId" in value:
                serverId = value["serverId"].strip()
                if serverId != "" and (serverId == "all" or config_queries.getAllServerValues(serverId) is not None):
                    storms: Storms = client.get_cog('Storms')
                    if serverId == "all":
                        for serverId in storms.stormStates.keys():
                            storms.generateNewStorm(serverId, True)
                        return storms.stormStates
                    else:
                        storms.generateNewStorm(serverId, True)
                        return storms.stormStates[serverId]

            return {"status": "error", "message": "Error: Invalid request."}
        except:
            abort(400, "Error: Unhandled exception.")

class StormsState():
    logger = logging.getLogger()

    def get():
        return {
            "options": {
                "serverId": [
                    "012345678910111213",
                    "all"
                ]
            },
            "postBodyTemplate": {
                "serverId": "012345678910111213"
            }
        }

    async def post(client: nextcord.Client, data):
        try:
            value = json.loads(data)

            if "serverId" in value:
                serverId = value["serverId"].strip()
                if serverId != "" and (serverId == "all" or config_queries.getAllServerValues(serverId) is not None):
                    storms: Storms = client.get_cog('Storms')
                    if serverId == "all":
                        return storms.stormStates
                    else:
                        return storms.stormStates[serverId]

            return {"status": "error", "message": "Error: Invalid request."}
        except:
            abort(400, "Error: Unhandled exception.")