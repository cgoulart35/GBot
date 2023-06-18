#region IMPORTS
import logging
import json
import nextcord
from quart import abort

from GBotDiscord.src import utils
from GBotDiscord.src.config import config_queries
from GBotDiscord.src.storms.storms_cog import Storms
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
                        returnStates = {}
                        for serverId in storms.stormStates.keys():
                            storms.generateNewStorm(serverId, True)
                            returnStates[serverId] = utils.copyDictWithoutKeys(storms.stormStates[serverId], "deleteMessages")
                        return returnStates 
                    else:
                        storms.generateNewStorm(serverId, True)
                        return utils.copyDictWithoutKeys(storms.stormStates[serverId], "deleteMessages")

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
                        returnStates = {}
                        for serverId, stormState in storms.stormStates.items():
                            returnStates[serverId] = utils.copyDictWithoutKeys(stormState, "deleteMessages")
                        return returnStates
                    else:
                        return utils.copyDictWithoutKeys(storms.stormStates[serverId], "deleteMessages")

            return {"status": "error", "message": "Error: Invalid request."}
        except:
            abort(400, "Error: Unhandled exception.")