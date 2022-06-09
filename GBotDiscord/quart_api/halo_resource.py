#region IMPORTS
import logging
import json
import nextcord
from quart import abort

from GBotDiscord.config import config_queries
from GBotDiscord.halo.halo_cog import Halo
#endregion

class HaloCompetition():
    logger = logging.getLogger()

    def get():
        return { "postBodyTemplate": { "serverId": "012345678910111213" },
                 "options": ["012345678910111213", "all"] }

    async def post(client: nextcord.Client, data):
        try:
            value = json.loads(data)

            if "serverId" in value:
                serverId = value["serverId"].strip()
                if serverId != "" and (serverId == "all" or config_queries.getAllServerValues(serverId) is not None):
                    if serverId == "all":
                        selectedServerId = None
                    else:
                        selectedServerId = serverId
                    halo: Halo = client.get_cog('Halo')
                    await halo.haloPlayerStatsGetRequests(selectedServerId)
                    return {"action": f"haloPlayerStatsGetRequests({serverId})", "status": "success"}

            return {"status": "error", "message": "Error: Invalid request."}
        except:
            abort(400, "Error: Unhandled exception.")

class HaloMOTD():

    def get():
        return { "postBodyTemplate": { "serverId": "012345678910111213" },
                 "options": ["012345678910111213", "all"] }

    async def post(client: nextcord.Client, data):
        try:
            value = json.loads(data)

            if "serverId" in value:
                serverId = value["serverId"].strip()
                if serverId != "" and (serverId == "all" or config_queries.getAllServerValues(serverId) is not None):
                    if serverId == "all":
                        selectedServerId = None
                    else:
                        selectedServerId = serverId
                    halo: Halo = client.get_cog('Halo')
                    await halo.haloMotdGetRequest(selectedServerId)
                    return {"action": f"haloMotdGetRequest({serverId})", "status": "success"}

            return {"status": "error", "message": "Error: Invalid request."}
        except:
            abort(400, "Error: Unhandled exception.")