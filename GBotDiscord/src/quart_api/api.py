#region IMPORTS
import logging
import json
import asyncio
import nextcord
from hypercorn.asyncio import serve
from hypercorn.config import Config as HypercornConfig
from quart import Quart, request, abort
from quart_cors import cors
from functools import wraps

from GBotDiscord.src.quart_api.development_resource import Development
from GBotDiscord.src.quart_api.discord_resource import Discord
# DISCONTINUED from GBotDiscord.src.quart_api.halo_resource import HaloCompetition, HaloMOTD
from GBotDiscord.src.quart_api.leaderboards_resource import Leaderboard
from GBotDiscord.src.quart_api.storms_resource import StormsStart, StormsState
from GBotDiscord.src.properties import GBotPropertiesManager
from GBotDiscord.src.firebase import GBotFirebaseService
#endregion

class GBotAPIService:
    client = None
    logger = logging.getLogger()

    def registerAPI(gbotClient: nextcord.Client):
        GBotAPIService.client = gbotClient
        app = Quart(__name__)
        app = cors(app, allow_origin="*")

        def authorize(function):
            if asyncio.iscoroutinefunction(function):
                @wraps(function)
                async def wrapper(*args, **kwargs):
                    auth = request.authorization
                    if (auth is None or
                        auth.type != "basic" or
                        auth.username is None or
                        auth.password is None or
                        not GBotFirebaseService.authenticate(auth.username, auth.password)):
                        abort(401)
                    return await function(*args, **kwargs)
                return wrapper
            else:
                @wraps(function)
                def wrapper(*args, **kwargs):
                    auth = request.authorization
                    if (auth is None or
                        auth.type != "basic" or
                        auth.username is None or
                        auth.password is None or
                        not GBotFirebaseService.authenticate(auth.username, auth.password)):
                        abort(401)
                    return function(*args, **kwargs)
                return wrapper

        @app.route("/GBot/private/development/doc/", methods = ["GET"])
        @authorize
        def get_development_doc():
            response = Development.doc()
            GBotAPIService.logPayloadAndResponse(response)
            return response

        @app.route("/GBot/private/development/", methods = ["POST"])
        @authorize
        async def post_development():
            data = await request.get_data()
            response = await Development.post(GBotAPIService.client, data)
            GBotAPIService.logPayloadAndResponse(response, data)
            return response

        @app.route("/GBot/private/discord/doc/", methods = ["GET"])
        @authorize
        def get_discord_doc():
            response = Discord.doc()
            GBotAPIService.logPayloadAndResponse(response)
            return response

        @app.route("/GBot/private/discord/", methods = ["POST"])
        @authorize
        async def post_discord():
            data = await request.get_data()
            response = await Discord.post(GBotAPIService.client, data)
            GBotAPIService.logPayloadAndResponse(response, data)
            return response

        # DISCONTINUED
        # @app.route("/GBot/private/halo/competition/doc/", methods = ["GET"])
        # @authorize
        # def get_halo_competition_doc():
        #     response = HaloCompetition.doc()
        #     GBotAPIService.logPayloadAndResponse(response)
        #     return response

        # @app.route("/GBot/private/halo/competition/", methods = ["POST"])
        # @authorize
        # async def post_halo_competition():
        #     data = await request.get_data()
        #     response = await HaloCompetition.post(GBotAPIService.client, data)
        #     GBotAPIService.logPayloadAndResponse(response, data)
        #     return response

        # @app.route("/GBot/private/halo/motd/doc/", methods = ["GET"])
        # @authorize
        # def get_halo_motd_doc():
        #     response = HaloMOTD.doc()
        #     GBotAPIService.logPayloadAndResponse(response)
        #     return response

        # @app.route("/GBot/private/halo/motd/", methods = ["POST"])
        # @authorize
        # async def post_halo_motd():
        #     data = await request.get_data()
        #     response = await HaloMOTD.post(GBotAPIService.client, data)
        #     GBotAPIService.logPayloadAndResponse(response, data)
        #     return response

        @app.route("/GBot/private/storms/start/doc/", methods = ["GET"])
        @authorize
        def get_storms_start_doc():
            response = StormsStart.doc()
            GBotAPIService.logPayloadAndResponse(response)
            return response

        @app.route("/GBot/private/storms/start/", methods = ["POST"])
        @authorize
        async def post_storms_start():
            data = await request.get_data()
            response = await StormsStart.post(GBotAPIService.client, data)
            GBotAPIService.logPayloadAndResponse(response, data)
            return response

        @app.route("/GBot/private/storms/state/doc/", methods = ["GET"])
        @authorize
        def get_storms_state_doc():
            response = StormsState.doc()
            GBotAPIService.logPayloadAndResponse(response)
            return response

        @app.route("/GBot/private/storms/state/", methods = ["POST"])
        @authorize
        async def post_storms_state():
            data = await request.get_data()
            response = await StormsState.post(GBotAPIService.client, data)
            GBotAPIService.logPayloadAndResponse(response, data)
            return response
        
        @app.route("/GBot/public/leaderboard/", methods = ["GET"])
        def get_leaderboard():
            response = Leaderboard.get()
            GBotAPIService.logPayloadAndResponse(response)
            return response

        # hypercorn directly rather than app.run_task, which points hypercorn's logs at raw stdout and
        # stderr, where they arrive with hypercorn's own prefix and the error log twice. Given logger
        # objects, it logs through the root handlers like everything else.
        config = HypercornConfig()
        config.bind = [f'0.0.0.0:{GBotPropertiesManager.API_PORT}']
        config.certfile = '/GBot/server.crt'
        config.keyfile = '/GBot/server.key'
        config.access_log_format = '%(h)s %(r)s %(s)s %(b)s %(D)s'
        config.accesslog = logging.getLogger('hypercorn.access')
        config.errorlog = logging.getLogger('hypercorn.error')
        gbotClient.loop.create_task(serve(app, config))

    def logPayloadAndResponse(response, data = None):
        if data != None:
            message = {
                "response": response,
                "requestPayload": json.loads(data.decode("utf-8"))
            }
            GBotAPIService.logger.info(json.dumps(message))
        else:
            # A request without a payload is a read: a doc page or the leaderboard, which is public
            # and would write every user's balance to the log on every hit.
            GBotAPIService.logger.debug(json.dumps({"response": response}))