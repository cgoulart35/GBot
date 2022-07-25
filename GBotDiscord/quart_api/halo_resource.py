# #region IMPORTS
# import logging
# import json
# import nextcord
# from quart import abort

# from GBotDiscord.config import config_queries
# from GBotDiscord.halo.halo_cog import Halo
# #endregion

# class HaloCompetition():
#     logger = logging.getLogger()

#     def get():
#         return {
#             "options": {
#                 "serverId": [
#                     "012345678910111213",
#                     "all"
#                 ],
#                 "startCompetition": [
#                     True,
#                     False
#                 ]
#             },
#             "postBodyTemplate": {
#                 "serverId": "012345678910111213",
#                 "startCompetition": False
#             }
#         }

#     async def post(client: nextcord.Client, data):
#         try:
#             value = json.loads(data)

#             if "serverId" in value and "startCompetition" in value:
#                 serverId = value["serverId"].strip()
#                 startCompetition = value["startCompetition"]
#                 if serverId != "" and (serverId == "all" or config_queries.getAllServerValues(serverId) is not None) and isinstance(startCompetition, bool):
#                     if serverId == "all":
#                         selectedServerId = None
#                     else:
#                         selectedServerId = serverId
#                     halo: Halo = client.get_cog('Halo')
#                     await halo.haloPlayerStatsGetRequests(selectedServerId, startCompetition)
#                     return {"action": f"haloPlayerStatsGetRequests({serverId}, {startCompetition})", "status": "success"}

#             return {"status": "error", "message": "Error: Invalid request."}
#         except:
#             abort(400, "Error: Unhandled exception.")

# class HaloMOTD():

#     def get():
#         return {
#             "options": {
#                 "serverId": [
#                     "012345678910111213",
#                     "all"
#                 ]
#             },
#             "postBodyTemplate": {
#                 "serverId": "012345678910111213"
#             }
#         }

#     async def post(client: nextcord.Client, data):
#         try:
#             value = json.loads(data)

#             if "serverId" in value:
#                 serverId = value["serverId"].strip()
#                 if serverId != "" and (serverId == "all" or config_queries.getAllServerValues(serverId) is not None):
#                     if serverId == "all":
#                         selectedServerId = None
#                     else:
#                         selectedServerId = serverId
#                     halo: Halo = client.get_cog('Halo')
#                     await halo.haloMotdGetRequest(selectedServerId)
#                     return {"action": f"haloMotdGetRequest({serverId})", "status": "success"}

#             return {"status": "error", "message": "Error: Invalid request."}
#         except:
#             abort(400, "Error: Unhandled exception.")