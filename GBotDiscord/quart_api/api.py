#region IMPORTS
import logging
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
            return Development.get()

        @app.route("/GBot/development/", methods = ["POST"])
        async def post_development():
            data = await request.get_data()
            return await Development.post(data)

        @app.route("/GBot/discord/", methods = ["GET"])
        def get_discord():
            return Discord.get()

        @app.route("/GBot/discord/", methods = ["POST"])
        async def post_discord():
            data = await request.get_data()
            return await Discord.post(GBotAPIService.client, data)

        @app.route("/GBot/halo/competition/", methods = ["GET"])
        def get_halo_competition():
            return HaloCompetition.get()

        @app.route("/GBot/halo/competition/", methods = ["POST"])
        async def post_halo_competition():
            data = await request.get_data()
            return await HaloCompetition.post(GBotAPIService.client, data)

        @app.route("/GBot/halo/motd/", methods = ["GET"])
        def get_halo_motd():
            return HaloMOTD.get()

        @app.route("/GBot/halo/motd/", methods = ["POST"])
        async def post_halo_motd():
            data = await request.get_data()
            return await HaloMOTD.post(GBotAPIService.client, data)

        gbotClient.loop.create_task(app.run_task(host='0.0.0.0', port=int(GBotAPIService.API_PORT), debug=True, use_reloader=False))