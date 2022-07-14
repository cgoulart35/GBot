#region IMPORTS
import logging
import json
import os
import nextcord
from quart import Quart, request

from GBotDiscord.quart_api.development_resource import Development
from GBotDiscord.quart_api.discord_resource import Discord
from GBotDiscord.quart_api.halo_resource import HaloCompetition, HaloMOTD
#endregion

class GBotAPIService:
    client = None
    logger = logging.getLogger()
    API_PORT = os.getenv("API_PORT")

    def registerAPI(gbotClient: nextcord.Client):
        GBotAPIService.client = gbotClient
        app = Quart(__name__)

        @app.route("/GBot/development/", methods = ["GET"])
        def get_development():
            response = Development.get()
            GBotAPIService.logPayloadAndResponse(response)
            return response

        @app.route("/GBot/development/", methods = ["POST"])
        async def post_development():
            data = await request.get_data()
            response = await Development.post(data)
            GBotAPIService.logPayloadAndResponse(response, data)
            return response

        @app.route("/GBot/discord/", methods = ["GET"])
        def get_discord():
            response = Discord.get()
            GBotAPIService.logPayloadAndResponse(response)
            return response

        @app.route("/GBot/discord/", methods = ["POST"])
        async def post_discord():
            data = await request.get_data()
            response = await Discord.post(GBotAPIService.client, data)
            GBotAPIService.logPayloadAndResponse(response, data)
            return response

        @app.route("/GBot/halo/competition/", methods = ["GET"])
        def get_halo_competition():
            response = HaloCompetition.get()
            GBotAPIService.logPayloadAndResponse(response)
            return response

        @app.route("/GBot/halo/competition/", methods = ["POST"])
        async def post_halo_competition():
            data = await request.get_data()
            response = await HaloCompetition.post(GBotAPIService.client, data)
            GBotAPIService.logPayloadAndResponse(response, data)
            return response

        @app.route("/GBot/halo/motd/", methods = ["GET"])
        def get_halo_motd():
            response = HaloMOTD.get()
            GBotAPIService.logPayloadAndResponse(response)
            return response

        @app.route("/GBot/halo/motd/", methods = ["POST"])
        async def post_halo_motd():
            data = await request.get_data()
            response = await HaloMOTD.post(GBotAPIService.client, data)
            GBotAPIService.logPayloadAndResponse(response, data)
            return response

        gbotClient.loop.create_task(app.run_task(host='0.0.0.0', port=int(GBotAPIService.API_PORT), debug=True, use_reloader=False))

    def logPayloadAndResponse(response, data = None):
        if data != None:
            message = {
                "response": response,
                "requestPayload": json.loads(data.decode("utf-8"))
            }
        else:
            message = {
                "response": response
            }

        GBotAPIService.logger.info(json.dumps(message))