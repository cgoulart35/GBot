#region IMPORTS
import logging
import json
import nextcord
from quart import Quart, request

from GBotDiscord.src.quart_api.development_resource import Development
from GBotDiscord.src.quart_api.discord_resource import Discord
# DISCONTINUED from GBotDiscord.src.quart_api.halo_resource import HaloCompetition, HaloMOTD
from GBotDiscord.src.quart_api.storms_resource import StormsStart, StormsState
from GBotDiscord.src.properties import GBotPropertiesManager
#endregion

class GBotAPIService:
    client = None
    logger = logging.getLogger()

    def registerAPI(gbotClient: nextcord.Client):
        GBotAPIService.client = gbotClient
        app = Quart(__name__)

        @app.route("/GBot/private/development/doc/", methods = ["GET"])
        def get_development_doc():
            response = Development.doc()
            GBotAPIService.logPayloadAndResponse(response)
            return response

        @app.route("/GBot/private/development/", methods = ["POST"])
        async def post_development():
            data = await request.get_data()
            response = await Development.post(data)
            GBotAPIService.logPayloadAndResponse(response, data)
            return response

        @app.route("/GBot/private/discord/doc/", methods = ["GET"])
        def get_discord_doc():
            response = Discord.doc()
            GBotAPIService.logPayloadAndResponse(response)
            return response

        @app.route("/GBot/private/discord/", methods = ["POST"])
        async def post_discord():
            data = await request.get_data()
            response = await Discord.post(GBotAPIService.client, data)
            GBotAPIService.logPayloadAndResponse(response, data)
            return response

        # DISCONTINUED
        # @app.route("/GBot/private/halo/competition/doc/", methods = ["GET"])
        # def get_halo_competition_doc():
        #     response = HaloCompetition.doc()
        #     GBotAPIService.logPayloadAndResponse(response)
        #     return response

        # @app.route("/GBot/private/halo/competition/", methods = ["POST"])
        # async def post_halo_competition():
        #     data = await request.get_data()
        #     response = await HaloCompetition.post(GBotAPIService.client, data)
        #     GBotAPIService.logPayloadAndResponse(response, data)
        #     return response

        # @app.route("/GBot/private/halo/motd/doc/", methods = ["GET"])
        # def get_halo_motd_doc():
        #     response = HaloMOTD.doc()
        #     GBotAPIService.logPayloadAndResponse(response)
        #     return response

        # @app.route("/GBot/private/halo/motd/", methods = ["POST"])
        # async def post_halo_motd():
        #     data = await request.get_data()
        #     response = await HaloMOTD.post(GBotAPIService.client, data)
        #     GBotAPIService.logPayloadAndResponse(response, data)
        #     return response

        @app.route("/GBot/private/storms/start/doc/", methods = ["GET"])
        def get_storms_start_doc():
            response = StormsStart.doc()
            GBotAPIService.logPayloadAndResponse(response)
            return response

        @app.route("/GBot/private/storms/start", methods = ["POST"])
        async def post_storms_start():
            data = await request.get_data()
            response = await StormsStart.post(GBotAPIService.client, data)
            GBotAPIService.logPayloadAndResponse(response, data)
            return response

        @app.route("/GBot/private/storms/state/doc/", methods = ["GET"])
        def get_storms_state_doc():
            response = StormsState.doc()
            GBotAPIService.logPayloadAndResponse(response)
            return response

        @app.route("/GBot/private/storms/state", methods = ["POST"])
        async def post_storms_state():
            data = await request.get_data()
            response = await StormsState.post(GBotAPIService.client, data)
            GBotAPIService.logPayloadAndResponse(response, data)
            return response

        gbotClient.loop.create_task(app.run_task(host='0.0.0.0', port=GBotPropertiesManager.API_PORT, debug=True))

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